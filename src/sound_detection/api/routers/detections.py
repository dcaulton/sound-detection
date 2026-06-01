"""FastAPI router for audio detection endpoints."""

from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

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
            await repo.save_detections(recording_id, [d.model_dump() for d in result.detections])

        log.info("Background analysis complete and saved", recording_id=recording_id, detections=len(result.detections))
    except Exception:
        log.exception("Background analysis failed", recording_id=recording_id)


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
    recording = Recording(
        microphone_id=metadata.mic_id or uuid4(),
        filename=file.filename,
        file_path=f"/tmp/{file.filename}",
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
