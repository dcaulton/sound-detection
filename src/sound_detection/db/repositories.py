"""Repository pattern for Recording and Detection."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlmodel import select

from sound_detection.db.models import Detection, Microphone, Recording, Site


class RecordingRepository:
    def __init__(self, session: Session | AsyncSession) -> None:
        self.session = session

    def create(self, recording: Recording) -> Recording:
        self.session.add(recording)
        self.session.commit()
        self.session.refresh(recording)
        return recording

    def get(self, recording_id: UUID) -> Any | None:
        result = self.session.execute(select(Recording).where(Recording.id == recording_id))
        return result.scalar_one_or_none()  # type: ignore[union-attr]

    def save_detections(self, recording_id: UUID, detections: list[dict]) -> None:
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
        self.session.commit()

    def get_or_create_default_microphone(self) -> "Microphone":
        # Site
        site_result = self.session.execute(select(Site).limit(1))
        site = site_result.scalars().first()  # type: ignore[union-attr]

        if not site:
            site = Site(name="Default Site")
            self.session.add(site)
            self.session.commit()
            self.session.refresh(site)

        # Microphone
        mic_result = self.session.execute(select(Microphone).limit(1))
        mic = mic_result.scalars().first()  # type: ignore[union-attr]

        if mic:
            return mic

        mic = Microphone(
            id=uuid4(),
            site_id=site.id,
            name="Default Microphone",
            latitude=0.0,
            longitude=0.0,
        )
        self.session.add(mic)
        self.session.commit()
        self.session.refresh(mic)
        return mic
