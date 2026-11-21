"""BirdNET-Go compatible read API for Birdsong.

Birdsong is a plate UI that talks to BirdNET-Go. These endpoints serve the
same shapes from our detections so a Birdsong container can point
BIRDNET_URL at this API.

Supported periods are whatever Birdsong asks for. "Last 30 days" arrives as
start_date/end_date on the summary. "All time" arrives with no dates.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from sound_detection.db.models import Detection, Microphone, Recording
from sound_detection.db.session import get_db

router = APIRouter(prefix="/api/v2", tags=["birdnet-compat"])
db_dep = Depends(get_db)


def _parse_day(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).replace(tzinfo=UTC)
    except ValueError:
        return None


def _window(start_date: str | None, end_date: str | None) -> tuple[datetime | None, datetime | None]:
    start = _parse_day(start_date)
    end = _parse_day(end_date)
    if end is not None:
        end = end + timedelta(days=1)
    return start, end


PLACEHOLDER = "NEEDS COMMON NAME"


def _real_name(value: str | None, scientific: str) -> str | None:
    if not value or value.strip().upper() == PLACEHOLDER:
        return None
    if value.strip().lower() == scientific.lower():
        return None
    return value.strip()


def _heard(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat()


@router.get("/analytics/species/summary")
async def species_summary(
    session: Annotated[AsyncSession, db_dep],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    site_id: Annotated[UUID | None, Query()] = None,
) -> list[dict[str, Any]]:
    """Species and counts. No dates means all time."""
    start, end = _window(start_date, end_date)
    heard = func.coalesce(Detection.start_time, Detection.created_at)
    # max() would pick the placeholder "NEEDS COMMON NAME" over a real name.
    real_common = func.max(Detection.common_name).filter(col(Detection.common_name) != PLACEHOLDER)
    stmt = (
        select(  # type: ignore[call-overload]
            Detection.scientific_name,
            real_common.label("common_name"),
            func.count().label("count"),
            func.min(heard).label("first_heard"),
            func.max(heard).label("last_heard"),
            func.max(Detection.confidence).label("max_confidence"),
            func.avg(Detection.confidence).label("avg_confidence"),
        )
        .join(Recording, col(Detection.recording_id) == col(Recording.id))
        .join(Microphone, col(Recording.microphone_id) == col(Microphone.id))
        .where(col(Detection.scientific_name) != "")
        .group_by(Detection.scientific_name)
        .order_by(func.count().desc())
    )
    if site_id is not None:
        stmt = stmt.where(col(Microphone.site_id) == site_id)
    if start is not None:
        stmt = stmt.where(heard >= start)
    if end is not None:
        stmt = stmt.where(heard < end)

    rows = (await session.execute(stmt)).all()
    missing = [name for name, common, *_ in rows if name and not _real_name(common, name)]
    looked_up = _fill_common_names(missing)
    return [
        {
            "scientific_name": name,
            "common_name": _real_name(common, name) or looked_up.get(name) or name,
            "count": int(count),
            "first_heard": _heard(first),
            "last_heard": _heard(last),
            "max_confidence": float(max_conf or 0),
            "avg_confidence": float(avg_conf or 0),
        }
        for name, common, count, first, last, max_conf, avg_conf in rows
        if name
    ]


def _fill_common_names(names: list[str]) -> dict[str, str]:
    """Names already stored on Species nodes. No network calls."""
    if not names:
        return {}
    from sound_detection.db.neo4j import get_neo4j_driver

    driver = get_neo4j_driver()
    with driver.session() as session:
        rows = session.run(
            "MATCH (s:Species) WHERE s.scientific_name IN $names "
            "AND s.common_name IS NOT NULL AND s.common_name <> '' "
            "RETURN s.scientific_name AS name, s.common_name AS common",
            names=names,
        ).data()
    return {r["name"]: r["common"] for r in rows if r.get("common") and r["common"].strip().upper() != PLACEHOLDER}


@router.get("/analytics/time/distribution/hourly")
async def hourly(
    session: Annotated[AsyncSession, db_dep],
    species: Annotated[str, Query()],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    site_id: Annotated[UUID | None, Query()] = None,
) -> list[dict[str, int]]:
    """Hour-of-day counts. Birdsong expects {hour, count}."""
    start, end = _window(start_date, end_date)
    heard = func.coalesce(Detection.start_time, Detection.created_at)
    hour = func.extract("hour", heard)
    stmt = (
        select(hour.label("hour"), func.count().label("count"))  # type: ignore[call-overload]
        .join(Recording, col(Detection.recording_id) == col(Recording.id))
        .join(Microphone, col(Recording.microphone_id) == col(Microphone.id))
        .where(col(Detection.scientific_name) == species)
        .group_by(hour)
    )
    if site_id is not None:
        stmt = stmt.where(col(Microphone.site_id) == site_id)
    if start is not None:
        stmt = stmt.where(heard >= start)
    if end is not None:
        stmt = stmt.where(heard < end)

    rows = (await session.execute(stmt)).all()
    return [{"hour": int(h), "count": int(c)} for h, c in rows]


@router.get("/analytics/time/daily")
async def daily(
    session: Annotated[AsyncSession, db_dep],
    species: Annotated[str, Query()],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    site_id: Annotated[UUID | None, Query()] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Calls per day. Birdsong reads j.data[].date and .count."""
    start, end = _window(start_date, end_date)
    heard = func.coalesce(Detection.start_time, Detection.created_at)
    day = func.date(heard)
    stmt = (
        select(day.label("date"), func.count().label("count"))  # type: ignore[call-overload]
        .join(Recording, col(Detection.recording_id) == col(Recording.id))
        .join(Microphone, col(Recording.microphone_id) == col(Microphone.id))
        .where(col(Detection.scientific_name) == species)
        .group_by(day)
        .order_by(day)
    )
    if site_id is not None:
        stmt = stmt.where(col(Microphone.site_id) == site_id)
    if start is not None:
        stmt = stmt.where(heard >= start)
    if end is not None:
        stmt = stmt.where(heard < end)

    rows = (await session.execute(stmt)).all()
    return {"data": [{"date": str(d)[:10], "count": int(c)} for d, c in rows]}


