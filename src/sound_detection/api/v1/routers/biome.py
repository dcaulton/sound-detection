from collections.abc import AsyncGenerator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.db.neo4j import get_neo4j_driver
from sound_detection.db.session import AsyncSessionLocal
from sound_detection.knowledge.biome_summary_service import BiomeSummaryService
from sound_detection.knowledge.rag.retriever import Retriever

router = APIRouter(prefix="/biome", tags=["biome"])


async def _get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def get_biome_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> BiomeSummaryService:
    return BiomeSummaryService(session)


dep_gbs = Depends(get_biome_service)


@router.post("/summary")
async def create_summary(
    site_id: Annotated[UUID, Query(...)],
    background_tasks: BackgroundTasks,
    service: Annotated[BiomeSummaryService, dep_gbs],
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    """Start a new biome summary job (returns immediately)."""
    summary_id = await service.create_summary_job(site_id=site_id, window_days=window_days)

    background_tasks.add_task(run_generate_summary, summary_id)

    return {
        "status": "started",
        "summary_id": str(summary_id),
        "message": "Summary generation started. Poll the status using GET /biome/summaries/{id}",
    }


@router.get("/summaries")
async def list_summaries(
    site_id: Annotated[UUID, Query(...)],
    service: Annotated[BiomeSummaryService, dep_gbs],
    limit: Annotated[int, Query(le=100)] = 20,
) -> list[dict]:
    return await service.list_summaries(site_id=site_id, limit=limit)


@router.get("/summaries/{summary_id}")
async def get_summary(
    summary_id: UUID,
    service: Annotated[BiomeSummaryService, dep_gbs],
) -> dict:
    summary = await service.get_summary(summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary


@router.delete("/summaries/{summary_id}")
async def delete_summary(
    summary_id: UUID,
    service: Annotated[BiomeSummaryService, dep_gbs],
) -> dict:
    deleted = await service.delete_summary(summary_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Summary not found")
    return {"status": "deleted", "summary_id": str(summary_id)}


async def run_generate_summary(summary_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        retriever = Retriever(get_neo4j_driver())
        service = BiomeSummaryService(session, retriever)
        await service.generate_summary(summary_id)
