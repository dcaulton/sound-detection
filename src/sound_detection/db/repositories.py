"""Repository pattern for Recording and Detection."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from sound_detection.db.models import Detection, Recording


class RecordingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, recording: Recording) -> Recording:
        self.session.add(recording)
        await self.session.commit()
        await self.session.refresh(recording)
        return recording

    async def get(self, recording_id: UUID) -> Any | None:
        result = await self.session.execute(select(Recording).where(Recording.id == recording_id))
        return result.scalar_one_or_none()

    async def save_detections(self, recording_id: UUID, detections: list[dict]) -> None:
        """Save detections from BirdNET analysis."""
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