@router.get("/species")
async def species_info(
    scientific_name: Annotated[str, Query()],
) -> dict[str, Any]:
    """Family and order. Empty for now; Birdsong hides missing facts."""
    return {
        "scientific_name": scientific_name,
        "taxonomy": {},
    }


@router.get("/detections")
async def detections(
    session: Annotated[AsyncSession, db_dep],
    species: Annotated[str, Query()],
    numResults: Annotated[int, Query()] = 4,
    site_id: Annotated[UUID | None, Query()] = None,
) -> list[dict[str, Any]]:
    """Latest detections. No audio yet; the card still lists time and confidence."""
    heard = func.coalesce(Detection.start_time, Detection.created_at)
    stmt = (
        select(Detection, heard.label("heard"))  # type: ignore[call-overload]
        .join(Recording, col(Detection.recording_id) == col(Recording.id))
        .join(Microphone, col(Recording.microphone_id) == col(Microphone.id))
        .where(col(Detection.scientific_name) == species)
        .order_by(heard.desc())
        .limit(max(1, min(numResults, 20)))
    )
    if site_id is not None:
        stmt = stmt.where(col(Microphone.site_id) == site_id)

    rows = (await session.execute(stmt)).all()
    out = []
    for det, when in rows:
        ts = when or det.created_at
        out.append(
            {
                "id": str(det.id),
                "date": ts.astimezone(UTC).date().isoformat(),
                "time": ts.astimezone(UTC).strftime("%H:%M:%S"),
                "confidence": det.confidence,
            }
        )
    return out
