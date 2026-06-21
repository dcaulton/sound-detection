import logging
import os
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.db.models import BiomeSummary
from sound_detection.knowledge.rag.retriever import Retriever

log = logging.getLogger(__name__)
log.setLevel(os.getenv("LOG_LEVEL", "INFO"))


class BiomeSummaryService:
    def __init__(self, session: AsyncSession, retriever: Retriever | None = None) -> None:
        self.session = session
        self.retriever = retriever
        self.chunks_per_species: int = 10

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
        """
        Long-running method. Updates the DB record through its lifecycle.
        Logs progress verbosely (7/10 chattiness).
        """
        summary = await self.session.get(BiomeSummary, summary_id)
        if not summary:
            return

        try:
            summary.status = "processing"
            await self.session.commit()

            log.info(f"Starting biome summary generation for job {summary_id}")

            # === Phase 1: Data Gathering & Filtering ===
            log.info(f"[{summary_id}] Phase 1: Gathering detections and filtering species...")

            # === Phase 2: Per-Species Enrichment (RAG + LLM) ===
            log.info(f"[{summary_id}] Phase 2: Enriching notable species with RAG data...")

            # === Phase 3: Narrative Generation ===
            log.info(f"[{summary_id}] Phase 3: Generating narrative...")

            # TODO: Implement actual logic here

            summary.status = "completed"
            log.info(f"[{summary_id}] Summary generation completed successfully.")

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
            "narrative": summary.narrative,
            "error_message": summary.error_message,
        }

    async def delete_summary(self, summary_id: UUID) -> bool:
        summary = await self.session.get(BiomeSummary, summary_id)
        if not summary:
            return False

        await self.session.delete(summary)
        await self.session.commit()
        return True
