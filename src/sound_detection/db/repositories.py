from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from sound_detection.db.models import Detection, Microphone, Recording, Site
from sound_detection.utils.datetime import parse_recording_datetime_from_filename

log = structlog.get_logger()


class RecordingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, recording_id: UUID) -> Recording | None:
        result = await self.session.execute(select(Recording).where(Recording.id == recording_id))
        return result.scalars().one_or_none()

    async def create(self, recording: Recording) -> Recording:
        self.session.add(recording)
        await self.session.commit()
        await self.session.refresh(recording)
        return recording

    async def save_detections(
        self, recording_id: UUID, detections: list[dict], duration_seconds: float | None = None
    ) -> None:
        """Save detections and update recording status."""
        if not detections:
            return

        recording = await self.session.get(Recording, recording_id)
        if recording is None:
            log.warning("Recording not found when saving detections", recording_id=recording_id)
            return

        recording.status = "completed"
        if duration_seconds is not None:
            recording.duration_seconds = duration_seconds
        self.session.add(recording)

        detection_objects: list[Detection] = []

        for d in detections:
            start_offset = d.get("start_time", 0.0)
            end_offset = d.get("end_time", 0.0)

            start_time = None
            end_time = None

            if recording.recorded_at is not None:
                start_time = recording.recorded_at + timedelta(seconds=start_offset)
                end_time = recording.recorded_at + timedelta(seconds=end_offset)

            det = Detection(
                recording_id=recording_id,
                species=d["species"],
                common_name=d["common_name"],
                scientific_name=d["scientific_name"],
                confidence=d["confidence"],
                start_offset=start_offset,
                end_offset=end_offset,
                start_time=start_time,
                end_time=end_time,
            )
            detection_objects.append(det)

        self.session.add_all(detection_objects)
        await self.session.commit()

    async def get_or_create_default_microphone(self) -> Microphone:
        # Get or create default site
        site_result = await self.session.execute(select(Site).limit(1))
        site = site_result.scalars().first()

        if site is None:
            site = Site(name="Default Site")
            self.session.add(site)
            await self.session.commit()
            await self.session.refresh(site)

        # Get or create default microphone
        mic_result = await self.session.execute(select(Microphone).limit(1))
        mic = mic_result.scalars().first()

        if not mic:
            mic = Microphone(
                site_id=site.id,
                name="Default Microphone",
                latitude=0.0,
                longitude=0.0,
            )
            self.session.add(mic)
            await self.session.commit()
            await self.session.refresh(mic)

        # Eagerly load the site relationship so mic.site doesn't trigger a lazy load later
        stmt = select(Microphone).options(selectinload(Microphone.site)).where(Microphone.id == mic.id)  # type: ignore[arg-type]
        result = await self.session.execute(stmt)  # ← use self.session consistently
        return result.scalar_one()

    async def update_recording(
        self,
        recording_id: UUID,
        microphone_id: UUID | None = None,
        recorded_at: datetime | None = None,
    ) -> Recording | None:
        recording = await self.session.get(Recording, recording_id)
        if not recording:
            return None

        changed = False

        # Handle microphone change → may require re-deriving recorded_at from filename
        if microphone_id and microphone_id != recording.microphone_id:
            recording.microphone_id = microphone_id
            mic = await self.session.get(Microphone, microphone_id)
            tz_name = mic.site.timezone if mic and mic.site else "UTC"

            new_recorded_at = parse_recording_datetime_from_filename(recording.filename, tz_name)
            if new_recorded_at:
                recording.recorded_at = new_recorded_at
            changed = True

        # Direct recorded_at override
        if recorded_at is not None:
            recording.recorded_at = recorded_at
            changed = True

        if changed:
            recording.updated_at = datetime.now(UTC)

            # Propagate to all child detections
            result = await self.session.execute(select(Detection).where(Detection.recording_id == recording_id))
            for det in result.scalars().all():
                if recording.recorded_at:
                    det.start_time = recording.recorded_at + timedelta(seconds=det.start_offset)
                    det.end_time = recording.recorded_at + timedelta(seconds=det.end_offset)
                det.updated_at = datetime.now(UTC)

            await self.session.commit()
            await self.session.refresh(recording)

        return recording
