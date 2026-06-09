from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.api.v1.routers.detections import background_analyze
from sound_detection.db.models import Detection, Recording
from sound_detection.db.repositories import RecordingRepository


@pytest.mark.asyncio
async def test_background_analyze_creates_recording_and_detections(
    async_session: AsyncSession,
) -> None:
    """
    Real end-to-end test using actual BirdNET on test_bird.mp3.
    Verifies Recording + Detection records are created correctly.
    """
    audio_path = Path("data/test_bird.mp3")
    audio_bytes = audio_path.read_bytes()
    filename = audio_path.name

    repo = RecordingRepository(async_session)
    mic = await repo.get_or_create_default_microphone()

    # Create a Recording (simulating the API layer)
    new_recording = Recording(
        microphone_id=mic.id,
        filename=filename,
        file_path=str(audio_path),
        status="pending",
        recorded_at=datetime.now(UTC),
    )
    async_session.add(new_recording)
    await async_session.commit()
    await async_session.refresh(new_recording)

    # Run the real background analysis (calls BirdNET)
    try:
        await background_analyze(
            recording_id=new_recording.id,
            audio_bytes=audio_bytes,
            filename=filename,
            session=async_session,
        )

    except Exception as e:
        print(">>> BACKGROUND_ANALYZE FAILED WITH:", e)
        raise

    # Force fresh read from DB (more reliable than refresh in this setup)
    rec_result = await async_session.execute(
        select(Recording).where(Recording.id == new_recording.id)  # type: ignore[arg-type]
    )
    updated_recording = rec_result.scalar_one()

    assert updated_recording.status == "completed"
    assert updated_recording.duration_seconds is not None and updated_recording.duration_seconds > 0

    # Detections
    det_result = await async_session.execute(
        select(Detection).where(Detection.recording_id == new_recording.id)  # type: ignore[arg-type]
    )
    detections = det_result.scalars().all()

    assert len(detections) > 0
    first = detections[0]
    assert first.species is not None
    assert first.confidence is not None
    assert first.start_time is not None
