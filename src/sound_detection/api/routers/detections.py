"""FastAPI router for audio detection endpoints."""

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from sound_detection.ml.inference import analyze_audio
from sound_detection.schemas.detection import AnalyzeAudioRequest, AnalyzeAudioResponse

log = structlog.get_logger()
router = APIRouter(prefix="/detections", tags=["detections"])


@router.post("/analyze", response_model=AnalyzeAudioResponse)
async def analyze_audio_file(
    file: UploadFile = File(...),  # noqa: B008
    metadata: AnalyzeAudioRequest = Depends(),  # noqa: B008
) -> AnalyzeAudioResponse:
    """Analyze uploaded audio file from a microphone and return wildlife detections."""
    if not file.filename or not file.filename.lower().endswith((".wav", ".mp3", ".flac")):
        raise HTTPException(400, "Only WAV, MP3, or FLAC files are supported")

    log.info("Received audio for analysis", filename=file.filename, size=file.size)

    content = await file.read()

    try:
        result = analyze_audio(
            audio_bytes=content,
            filename=file.filename,
            mic_id=metadata.mic_id,
            latitude=metadata.latitude,
            longitude=metadata.longitude,
            recording_date=metadata.recording_date,
        )
        log.info("Analysis complete", detections=len(result.detections))
        return result
    except Exception as e:
        log.exception("Analysis failed")
        raise HTTPException(500, f"Analysis failed: {e!s}") from e
