from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from neo4j import Driver
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from sound_detection.core.concurrency import analysis_semaphore
from sound_detection.db.models import BiomeSummary, Detection, Microphone, Recording, SpeciesSiteProximity
from sound_detection.knowledge.biome_export import backfill_images as export_backfill_images
from sound_detection.knowledge.biome_export import export_to_docx as export_to_docx_fn
from sound_detection.knowledge.biome_narratives import (
    build_human_narrative_chain,
    build_narrative_chain,
    build_species_enrichment_chain,
    enrich_species,
    generate_narratives,
)
from sound_detection.knowledge.filtering import (
    confirmation_signal_count,
    filter_species,
    is_confirmed_species,
    is_unexpected,
)
from sound_detection.knowledge.grading_criteria import DEFAULT_CRITERIA
from sound_detection.knowledge.rag.retriever import Retriever
from sound_detection.knowledge.species_knowledge_service import SpeciesKnowledgeService

log = structlog.get_logger(__name__)


class BiomeSummaryService:
    def __init__(
        self,
        session: AsyncSession,
        neo4j_driver: Driver | None = None,
    ) -> None:
        self.session = session
        self.neo4j_driver = neo4j_driver
        self.chunks_per_species: int = 10

        # Create SpeciesKnowledgeService only if we have a driver
        self.species_service = SpeciesKnowledgeService(neo4j_driver) if neo4j_driver else None
        self.retriever = Retriever(neo4j_driver) if neo4j_driver else None

    def _build_human_narrative_chain(self) -> Any:
        return build_human_narrative_chain()

    def _build_species_enrichment_chain(self) -> Any:
        return build_species_enrichment_chain()

    def _build_narrative_chain(self) -> Any:
        return build_narrative_chain()

    async def create_summary_job(
        self, site_id: UUID, window_days: int = 30, criteria: dict[str, Any] | None = None, dry_run: bool = False
    ) -> UUID:
        summary = BiomeSummary(
            site_id=site_id,
            window_days=window_days,
            status="pending",
            criteria=criteria,
        )
        # Stash dry_run flag in criteria so the background task can see it without a schema change
        if dry_run:
            summary.criteria = {**(criteria or {}), "_dry_run": True}
        self.session.add(summary)
        await self.session.commit()
        await self.session.refresh(summary)

        log.info("created_biome_summary_job", summary_id=str(summary.id), site_id=str(site_id), dry_run=dry_run)
        return summary.id

    async def generate_summary(self, summary_id: UUID) -> None:
        async with analysis_semaphore:
            summary = await self.session.get(BiomeSummary, summary_id)
            if not summary:
                log.warning("summary_not_found", summary_id=str(summary_id))
                return

            criteria = dict(summary.criteria or DEFAULT_CRITERIA)
            dry_run = bool(criteria.pop("_dry_run", False))
            start_time = datetime.now(UTC)
            log.info(
                "starting_biome_summary",
                summary_id=str(summary_id),
                window_days=summary.window_days,
                dry_run=dry_run,
            )

            try:
                summary.status = "processing:phase1"
                await self.session.commit()

                # === Phase 1: Data Gathering & Filtering ===
                log.info("phase1_start", summary_id=str(summary_id))
                phase_start = datetime.now(UTC)
                (
                    confirmed_counts,
                    speculated_counts,
                    confirmed_species,
                    speculated_species,
                ) = await self._gather_and_filter_species(summary, criteria)

                species_counts = {
                    name: confirmed_counts.get(name, 0) + speculated_counts.get(name, 0)
                    for name in set(confirmed_counts) | set(speculated_counts)
                }
                log.info(
                    "phase1_complete",
                    summary_id=str(summary_id),
                    duration_s=(datetime.now(UTC) - phase_start).seconds,
                    confirmed=len(confirmed_counts),
                    speculated=len(speculated_counts),
                )

                if dry_run:
                    summary.status = "dry_run_complete"
                    summary.summary_json = {
                        "window_days": summary.window_days,
                        "dry_run": True,
                        "confirmed_species_count": len(confirmed_counts),
                        "speculated_species_count": len(speculated_counts),
                        "confirmed_counts": confirmed_counts,
                        "speculated_counts": speculated_counts,
                        "confirmed_species": confirmed_species,
                        "speculated_species": speculated_species,
                        "generated_at": datetime.now(UTC).isoformat(),
                    }
                    duration = (datetime.now(UTC) - start_time).seconds
                    log.info("dry_run_complete", summary_id=str(summary_id), duration_s=duration)
                    return

                # === Phase 2: Per-Species Enrichment ===
                summary.status = "processing:phase2"
                await self.session.commit()
                phase_start = datetime.now(UTC)
                log.info(
                    "phase2_start",
                    summary_id=str(summary_id),
                    confirmed=len(confirmed_species),
                    speculated=len(speculated_species),
                )
                enriched_confirmed_species = await self._enrich_species(
                    summary_id, confirmed_species, summary.window_days
                )
                # skip enriching speculated species for now, it's very expensive
                enriched_speculated_species: list[dict] = []
                log.info(
                    "phase2_complete",
                    summary_id=str(summary_id),
                    duration_s=(datetime.now(UTC) - phase_start).seconds,
                )

                # === Phase 3: Narrative Generation ===
                summary.status = "processing:phase3"
                await self.session.commit()
                log.info("phase3_start", summary_id=str(summary_id))
                phase_start = datetime.now(UTC)
                machine_narrative, human_narrative, images, species_table = await self._generate_narratives(
                    summary_id=summary.id,
                    confirmed_counts=confirmed_counts,
                    enriched_confirmed_species=enriched_confirmed_species,
                    speculated_counts=speculated_counts,
                    enriched_speculated_species=enriched_speculated_species,
                    window_days=summary.window_days,
                    criteria=criteria,
                )
                summary.narrative = machine_narrative
                summary.human_narrative = human_narrative
                summary.notable_species_images = images
                summary.species_table = species_table  # type: ignore[assignment]
                log.info(
                    "phase3_complete",
                    summary_id=str(summary_id),
                    duration_s=(datetime.now(UTC) - phase_start).seconds,
                )

                # Save final results
                summary.summary_json = {
                    "window_days": summary.window_days,
                    "total_detections": sum(species_counts.values()),
                    "total_species": len(confirmed_counts | speculated_counts),
                    "species_counts": confirmed_counts,
                    "notable_species": enriched_confirmed_species,
                    "generated_at": datetime.now(UTC).isoformat(),
                }
                summary.status = "completed"

                duration = (datetime.now(UTC) - start_time).seconds
                log.info("summary_complete", summary_id=str(summary_id), duration_s=duration)

            except Exception as e:
                summary.status = "failed"
                summary.error_message = str(e)
                log.exception("summary_failed", summary_id=str(summary_id))
            finally:
                await self.session.commit()

    async def list_summaries(self, site_id: UUID, limit: int = 20) -> list[dict]:
        stmt = (
            select(BiomeSummary)
            .where(BiomeSummary.site_id == site_id)  # type: ignore[arg-type]
            .order_by(BiomeSummary.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        summaries = result.scalars().all()

        return [
            {
                "id": str(s.id),
                "created_at": s.created_at.isoformat(),
                "status": s.status,
                "window_days": s.window_days,
            }
            for s in summaries
        ]

    async def get_summary(self, summary_id: UUID) -> dict | None:
        summary = await self.session.get(BiomeSummary, summary_id)
        if not summary:
            return None

        return {
            "id": str(summary.id),
            "site_id": str(summary.site_id),
            "created_at": summary.created_at.isoformat(),
            "status": summary.status,
            "window_days": summary.window_days,
            "summary_json": summary.summary_json,
            "narrative": summary.narrative,  # existing (Weathervane)
            "human_narrative": summary.human_narrative,  # new pretty version
            "notable_species_images": summary.notable_species_images or [],
            "species_table": summary.species_table or [],
            "grok_narrative": summary.grok_narrative,  # optional high-powered version
            "error_message": summary.error_message,
        }

    async def delete_summary(self, summary_id: UUID) -> bool:
        summary = await self.session.get(BiomeSummary, summary_id)
        if not summary:
            return False

        await self.session.delete(summary)
        await self.session.commit()
        return True

    async def _gather_and_filter_species(
        self, summary: BiomeSummary, criteria: dict[str, Any]
    ) -> tuple[dict[str, int], dict[str, int], list[dict], list[dict]]:
        """
        Returns:
            confirmed_counts:   scientific_name -> detection count for species with >= 2 of 3 signals
            speculated_counts:  scientific_name -> detection count for species with exactly 1 signal
            confirmed_species:  filtered list for enrichment (confirmation=confirmed)
            speculated_species: filtered list for enrichment (confirmation=speculated)

        A species is confirmed when at least two of these are true:
        BirdNET saw it, Perch saw it, or the nearest iNat observation is within
        criteria.proximity.radius_miles of the site.
        """
        log.info("querying_detections", summary_id=str(summary.id), window_days=summary.window_days)
        cutoff = datetime.now(UTC) - timedelta(days=summary.window_days)

        # Per-species, per-model counts so we can score the three signals independently
        model_stmt = (
            select(  # type: ignore[call-overload]
                Detection.scientific_name,
                Detection.model,
                func.count().label("count"),  # type: ignore[arg-type]
            )
            .join(Recording, col(Detection.recording_id) == col(Recording.id))
            .join(Microphone, col(Recording.microphone_id) == col(Microphone.id))
            .where(col(Microphone.site_id) == summary.site_id)
            .where(col(Detection.created_at) >= cutoff)
            .group_by(Detection.scientific_name, Detection.model)
        )
        model_rows = (await self.session.execute(model_stmt)).all()

        birdnet_counts: dict[str, int] = {}
        perch_counts: dict[str, int] = {}
        for name, model, count in model_rows:
            if not name:
                continue
            n = int(count)
            if model == "perch":
                perch_counts[name] = n
            else:
                birdnet_counts[name] = birdnet_counts.get(name, 0) + n

        # Proximity signal: nearest iNat observation for this site
        prox_rows = (
            (
                await self.session.execute(
                    select(SpeciesSiteProximity).where(col(SpeciesSiteProximity.site_id) == summary.site_id)
                )
            )
            .scalars()
            .all()
        )
        proximity_miles: dict[str, float] = {
            r.scientific_name: r.distance_miles for r in prox_rows if r.distance_miles is not None
        }

        radius_miles = float((criteria.get("proximity") or {}).get("radius_miles", 100))
        far_miles = float((criteria.get("proximity") or {}).get("far_miles", 500))
        min_signals = int((criteria.get("confirmation") or {}).get("min_signals", 2))
        prior_days = int((criteria.get("expected") or {}).get("prior_days", 60))
        prior_min_count = int((criteria.get("expected") or {}).get("min_count", 50))

        confirmed_counts: dict[str, int] = {}
        speculated_counts: dict[str, int] = {}
        unexpected: set[str] = set()
        for name in set(birdnet_counts) | set(perch_counts):
            dist = proximity_miles.get(name)
            signals = confirmation_signal_count(
                has_birdnet=name in birdnet_counts,
                has_perch=name in perch_counts,
                distance_miles=dist,
                radius_miles=radius_miles,
                far_miles=far_miles,
            )
            total = birdnet_counts.get(name, 0) + perch_counts.get(name, 0)
            if is_confirmed_species(signals, min_signals):
                confirmed_counts[name] = total
            else:
                speculated_counts[name] = total
            if is_unexpected(name in birdnet_counts, name in perch_counts, dist, radius_miles, far_miles):
                unexpected.add(name)

        # Familiar residents: many detections in the window before this one,
        # and known from eBird/BirdNET as recorded in Illinois.
        prior_end = cutoff
        prior_start = cutoff - timedelta(days=prior_days)
        prior_stmt = (
            select(Detection.scientific_name, func.count().label("n"))  # type: ignore[call-overload]
            .join(Recording, col(Detection.recording_id) == col(Recording.id))
            .join(Microphone, col(Recording.microphone_id) == col(Microphone.id))
            .where(col(Microphone.site_id) == summary.site_id)
            .where(col(Detection.created_at) >= prior_start)
            .where(col(Detection.created_at) < prior_end)
            .group_by(Detection.scientific_name)
        )
        prior_rows = (await self.session.execute(prior_stmt)).all()
        prior_counts = {name: int(n) for name, n in prior_rows if name and int(n) >= prior_min_count}

        if not confirmed_counts and not speculated_counts:
            log.info("no_detections", summary_id=str(summary.id))
            return {}, {}, [], []

        all_counts = {**speculated_counts, **confirmed_counts}  # confirmed overwrites if both
        max_count = max(all_counts.values())
        log.info(
            "detections_found",
            summary_id=str(summary.id),
            confirmed=len(confirmed_counts),
            speculated=len(speculated_counts),
            max_count=max_count,
        )

        # Get species context from Neo4j (union of names)
        species_contexts: dict[str, dict] = {}
        if self.species_service is not None:
            for name in set(confirmed_counts) | set(speculated_counts):
                context = self.species_service.get_species_by_scientific_name(name)
                if context:
                    species_contexts[name] = context

        confirmed_species, speculated_species = filter_species(
            confirmed_counts,
            speculated_counts,
            species_contexts,
            criteria,
            neo4j_driver=self.neo4j_driver,
        )

        # Tag unexpected (far iNat + both models) and familiar residents
        # (many detections in the prior window, and eBird says Illinois).
        for sp in confirmed_species + speculated_species:
            name = sp["scientific_name"]
            sp["unexpected"] = name in unexpected
            ctx = species_contexts.get(name) or {}
            illinois = ctx.get("recorded_in_illinois")
            sp["expected_here"] = name in prior_counts and illinois is True
            if sp["expected_here"]:
                sp["prior_count"] = prior_counts[name]

        log.info(
            "filtering_complete",
            summary_id=str(summary.id),
            confirmed_after=len(confirmed_species),
            confirmed_before=len(confirmed_counts),
            speculated_after=len(speculated_species),
            speculated_before=len(speculated_counts),
        )

        return confirmed_counts, speculated_counts, confirmed_species, speculated_species

    async def _enrich_species(self, summary_id: UUID, filtered_species: list[dict], window_days: int) -> list[dict]:
        return await enrich_species(
            summary_id,
            filtered_species,
            window_days,
            self.retriever,
            self.chunks_per_species,
            chain=self._build_species_enrichment_chain(),
        )

    async def export_to_docx(self, summary: dict) -> Path:
        """Delegate to the export module. Kept on the service for router compatibility."""
        return export_to_docx_fn(summary)

    async def _generate_narratives(
        self,
        summary_id: UUID,
        confirmed_counts: dict[str, int],
        enriched_confirmed_species: list[dict],
        speculated_counts: dict[str, int],
        enriched_speculated_species: list[dict],
        window_days: int,
        criteria: dict[str, Any],
    ) -> tuple[str, str, list[dict[str, Any]], list[Any]]:
        return await generate_narratives(
            summary_id,
            confirmed_counts,
            enriched_confirmed_species,
            speculated_counts,
            enriched_speculated_species,
            window_days,
            criteria,
            neo4j_driver=self.neo4j_driver,
            machine_chain=self._build_narrative_chain(),
            human_chain=self._build_human_narrative_chain(),
        )

    async def build_grok_data_package(self, summary_id: UUID) -> str | None:
        """
        Build a clean, paste-ready markdown package of the summary data
        for use with a stronger external model (Grok, etc.).
        """
        summary = await self.session.get(BiomeSummary, summary_id)
        if not summary or summary.status != "completed":
            return None

        table: list[dict] = summary.species_table or []
        if not table:
            return "No species table available for this summary."

        # Re-derive the useful buckets from the stored table
        by_score = sorted(table, key=lambda x: x.get("score", 0), reverse=True)
        by_count = sorted(table, key=lambda x: x.get("count", 0), reverse=True)

        dominant = by_count[:8]
        high_interest = [s for s in by_score if s.get("score", 0) >= 12][:10]
        rare = [s for s in by_score if s.get("count", 0) <= 4 and s.get("score", 0) >= 10][:8]

        def fmt(rows: list[dict]) -> str:
            if not rows:
                return "_None_"
            lines = []
            for r in rows:
                common = r.get("common_name") or "—"
                sci = r.get("scientific_name", "")
                count = r.get("count", "?")
                score = r.get("score", "?")
                lines.append(f"- {common} (*{sci}*): {count} detections (score {score})")
            return "\n".join(lines)

        package = f"""# Biome Summary Data Package
    Site ID: {summary.site_id}
    Window: last {summary.window_days} days
    Generated: {summary.created_at.isoformat() if summary.created_at else "unknown"}
    Total species with >1 detection: {len(table)}

    ## Dominant / Most Frequent Species
    {fmt(dominant)}

    ## High-Interest & Indicator Species
    {fmt(high_interest)}

    ## Rare / Unexpected Species
    {fmt(rare)}

    ## Full Species Table (count > 1)
    | Common Name | Scientific Name | Detections | Score |
    |-------------|-----------------|------------|-------|
    """
        for r in by_count:
            common = r.get("common_name") or "—"
            sci = r.get("scientific_name", "")
            package += f"| {common} | {sci} | {r.get('count', '')} | {r.get('score', '')} |\n"

        package += """
    ---
    Instructions for the model:
    You are an experienced field naturalist and ecologist. Using only the data above, write a clear, engaging, 
    well-structured markdown report for a homeowner / land steward in the Chicago suburbs / prairie restoration 
    context. Balance the common soundscape with high-interest, indicator, raptor/owl, and rare species. Use 
    both common and scientific names. Aim for 700-1000 words.
    """
        return package

    async def update_grok_narrative(self, summary_id: UUID, text: str) -> bool:
        summary = await self.session.get(BiomeSummary, summary_id)
        if not summary:
            return False

        summary.grok_narrative = text
        self.session.add(summary)
        await self.session.commit()
        return True

    async def backfill_images(self, summary_id: UUID) -> dict | None:
        """Delegate to the export module."""
        return await export_backfill_images(self.session, summary_id)
