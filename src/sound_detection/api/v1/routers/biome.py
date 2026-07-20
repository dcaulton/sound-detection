from collections.abc import AsyncGenerator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.db.neo4j import get_neo4j_driver
from sound_detection.db.session import AsyncSessionLocal
from sound_detection.knowledge.biome_summary_service import BiomeSummaryService

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
        neo4j_driver = get_neo4j_driver()
        service = BiomeSummaryService(session, neo4j_driver)
        await service.generate_summary(summary_id)


@router.get("/summaries/{summary_id}/export")
async def export_summary(
    summary_id: UUID,
    service: Annotated[BiomeSummaryService, Depends(get_biome_service)],
    format: str = Query("docx", pattern="^(docx|pdf)$"),
) -> FileResponse:
    summary = await service.get_summary(summary_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    if summary["status"] != "completed":
        raise HTTPException(status_code=400, detail="Summary is not completed yet")

    if format == "docx":
        file_path = await service.export_to_docx(summary)
        return FileResponse(
            path=file_path,
            filename=f"biome_summary_{summary_id}.docx",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    else:
        raise HTTPException(status_code=501, detail="PDF export not implemented yet")


@router.get("/summaries/{summary_id}/grok-package", response_class=PlainTextResponse)
async def get_grok_data_package(
    summary_id: UUID,
    service: Annotated[BiomeSummaryService, Depends(get_biome_service)],
) -> str | None:
    package = await service.build_grok_data_package(summary_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Summary not found or not completed")
    return package


@router.put("/summaries/{summary_id}/grok-narrative", response_class=PlainTextResponse)
async def update_grok_narrative(
    summary_id: UUID,
    request: Request,
    service: Annotated[BiomeSummaryService, Depends(get_biome_service)],
) -> str:
    """
    Accept raw markdown/text and store it as the Grok narrative.
    Content-Type: text/plain
    """
    body = await request.body()
    text = body.decode("utf-8").strip()

    if not text:
        raise HTTPException(status_code=400, detail="Empty body")

    updated = await service.update_grok_narrative(summary_id, text)
    if not updated:
        raise HTTPException(status_code=404, detail="Summary not found")

    return "OK"


@router.post("/summaries/{summary_id}/backfill-images")
async def backfill_summary_images(
    summary_id: UUID,
    service: Annotated[BiomeSummaryService, Depends(get_biome_service)],
) -> dict | None:
    """
    Debug endpoint: re-fetch images for species in an existing summary
    and update notable_species_images.
    """
    result = await service.backfill_images(summary_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    return result
