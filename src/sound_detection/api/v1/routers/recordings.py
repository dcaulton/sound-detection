from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.api.v1.schemas.recording import RecordingUpdate
from sound_detection.db.models import Recording
from sound_detection.db.repositories import RecordingRepository
from sound_detection.db.session import get_db

router = APIRouter(prefix="/v1/recordings", tags=["recordings"])

db_dep = Depends(get_db)


@router.patch("/{recording_id}", response_model=Recording)
async def update_recording(
    recording_id: UUID,
    payload: RecordingUpdate,
    db: AsyncSession = db_dep,
) -> Recording:
    repo = RecordingRepository(db)
    updated = await repo.update_recording(
        recording_id=recording_id,
        microphone_id=payload.microphone_id,
        recorded_at=payload.recorded_at,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Recording not found")
    return updated
