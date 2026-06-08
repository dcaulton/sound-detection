from collections.abc import Sequence

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from sound_detection.db.models import Site
from sound_detection.db.session import get_db

router = APIRouter(prefix="/sites", tags=["sites"])

db_dep = Depends(get_db)


@router.get("/")
async def list_sites(db: AsyncSession = db_dep) -> Sequence[Site]:
    result = await db.execute(select(Site))
    return result.scalars().all()


@router.post("/")
async def create_site(site: Site, db: AsyncSession = db_dep) -> Site:
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return site
