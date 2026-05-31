"""Repository pattern for Recording and Detection."""

from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.db.models import Recording


class RecordingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, recording: Recording) -> Recording:
        self.session.add(recording)
        await self.session.commit()
        await self.session.refresh(recording)
        return recording
