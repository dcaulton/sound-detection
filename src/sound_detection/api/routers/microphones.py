from collections.abc import Sequence

from fastapi import APIRouter, Depends
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
