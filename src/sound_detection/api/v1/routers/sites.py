from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
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


@router.put("/{site_id}")
async def update_site(
    site_id: UUID,
    site_update: Site,
    db: AsyncSession = db_dep,
) -> Site:
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    for key, value in site_update.dict(exclude_unset=True).items():
        setattr(site, key, value)

    await db.commit()
    await db.refresh(site)
    return site


@router.delete("/{site_id}", status_code=204)
async def delete_site(site_id: UUID, db: AsyncSession = db_dep) -> None:
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    await db.delete(site)
    await db.commit()
