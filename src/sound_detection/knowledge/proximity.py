"""Persist nearest-iNat distance for a species at a site.

Used by the backfill script and the active detection path.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from sound_detection.db.models import SpeciesSiteProximity
from sound_detection.knowledge.harvesters.inaturalist import DEFAULT_RADIUS_KM, InaturalistHarvester

log = logging.getLogger(__name__)


async def upsert_proximity(
    session: AsyncSession,
    site_id: UUID,
    scientific_name: str,
    lat: float,
    lon: float,
    harvester: InaturalistHarvester | None = None,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> SpeciesSiteProximity:
    """Fetch nearest observation and upsert the proximity row. Always writes a row."""
    harvester = harvester or InaturalistHarvester()
    result = harvester.nearest_observation(scientific_name, lat, lon, radius_km=radius_km)

    existing = (
        await session.execute(
            select(SpeciesSiteProximity).where(
                col(SpeciesSiteProximity.site_id) == site_id,
                col(SpeciesSiteProximity.scientific_name) == scientific_name,
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing is None:
        row = SpeciesSiteProximity(
            site_id=site_id,
            scientific_name=scientific_name,
            search_radius_km=radius_km,
            fetched_at=now,
        )
        session.add(row)
    else:
        row = existing
        row.fetched_at = now
        row.search_radius_km = radius_km

    if result:
        row.distance_km = result["distance_km"]
        row.distance_miles = result["distance_miles"]
        row.observation_id = result["observation_id"]
        row.observed_on = result["observed_on"]
        row.observation_lat = result["observation_lat"]
        row.observation_lon = result["observation_lon"]
        row.quality_grade = result["quality_grade"]
        row.place_guess = result["place_guess"]
    else:
        row.distance_km = None
        row.distance_miles = None
        row.observation_id = None
        row.observed_on = None
        row.observation_lat = None
        row.observation_lon = None
        row.quality_grade = None
        row.place_guess = None

    await session.commit()
    await session.refresh(row)
    return row


def proximity_to_dict(row: SpeciesSiteProximity) -> dict[str, Any]:
    return {
        "site_id": str(row.site_id),
        "scientific_name": row.scientific_name,
        "distance_km": row.distance_km,
        "distance_miles": row.distance_miles,
        "observation_id": row.observation_id,
        "observed_on": row.observed_on.isoformat() if row.observed_on else None,
        "observation_lat": row.observation_lat,
        "observation_lon": row.observation_lon,
        "quality_grade": row.quality_grade,
        "place_guess": row.place_guess,
        "search_radius_km": row.search_radius_km,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
    }
