import logging
import os
import tempfile
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID

import requests
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_ollama import ChatOllama
from neo4j import Driver
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.db.models import BiomeSummary, Detection, Microphone, Recording
from sound_detection.knowledge.rag.retriever import Retriever
from sound_detection.knowledge.species_knowledge_service import SpeciesKnowledgeService

log = logging.getLogger(__name__)
log.setLevel(os.getenv("LOG_LEVEL", "INFO"))

llm = ChatOllama(model="qwen2.5:32b", temperature=0.3)

NON_SPECIES_LABELS = {
    "power tools",
    "fireworks",
    "engine",
    "human vocal",
    "gun",
    "siren",
    "dog",
    "cat",
    "vehicle",
    "airplane",
    "helicopter",
    "chainsaw",
    "lawn mower",
    "human non-vocal",
    # add more as we discover them
}

SPECIES_GROUPS = {
    # Owls
    "bubo": "owl",
    "strix": "owl",
    "megascops": "owl",
    "asio": "owl",
    "aegolius": "owl",
    "otus": "owl",
    "tyto": "owl",
    "surnia": "owl",
    # Raptors (hawks, eagles, falcons, kites, etc.)
    "buteo": "raptor",
    "accipiter": "raptor",
    "haliaeetus": "raptor",
    "circus": "raptor",
    "pandion": "raptor",
    "falco": "raptor",
    "aquila": "raptor",
    "elanus": "raptor",
    "ictinia": "raptor",
    "cathartes": "raptor",  # Turkey Vulture
    "coragyps": "raptor",  # Black Vulture
    # Hummingbirds
    "archilochus": "hummingbird",
    "selasphorus": "hummingbird",
    "calypte": "hummingbird",
    "amazilia": "hummingbird",
    "cynanthus": "hummingbird",
}


def get_species_image(scientific_name: str) -> str | None:
    """
    Try to get a representative image URL for a species.
    Uses Wikipedia first (simple and reliable).
    """
    try:
        # Wikipedia API - get page summary which includes a thumbnail
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{scientific_name.replace(' ', '_')}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            thumbnail = data.get("thumbnail", {}).get("source")
            if thumbnail:
                return str(thumbnail)
    except Exception:
        pass
    return None


