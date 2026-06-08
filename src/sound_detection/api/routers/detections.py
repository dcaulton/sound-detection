"""FastAPI router for audio detection endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from sound_detection.db.models import Recording
from sound_detection.db.repositories import RecordingRepository
from sound_detection.db.session import AsyncSessionLocal, get_db
from sound_detection.ml.inference import analyze_audio
from sound_detection.schemas.detection import AnalyzeAudioRequest

log = structlog.get_logger()
router = APIRouter(prefix="/detections", tags=["detections"])


async def background_analyze(recording_id: UUID, audio_bytes: bytes, filename: str) -> None:
    try:
        result = analyze_audio(audio_bytes=audio_bytes, filename=filename)

        # Create fresh session for background task
        async with AsyncSessionLocal() as db:
            repo = RecordingRepository(db)
            repo.save_detections(recording_id, [d.model_dump() for d in result.detections])

        log.info("Background analysis complete and saved", recording_id=recording_id, detections=len(result.detections))
    except Exception:
        log.exception("Background analysis failed", recording_id=recording_id)


@router.get("/recordings")
async def list_recordings(db: AsyncSession = Depends(get_db), limit: int = Query(50, le=100)) -> list[dict]:  # noqa: B008
    """List recent recordings."""
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
            "detections": [
                {
                    "species": d.species,
                    "common_name": d.common_name,
                    "confidence": d.confidence,
                    "start_time": d.start_time,
                    "end_time": d.end_time,
                }
                for d in getattr(r.Recording, "detections", [])
            ],
        }
        for r in recordings
    ]


@router.get("/recordings/{recording_id}")
async def get_recording(recording_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:  # noqa: B008
    """Get a recording with its detections."""
    repo = RecordingRepository(db)
    recording = repo.get(recording_id)
    if not recording:
        raise HTTPException(404, "Recording not found")
    return {"id": str(recording.id), "status": recording.status}


@router.post("/analyze", status_code=202)
async def analyze_audio_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),  # noqa: B008
    metadata: AnalyzeAudioRequest = Depends(),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict:
    """Upload audio → returns immediately, processing happens in background."""
    if not file.filename or not file.filename.lower().endswith((".wav", ".mp3", ".flac")):
        raise HTTPException(400, "Only WAV, MP3, or FLAC files are supported")

    content = await file.read()
    repo = RecordingRepository(db)

    # Get or create a microphone if none was specified
    if not metadata.mic_id:
        default_mic = repo.get_or_create_default_microphone()
        mic_id: UUID = default_mic.id
    else:
        mic_id = metadata.mic_id  # type: ignore[assignment]

    recording = Recording(
        microphone_id=mic_id,
        filename=file.filename,
        file_path=f"/tmp/{file.filename}",
        status="pending",
    )
    recording = repo.create(recording)

    background_tasks.add_task(background_analyze, recording.id, content, file.filename)

    log.info("Upload accepted for background processing", recording_id=recording.id)

    return {
        "message": "Processing started",
        "recording_id": str(recording.id),
        "status": "pending",
    }
