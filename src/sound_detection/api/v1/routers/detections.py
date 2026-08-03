"""FastAPI router for audio detection endpoints."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import func, select

from sound_detection.core.concurrency import analysis_semaphore
from sound_detection.db.models import Detection, Microphone, Recording
from sound_detection.db.neo4j import get_neo4j_driver
from sound_detection.db.repositories import RecordingRepository
from sound_detection.db.session import AsyncSessionLocal, get_db
from sound_detection.knowledge.seed_or_update import SeedOrUpdate
from sound_detection.ml.inference import analyze_with_birdnet
from sound_detection.ml.perch_inference import analyze_with_perch
from sound_detection.schemas.detection import AnalyzeAudioRequest
from sound_detection.schemas.detection import Detection as SchemaDetection
from sound_detection.utils.datetime import parse_recording_datetime_from_filename

log = structlog.get_logger()
router = APIRouter(prefix="/detections", tags=["detections"])
db_dep = Depends(get_db)


async def background_analyze(
    recording_id: UUID, audio_bytes: bytes, filename: str, session: AsyncSession | None = None
) -> None:
    async with analysis_semaphore:
        try:
            log.info("Acquired analysis semaphore", recording_id=recording_id)

            perch_response = await asyncio.to_thread(analyze_with_perch, audio_bytes=audio_bytes, filename=filename)
            log.info("Perch analysis complete", detections_found=len(perch_response.detections))
            perch_dets = perch_response.detections
            perch_dets = coalesce_adjacent(perch_dets)

            birdnet_response = await asyncio.to_thread(analyze_with_birdnet, audio_bytes=audio_bytes, filename=filename)
            log.info("Birdnet analysis complete", detections_found=len(birdnet_response.detections))
            birdnet_dets = birdnet_response.detections
            birdnet_dets = coalesce_adjacent(birdnet_dets)

            all_dets = coalesce_across_models(birdnet_dets + perch_dets)

            close_session = False
            if session is None:
                session = AsyncSessionLocal()
                close_session = True
            repo = RecordingRepository(session)

            await repo.save_detections(recording_id=recording_id, detections=all_dets)

            # Update recording
            recording = await session.get(Recording, recording_id)

            if recording:
                recording.status = "completed"
                recording.duration_seconds = getattr(birdnet_response, "file_duration", None)
                session.add(recording)

            if close_session:
                await session.commit()
                await session.close()

            log.info("Recording updated to complete")

            # Trigger knowledge enrichment once per new species
            unique_species = {d.scientific_name for d in birdnet_response.detections}
            unique_species |= {d.scientific_name for d in perch_response.detections}
            for species in unique_species:
                try:
                    seed = SeedOrUpdate(get_neo4j_driver())
                    seed.seed_or_update(species)
                except Exception:
                    log.exception(f"Failed to seed knowledge for species: {species}")

            log.warning("Background analysis complete and saved", recording_id=recording_id)

        except Exception:
            log.exception("Background analysis failed", recording_id=recording_id)


@router.get("/recordings")
async def list_recordings(db: AsyncSession = Depends(get_db), limit: int = Query(50, le=100)) -> list[dict]:  # noqa: B008
    """List recent recordings."""
    # TODO move this to the repository
    result = await db.execute(
        select(Recording)
        .options(selectinload(Recording.detections))  # type: ignore[arg-type]
        .order_by(desc(Recording.uploaded_at))  # type: ignore[arg-type]
        .limit(limit)
    )
    recordings = result.all()
    return [
        {
            "id": str(r.Recording.id),
            "filename": r.Recording.filename,
            "status": r.Recording.status,
            "uploaded_at": r.Recording.uploaded_at.isoformat() if r.Recording.uploaded_at else None,
            "detections_count": len(r.Recording.detections) if hasattr(r.Recording, "detections") else 0,
            "microphone_id": r.Recording.microphone_id,
        }
        for r in recordings
    ]


@router.get("/recordings/{recording_id}")
async def get_recording(recording_id: UUID, db: AsyncSession = db_dep) -> dict:
    """Get a recording with its detections."""
    repo = RecordingRepository(db)
    r = await repo.get(recording_id)
    if not r:
        raise HTTPException(404, "Recording not found")
    return {
        "id": str(r.id),
        "filename": r.filename,
        "status": r.status,
        "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
        "detections_count": len(r.detections) if hasattr(r, "detections") else 0,
        "detections": [
            {
                "species": d.species,
                "common_name": d.common_name,
                "confidence": d.confidence,
                "start_time": d.start_time,
                "end_time": d.end_time,
                "start_offset": d.start_offset,
                "end_offset": d.end_offset,
                "model": d.model,
                "confirmed_group_id": d.confirmed_group_id,
            }
            for d in getattr(r, "detections", [])
        ],
        "microphone_id": r.microphone_id,
    }


@router.post("/analyze", status_code=202)
async def analyze_audio_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),  # noqa: B008
    metadata: AnalyzeAudioRequest = Depends(),  # noqa: B008
    db: AsyncSession = db_dep,
) -> dict:
    """Upload audio → returns immediately, processing happens in background."""
    if not file.filename or not file.filename.lower().endswith((".wav", ".mp3", ".flac")):
        raise HTTPException(400, "Only WAV, MP3, or FLAC files are supported")

    content = await file.read()
    repo = RecordingRepository(db)

    # Get or create a microphone if none was specified
    if not metadata.mic_id:
        default_mic = await repo.get_or_create_default_microphone()
        mic_id: UUID = default_mic.id
    else:
        mic_id = metadata.mic_id  # type: ignore[assignment]

    # Parse recorded_at from filename using the microphone's timezone ===
    mic = await db.get(Microphone, mic_id)
    tz_name = mic.site.timezone if mic and mic.site else "UTC"

    recorded_at = parse_recording_datetime_from_filename(filename=file.filename, timezone=tz_name) or datetime.now(
        UTC
    )  # fallback to upload time
    log.debug(f"recorded at time is {recorded_at}")

    recording = Recording(
        microphone_id=mic_id,
        filename=file.filename,
        file_path=f"/tmp/{file.filename}",
        recorded_at=recorded_at,
        status="pending",
    )
    recording = await repo.create(recording)

    background_tasks.add_task(background_analyze, recording.id, content, file.filename)

    log.info("Upload accepted for background processing", recording_id=recording.id)

    return {
        "message": "Processing started",
        "recording_id": str(recording.id),
        "status": "pending",
    }


@router.get("/analytics/species-counts")
async def get_species_counts(days: int = 7, db: AsyncSession = db_dep) -> list[dict]:
    """Return count of each species detected in the last N days."""
    since = datetime.utcnow() - timedelta(days=days)

    stmt = (
        select(Detection.scientific_name, Detection.common_name, func.count().label("count"))
        .join(Recording)
        .where(Recording.uploaded_at >= since)
        .group_by(Detection.scientific_name, Detection.common_name)
        .order_by(func.count().desc())
    )

    result = await db.execute(stmt)
    return [
        {
            "scientific_name": row.scientific_name,
            "common_name": row.common_name,
            "count": row.count,
        }
        for row in result.all()
    ]


def _norm_species(d: SchemaDetection) -> str:
    name = getattr(d, "scientific_name", None) or getattr(d, "species", None) or ""
    return str(name).strip().lower()


def _linked(a_start: float, a_end: float, b_start: float, b_end: float, max_gap_s: float) -> bool:
    if a_start > b_start:
        a_start, a_end, b_start, b_end = b_start, b_end, a_start, a_end
    return (b_start - a_end) <= max_gap_s


def coalesce_adjacent(
    detections: list[SchemaDetection],
    *,
    max_gap_s: float = 0.35,
) -> list[SchemaDetection]:
    """
    Merge consecutive/overlapping detections of the same species from the
    same model into a single span (e.g. twelve 5s Perch windows → one row).
    """
    if not detections:
        return []

    # Bucket: (model, species) → list of detections
    buckets: dict[tuple[str, str], list[SchemaDetection]] = defaultdict(list)
    passthrough: list[SchemaDetection] = []

    for d in detections:
        species = _norm_species(d)
        model = (getattr(d, "model", None) or "unknown").lower()
        if not species:
            passthrough.append(d)
            continue
        buckets[(model, species)].append(d)

    merged: list[SchemaDetection] = []

    for (_model, _species), group in buckets.items():
        # Sort by start
        group = sorted(group, key=lambda d: float(d.start_offset))
        cluster: list[SchemaDetection] = [group[0]]

        def flush(cluster: list[SchemaDetection]) -> SchemaDetection:
            base = cluster[0]
            start = min(float(x.start_offset) for x in cluster)
            end = max(float(x.end_offset) for x in cluster)
            conf = max(float(x.confidence) for x in cluster)
            # Mutate a copy-like update on the schema object
            base.start_offset = start
            base.end_offset = end
            base.confidence = conf
            # If you also store absolute times, recompute from recording start elsewhere
            return base

        for d in group[1:]:
            if _linked(
                float(cluster[0].start_offset),  # cluster span start
                max(float(x.end_offset) for x in cluster),
                float(d.start_offset),
                float(d.end_offset),
                max_gap_s,
            ):
                cluster.append(d)
            else:
                merged.append(flush(cluster))
                cluster = [d]
        merged.append(flush(cluster))

    return passthrough + merged


def coalesce_across_models(
    detections: list[SchemaDetection],
    *,
    max_gap_s: float = 0.35,
) -> list[SchemaDetection]:
    """
    Assign confirmed_group_id when the same species from different models
    has overlapping/adjacent time ranges.
    """
    for d in detections:
        d.confirmed_group_id = None

    by_species: dict[str, list[SchemaDetection]] = defaultdict(list)
    for d in detections:
        key = _norm_species(d)
        if key:
            by_species[key].append(d)

    for group in by_species.values():
        n = len(group)
        if n < 2:
            continue
        parent = list(range(n))

        def find(i: int, p: list[int] = parent) -> int:
            while p[i] != i:
                p[i] = p[p[i]]
                i = p[i]
            return i

        def union(i: int, j: int, p: list[int] = parent) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                p[rj] = ri

        for i in range(n):
            for j in range(i + 1, n):
                if _linked(
                    float(group[i].start_offset),
                    float(group[i].end_offset),
                    float(group[j].start_offset),
                    float(group[j].end_offset),
                    max_gap_s,
                ):
                    union(i, j)

        components: dict[int, list[SchemaDetection]] = defaultdict(list)
        for i, d in enumerate(group):
            components[find(i)].append(d)

        for members in components.values():
            models = {(m.model or "unknown").lower() for m in members}
            if len(models) < 2:
                continue
            gid = uuid4()
            for d in members:
                d.confirmed_group_id = gid

    return detections
