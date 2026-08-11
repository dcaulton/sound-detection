import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.db.models import Detection, Microphone, Recording, Site


@pytest.mark.asyncio
async def test_delete_recording_cascades_detections(async_session: AsyncSession) -> None:
    site = Site(name="Cascade Test Site")
    async_session.add(site)
    await async_session.commit()
    await async_session.refresh(site)

    mic = Microphone(
        site_id=site.id,
        name="Cascade Test Mic",
        latitude=0.0,
        longitude=0.0,
    )
    async_session.add(mic)
    await async_session.commit()
    await async_session.refresh(mic)

    rec = Recording(
        microphone_id=mic.id,
        filename="cascade_test.wav",
        file_path="/tmp/cascade_test.wav",
        status="completed",
    )
    async_session.add(rec)
    await async_session.commit()
    await async_session.refresh(rec)

    det = Detection(
        recording_id=rec.id,
        scientific_name="Turdus migratorius",
        common_name="American Robin",
        confidence=0.9,
        start_offset=23.5,
        end_offset=28.5,
        species="Turdus migratorius",
    )
    async_session.add(det)
    await async_session.commit()

    rec_id = rec.id
    await async_session.delete(rec)
    await async_session.commit()

    left = await async_session.scalar(select(func.count()).select_from(Recording).where(Recording.id == rec_id))  # type: ignore[arg-type]
    dets = await async_session.scalar(
        select(func.count()).select_from(Detection).where(Detection.recording_id == rec_id)  # type: ignore[arg-type]
    )
    assert left == 0
    assert dets == 0
