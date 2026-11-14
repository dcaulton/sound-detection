"""Backfill nearest-iNat distance for every (site, detected species) pair.

Usage:
    DATABASE_URL=postgresql://sound:sound@localhost:5433/sound_detection \
    uv run python bin/backfill_proximity.py

Optional:
    --site-id UUID     only one site
    --limit N          max species per site
    --radius-km 160
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time
from uuid import UUID

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import col

from sound_detection.db.models import Detection, Microphone, Recording, Site
from sound_detection.knowledge.harvesters.inaturalist import InaturalistHarvester
from sound_detection.knowledge.proximity import upsert_proximity

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

RATE_LIMIT_SLEEP = 1.25


def _normalize_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


async def species_for_site(session: AsyncSession, site_id: UUID) -> list[str]:
    stmt = (
        select(distinct(col(Detection.scientific_name)))
        .join(Recording, col(Detection.recording_id) == col(Recording.id))
        .join(Microphone, col(Recording.microphone_id) == col(Microphone.id))
        .where(col(Microphone.site_id) == site_id)
        .where(col(Detection.scientific_name).is_not(None))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [r for r in rows if r and " " in r and r[0].isupper()]


async def run(site_id: UUID | None, limit: int | None, radius_km: float) -> None:
    url = _normalize_url(os.getenv("DATABASE_URL", "postgresql+psycopg://sound:sound@localhost:5433/sound_detection"))
    engine = create_async_engine(url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    harvester = InaturalistHarvester()

    async with Session() as session:
        if site_id:
            sites = (await session.execute(select(Site).where(col(Site.id) == site_id))).scalars().all()
        else:
            sites = (await session.execute(select(Site))).scalars().all()

        for site in sites:
            if site.latitude == 0 and site.longitude == 0:
                log.warning("skipping %s (%s): coordinates are 0,0", site.id, site.name)
                continue
            if not (-90 <= site.latitude <= 90 and -180 <= site.longitude <= 180):
                log.warning("skipping %s (%s): coordinates out of range", site.id, site.name)
                continue

            names = await species_for_site(session, site.id)
            if limit:
                names = names[:limit]
            log.info("site %s (%s): %d species", site.id, site.name, len(names))

            for name in names:
                try:
                    row = await upsert_proximity(
                        session,
                        site.id,
                        name,
                        site.latitude,
                        site.longitude,
                        harvester=harvester,
                        radius_km=radius_km,
                    )
                    dist = f"{row.distance_miles} mi" if row.distance_miles is not None else "none in radius"
                    log.info("  %s -> %s", name, dist)
                except Exception:
                    log.exception("  failed for %s", name)
                time.sleep(RATE_LIMIT_SLEEP)

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-id", type=UUID, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--radius-km", type=float, default=160.0)
    args = parser.parse_args()
    asyncio.run(run(args.site_id, args.limit, args.radius_km))


if __name__ == "__main__":
    main()
