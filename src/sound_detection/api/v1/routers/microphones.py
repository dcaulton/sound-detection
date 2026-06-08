from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from sound_detection.db.models import Microphone
from sound_detection.db.session import get_db

router = APIRouter(prefix="/microphones", tags=["microphones"])

db_dep = Depends(get_db)


@router.get("/")
async def list_microphones(db: AsyncSession = db_dep) -> Sequence[Microphone]:
    result = await db.execute(select(Microphone))
    return result.scalars().all()


@router.post("/")
async def create_microphone(mic: Microphone, db: AsyncSession = db_dep) -> Microphone:
    db.add(mic)
    await db.commit()
    await db.refresh(mic)
    return mic


@router.put("/{microphone_id}")
async def update_microphone(microphone_id: UUID, mic_update: Microphone, db: AsyncSession = db_dep) -> Microphone:
    mic = await db.get(Microphone, microphone_id)
    if not mic:
        raise HTTPException(status_code=404, detail="Microphone not found")

    for key, value in mic_update.dict(exclude_unset=True).items():
        setattr(mic, key, value)

    await db.commit()
    await db.refresh(mic)
    return mic


@router.delete("/{microphone_id}", status_code=204)
async def delete_microphone(microphone_id: UUID, db: AsyncSession = db_dep) -> None:
    mic = await db.get(Microphone, microphone_id)
    if not mic:
        raise HTTPException(status_code=404, detail="Microphone not found")
    await db.delete(mic)
    await db.commit()
