from collections.abc import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import nulls_last
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from sound_detection.db.models import Site, SpeciesSiteProximity
from sound_detection.db.session import get_db
from sound_detection.knowledge.proximity import proximity_to_dict

router = APIRouter(prefix="/sites", tags=["sites"])

db_dep = Depends(get_db)


@router.get("/")
async def list_sites(db: AsyncSession = db_dep) -> Sequence[Site]:
    result = await db.execute(select(Site))
    return result.scalars().all()


@router.get("/{site_id}/proximity")
async def list_site_proximity(site_id: UUID, db: AsyncSession = db_dep) -> list[dict]:
    """Passive: nearest iNat distance for each species known at this site."""
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    rows = (
        (
            await db.execute(
                select(SpeciesSiteProximity)
                .where(SpeciesSiteProximity.site_id == site_id)
                .order_by(nulls_last(col(SpeciesSiteProximity.distance_miles)))
            )
        )
        .scalars()
        .all()
    )
    return [proximity_to_dict(r) for r in rows]


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