def get_species_group(scientific_name: str) -> str | None:
    """Return the group (owl / raptor / hummingbird) or None."""
    if not scientific_name:
        return None
    genus = scientific_name.split()[0].lower()
    return SPECIES_GROUPS.get(genus)


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

    async def create_summary_job(self, site_id: UUID, window_days: int = 30) -> UUID:
        """Creates a pending summary job and returns the ID immediately."""
        summary = BiomeSummary(
            site_id=site_id,
            window_days=window_days,
            status="pending",
        )
        self.session.add(summary)
        await self.session.commit()
        await self.session.refresh(summary)

        log.info(f"Created biome summary job {summary.id} for site {site_id}")
        return summary.id

    async def generate_summary(self, summary_id: UUID) -> None:
        summary = await self.session.get(BiomeSummary, summary_id)
        if not summary:
            log.warning(f"Summary {summary_id} not found")
            return

        start_time = datetime.now(UTC)
        log.info(f"[{summary_id}] Starting biome summary generation (window: {summary.window_days} days)")

        try:
            summary.status = "processing"
            await self.session.commit()

            # === Phase 1: Data Gathering & Filtering ===
            log.info(f"[{summary_id}] Phase 1: Gathering detections and filtering species...")
            phase_start = datetime.now(UTC)
            species_counts, filtered_species = await self._gather_and_filter_species(summary)
            log.info(f"[{summary_id}] Phase 1 completed in {(datetime.now(UTC) - phase_start).seconds}s")

            # === Phase 2: Per-Species Enrichment ===
            log.info(f"[{summary_id}] Phase 2: Enriching {len(filtered_species)} notable species with RAG + LLM...")
            phase_start = datetime.now(UTC)
            enriched_species = await self._enrich_species(summary_id, filtered_species, summary.window_days)
            log.info(f"[{summary_id}] Phase 2 completed in {(datetime.now(UTC) - phase_start).seconds}s")

            # === Phase 3: Narrative Generation ===
            log.info(f"[{summary_id}] Phase 3: Generating final narrative...")
            phase_start = datetime.now(UTC)
            machine_narrative, human_narrative, images = await self._generate_narratives(
                summary_id, species_counts, enriched_species, summary.window_days
            )
            summary.narrative = machine_narrative
            summary.human_narrative = human_narrative
            summary.notable_species_images = images
            log.info(f"[{summary_id}] Phase 3 completed in {(datetime.now(UTC) - phase_start).seconds}s")

            # Save final results
            summary.summary_json = {
                "window_days": summary.window_days,
                "total_detections": sum(species_counts.values()),
                "total_species": len(species_counts),
                "species_counts": species_counts,
                "notable_species": enriched_species,
                "generated_at": datetime.now(UTC).isoformat(),
            }
            summary.status = "completed"

            duration = (datetime.now(UTC) - start_time).seconds
            log.info(f"[{summary_id}] Summary generation completed successfully in {duration}s")

        except Exception as e:
            summary.status = "failed"
            summary.error_message = str(e)
            log.exception(f"[{summary_id}] Summary generation failed")
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

    async def _gather_and_filter_species(self, summary: BiomeSummary) -> tuple[dict[str, int], list[dict]]:
        log.info(f"[{summary.id}] Querying detections from last {summary.window_days} days...")

        cutoff = datetime.now(UTC) - timedelta(days=summary.window_days)

        stmt = (
            select(  # type: ignore[call-overload]
                Detection.scientific_name,
                func.count().label("count"),  # type: ignore[arg-type]
            )  # type: ignore[arg-type]
            .join(Recording, Detection.recording_id == Recording.id)
            .join(Microphone, Recording.microphone_id == Microphone.id)
            .where(Microphone.site_id == summary.site_id)
            .where(Detection.created_at >= cutoff)
            .group_by(Detection.scientific_name)
            .order_by(func.count().desc())  # type: ignore[arg-type]
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        # Build counts with explicit int() to satisfy mypy
        species_counts: dict[str, int] = {}
        for row in rows:
            species_counts[row.scientific_name] = int(row.count)  # type: ignore[call-overload]

        if not species_counts:
            log.info(f"[{summary.id}] No detections found in window.")
            return {}, []

        max_count = max(species_counts.values())
        log.info(f"[{summary.id}] Found {len(species_counts)} species. Max count = {max_count}")

        # Get species context from Neo4j
        species_contexts: dict[str, dict] = {}
        if self.species_service is not None:
            for name in species_counts:
                context = self.species_service.get_species_by_scientific_name(name)
                if context:
                    species_contexts[name] = context

        # Apply sliding-scale filtering
        filtered_species: list[dict] = []
        for name, count in species_counts.items():
            name_lower = name.lower().strip()

            # 1. Skip known non-species labels
            if name_lower in NON_SPECIES_LABELS:
                continue

            # 2. Skip single-observation detections (likely false positives)
            if count <= 1:
                continue

            # 3. Optional: require it to look roughly like a scientific name
            # (contains a space and starts with a capital letter)
            if " " not in name or not name[0].isupper():
                continue

            context = species_contexts.get(name, {})
            # this is a little too agressive for now, and messes up multitenancy.
            # TODO: have a user or site setting drive this later
            # recorded_in_illinois = context.get("recorded_in_illinois", False)
            # if not recorded_in_illinois:
            #     continue

            filtered_species.append(
                {
                    "scientific_name": name,
                    "count": count,
                    "context": context,
                }
            )

        log.info(
            f"[{summary.id}] After filtering: {len(filtered_species)} species kept "
            f"(discarded {len(species_counts) - len(filtered_species)})"
        )

        return species_counts, filtered_species

    def _build_species_enrichment_chain(self) -> Runnable:
        prompt = ChatPromptTemplate.from_template(
            """You are an expert ornithologist and ecologist analyzing bird observations.

    Species: {scientific_name} ({common_name})
    Detection count in the last {window_days} days: {count}

    Structured knowledge:
    - Recorded in Illinois: {recorded_in_illinois}
    - Primary habitat: {primary_habitat}
    - Diet: {diet_description}
    - Interesting facts: {interesting_facts}

    Relevant context from Wikipedia:
    {chunks_text}

    Task:
    Write a concise but insightful paragraph (3-6 sentences) that explains:
    - Why this species might be notable or unusual in this location right now
    - Any relevant seasonal, migratory, or ecological context
    - Interesting biological or behavioral details worth mentioning

    Be factual and avoid speculation. If the species is common and expected, say so briefly.
    """
        )

        chain = prompt | llm | StrOutputParser()
        return chain

    async def _enrich_species(self, summary_id: UUID, filtered_species: list[dict], window_days: int) -> list[dict]:
        if not self.retriever:
            log.warning(f"[{summary_id}] No retriever available - skipping RAG step")
            return filtered_species

        log.info(f"[{summary_id}] Enriching {len(filtered_species)} species using LangChain + RAG...")

        chain = self._build_species_enrichment_chain()
        enriched = []

        for species in filtered_species:
            name = species["scientific_name"]
            count = species["count"]
            context = species.get("context", {})

            log.info(f"[{summary_id}] → Enriching {name} ({count} detections)")

            # Get top relevant chunks
            chunks = self.retriever.retrieve(name, top_k=self.chunks_per_species)

            # Format chunks for the prompt
            chunks_text = (
                "\n\n".join(f"- {chunk.get('text', '')[:800]}" for chunk in chunks[:5])
                if chunks
                else "No additional context available."
            )

            try:
                insight = await chain.ainvoke(
                    {
                        "scientific_name": name,
                        "common_name": context.get("common_name", name),
                        "window_days": window_days,
                        "count": count,
                        "recorded_in_illinois": context.get("recorded_in_illinois", False),
                        "primary_habitat": context.get("primary_habitat", "Unknown"),
                        "diet_description": context.get("diet_description", "Unknown"),
                        "interesting_facts": context.get("interesting_facts", "None available"),
                        "chunks_text": chunks_text,
                    }
                )

                enriched.append(
                    {
                        **species,
                        "chunks": chunks,
                        "llm_insight": insight.strip(),
                    }
                )

            except Exception as e:
                log.warning(f"[{summary_id}] LLM enrichment failed for {name}: {e}")
                enriched.append(
                    {
                        **species,
                        "chunks": chunks,
                        "llm_insight": None,
                    }
                )

        log.info(f"[{summary_id}] Finished enriching {len(enriched)} species with LangChain")
        return enriched

    def _build_narrative_chain(self) -> Runnable:
        prompt = ChatPromptTemplate.from_template(
            """You are an experienced field ecologist and naturalist writing a detailed monthly biome 
               report for a specific location (a yard or small site in Illinois).

    **Report Context**
    - Time window: Last {window_days} days
    - Total species detected: {total_species}
    - Top species by detection count: {top_species}

    **Notable / Enriched Species**
    {notable_species_text}

    **Task**
    Write a rich, engaging narrative report (minimum 1000 words) with the following structure:

    1. **Overall Summary** - Give a high-level overview of bird activity during this period. 
       How does it compare to what one might expect?

    2. **Seasonal & Ecological Context** - Discuss any species that appear to be at peak numbers 
       for understandable reasons (migration timing, breeding season, food availability, etc.).

    3. **Notable & Unusual Sightings** - Highlight species that are uncommon or surprising for 
       this location. Use the enriched information provided. Explain why they might be here and 
       what makes them interesting.

    4. **Ecological Insights** - Weave in relevant details from the species data (diet, habitat, 
       behavior, interesting facts).  Connect observations to broader ecological patterns where 
       appropriate.

    5. **Reflections & Closing** - End with thoughtful observations or questions the data raises.

    Write in a natural, knowledgeable tone - like a field report written by someone who knows 
    the local avifauna well. 
    Be specific and use the provided data. Avoid generic statements.

    Narrative:"""
        )

        chain = prompt | llm | StrOutputParser()
        return chain

    async def _generate_narrative(
        self,
        summary_id: UUID,
        species_counts: dict[str, int],
        enriched_species: list[dict],
        window_days: int,
    ) -> str:
        log.info(f"[{summary_id}] Generating long-form narrative...")

        # Prepare top species list
        sorted_species = sorted(species_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_species_text = ", ".join(f"{name} ({count})" for name, count in sorted_species)

        # Prepare notable species section
        notable_text_parts = []
        for sp in enriched_species:
            name = sp["scientific_name"]
            count = sp["count"]
            insight = sp.get("llm_insight") or "No additional insight generated."
            notable_text_parts.append(f"**{name}** ({count} detections):\n{insight}")

        notable_species_text = "\n\n".join(notable_text_parts)

        chain = self._build_narrative_chain()

        log.info(f"[{summary_id}] Sending narrative generation request to LLM...")
        narrative: str = await chain.ainvoke(
            {
                "window_days": window_days,
                "total_species": len(species_counts),
                "top_species": top_species_text,
                "notable_species_text": notable_species_text,
            }
        )

        log.info(f"[{summary_id}] Narrative generated ({len(narrative)} characters)")
        return narrative.strip()

    async def export_to_docx(self, summary: dict) -> Path:
        """
        Generate a nicely formatted Word document from a completed summary.
        Returns the path to a temporary .docx file.
        """
        doc = Document()

        # ---------- Title ----------
        title = doc.add_heading("Biome Summary Report", level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # ---------- Metadata ----------
        meta = doc.add_paragraph()
        meta.add_run("Site ID: ").bold = True
        meta.add_run(str(summary.get("site_id", "Unknown")))
        meta.add_run("\n")
        meta.add_run("Window: ").bold = True
        meta.add_run(f"Last {summary.get('window_days', '?')} days")
        meta.add_run("\n")
        meta.add_run("Generated: ").bold = True
        created = summary.get("created_at", "")
        meta.add_run(created[:19].replace("T", " ") if created else "Unknown")

        doc.add_paragraph()  # spacer

        # ---------- Human Narrative ----------
        doc.add_heading("Summary", level=1)

        human_narrative = summary.get("human_narrative") or summary.get("narrative") or "No narrative available."

        # Simple paragraph splitting (works well enough for markdown-ish text)
        for block in human_narrative.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            if block.startswith("#"):
                # Treat as a heading
                level = min(block.count("#"), 3)
                text = block.lstrip("# ").strip()
                doc.add_heading(text, level=level)
            else:
                doc.add_paragraph(block)

        # ---------- Notable Species with Images ----------
        images = summary.get("notable_species_images") or []
        if images:
            doc.add_heading("Notable Species", level=1)

            for item in images:
                name = item.get("scientific_name", "Unknown")
                common = item.get("common_name") or ""
                count = item.get("count", "?")
                image_url = item.get("image_url")

                # Caption
                caption = f"{common} ({name})" if common else name
                caption += f"  —  {count} detections"
                doc.add_heading(caption, level=2)

                # Try to embed the image
                if image_url:
                    try:
                        resp = requests.get(image_url, timeout=8)
                        if resp.status_code == 200:
                            image_stream = BytesIO(resp.content)
                            doc.add_picture(image_stream, width=Inches(3.5))
                            last_paragraph = doc.paragraphs[-1]
                            last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    except Exception as e:
                        doc.add_paragraph(f"[Could not load image: {e}]")

                doc.add_paragraph()  # spacer between species

        # ---------- Footer ----------
        doc.add_paragraph()
        footer = doc.add_paragraph("Generated by sound-detection")
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer.runs[0].font.size = Pt(9)
        footer.runs[0].font.color.rgb = RGBColor(120, 120, 120)

        # Save to a temporary file
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()

        return Path(tmp.name)

    async def _generate_narratives(
        self,
        summary_id: UUID,
        species_counts: dict[str, int],
        enriched_species: list[dict],
        window_days: int,
    ) -> tuple[str, str, list[dict]]:
        log.info(f"[{summary_id}] Generating narratives...")

        # ----- Group analysis (owls, raptors, hummingbirds) -----
        group_counts = defaultdict(list)
        for name, count in species_counts.items():
            group = get_species_group(name)
            if group:
                group_counts[group].append((name, count))

        group_summary_parts = []
        if group_counts.get("owl"):
            owls = group_counts["owl"]
            group_summary_parts.append(f"Owls: {len(owls)} species detected ({', '.join(n for n, _ in owls)})")
        if group_counts.get("raptor"):
            raptors = group_counts["raptor"]
            group_summary_parts.append(f"Raptors: {len(raptors)} species detected ({', '.join(n for n, _ in raptors)})")
        if group_counts.get("hummingbird"):
            hummers = group_counts["hummingbird"]
            group_summary_parts.append(
                f"Hummingbirds: {len(hummers)} species detected ({', '.join(n for n, _ in hummers)})"
            )

        group_highlight = (
            "\n".join(group_summary_parts)
            if group_summary_parts
            else "No major raptor, owl, or hummingbird diversity noted."
        )

        # ----- Shared context -----
        sorted_species = sorted(species_counts.items(), key=lambda x: x[1], reverse=True)
        top_species_text = ", ".join(f"{name} ({count})" for name, count in sorted_species[:10])

        notable_text_parts = []
        for sp in enriched_species:
            name = sp["scientific_name"]
            count = sp["count"]
            insight = sp.get("llm_insight") or "No additional insight."
            notable_text_parts.append(f"**{name}** ({count} detections):\n{insight}")

        notable_species_text = "\n\n".join(notable_text_parts)

        # Common variables for both prompts
        prompt_vars = {
            "window_days": window_days,
            "total_species": len(species_counts),
            "top_species": top_species_text,
            "notable_species_text": notable_species_text,
            "group_highlight": group_highlight,
        }

        # ----- Machine / Weathervane narrative -----
        machine_chain = self._build_narrative_chain()
        machine_narrative = await machine_chain.ainvoke(prompt_vars)

        # ----- Human-readable narrative -----
        human_prompt = ChatPromptTemplate.from_template(
            """You are an experienced field naturalist writing a clear, engaging summary for a 
               homeowner or land steward.

    Write a well-structured markdown report (use headings, bullet points, and short paragraphs).

    **Important instructions:**
    - Start with the overall picture of bird activity (including the most frequently detected species).
    - Explicitly comment on any notable diversity in raptors, owls, or hummingbirds when present.
    - Balance discussion of rare/unusual species with the common and dominant ones.
    - Mention ecological significance where relevant (habitat quality, predator presence, seasonal patterns, etc.).
    - Keep the tone knowledgeable but accessible. Aim for 600 to 900 words.

    **Data**
    Time window: last {window_days} days
    Total species detected: {total_species}
    Most frequently detected species: {top_species}

    Notable / enriched species details:
    {notable_species_text}

    **Special Groups Detected**
    {group_highlight}

    Human-readable report:"""
        )

        human_chain = human_prompt | llm | StrOutputParser()
        human_narrative = await human_chain.ainvoke(prompt_vars)

        # ----- Images for top notable species -----
        notable_species_images = []
        for sp in enriched_species[:5]:
            name = sp["scientific_name"]
            image_url = get_species_image(name)
            if image_url:
                notable_species_images.append(
                    {
                        "scientific_name": name,
                        "common_name": sp.get("context", {}).get("common_name"),
                        "count": sp["count"],
                        "image_url": image_url,
                    }
                )

        return machine_narrative.strip(), human_narrative.strip(), notable_species_images
