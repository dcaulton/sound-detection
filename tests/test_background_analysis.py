import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.api.v1.routers.detections import background_analyze
from sound_detection.db.models import Detection, Recording
from sound_detection.db.repositories import RecordingRepository

FIXTURE = Path("data/test_bird.mp3")


@pytest.mark.asyncio
async def test_background_analyze_creates_recording_and_detections(
    async_session: AsyncSession,
) -> None:
    assert FIXTURE.is_file(), f"Missing fixture: {FIXTURE}"

    # Working copy — background_analyze may delete audio_path in finally
    work_dir = Path(tempfile.mkdtemp(prefix="sd_test_"))
    work_path = work_dir / FIXTURE.name
    shutil.copy(FIXTURE, work_path)

    try:
        repo = RecordingRepository(async_session)
        mic = await repo.get_or_create_default_microphone()

        new_recording = Recording(
            microphone_id=mic.id,
            filename=FIXTURE.name,
            file_path=str(work_path),
            status="pending",
            recorded_at=datetime.now(UTC),
        )
        async_session.add(new_recording)
        await async_session.commit()
        await async_session.refresh(new_recording)

        await background_analyze(
            recording_id=new_recording.id,
            audio_path=str(work_path),
            filename=FIXTURE.name,
            session=async_session,
        )

        rec_result = await async_session.execute(
            select(Recording).where(Recording.id == new_recording.id)  # type: ignore[arg-type]
        )
        updated = rec_result.scalar_one()
        assert updated.status == "completed"
        assert updated.duration_seconds is not None and updated.duration_seconds > 0

        det_result = await async_session.execute(
            select(Detection).where(Detection.recording_id == new_recording.id)  # type: ignore[arg-type]
        )
        detections = list(det_result.scalars().all())
        assert len(detections) > 0
        assert detections[0].species is not None
        assert detections[0].confidence is not None
        assert detections[0].start_time is not None
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
