from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from sound_detection.db.models import Detection, Microphone, Recording, Site


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

    async def save_detections(self, recording_id: UUID, detections: list[dict]) -> None:
        for det in detections:
            detection = Detection(
                recording_id=recording_id,
                species=det["scientific_name"],
                common_name=det["common_name"],
                scientific_name=det["scientific_name"],
                confidence=det["confidence"],
                start_time=det["start_time"],
                end_time=det["end_time"],
            )
            self.session.add(detection)
        await self.session.commit()

    async def get_or_create_default_microphone(self) -> Microphone:
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

        if mic:
            return mic

        mic = Microphone(
            site_id=site.id,
            name="Default Microphone",
            latitude=0.0,
            longitude=0.0,
        )
        self.session.add(mic)
        await self.session.commit()
        await self.session.refresh(mic)
        return mic
