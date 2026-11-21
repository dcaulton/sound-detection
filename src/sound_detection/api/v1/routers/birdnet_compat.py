"""BirdNET-Go compatible read API for Birdsong.

Birdsong is a plate UI that talks to BirdNET-Go. These endpoints serve the
same shapes from our detections so a Birdsong container can point
BIRDNET_URL at this API.

Supported periods are whatever Birdsong asks for. "Last 30 days" arrives as
start_date/end_date on the summary. "All time" arrives with no dates.

gate (default confirmed):
  confirmed  both BirdNET and Perch
  local      at least one model, and iNat within 100 miles
  rare       both models, and iNat has nothing nearby
  all        every binomial, including single-model hits
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from sound_detection.db.models import Detection, Microphone, Recording, SpeciesSiteProximity
from sound_detection.db.session import get_db
from sound_detection.knowledge.filtering import NON_SPECIES_LABELS, is_local, is_unexpected

router = APIRouter(prefix="/api/v2", tags=["birdnet-compat"])
db_dep = Depends(get_db)

PLACEHOLDER = "NEEDS COMMON NAME"
NEAR_KM = 160.9344  # 100 miles
FAR_KM = 804.672  # 500 miles
GATES = {"confirmed", "local", "rare", "all"}


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


def is_binomial(name: str) -> bool:
    """True for 'Genus species'. Drops Engine, Dog, and Walk_and_footsteps."""
    if not name or name.lower().strip() in NON_SPECIES_LABELS:
        return False
    parts = name.split()
    if len(parts) != 2 or "_" in name:
        return False
    return parts[0][:1].isupper() and parts[1][:1].islower()


def passes_gate(
    gate: str,
    has_birdnet: bool,
    has_perch: bool,
    distance_km: float | None,
) -> bool:
    """Which species a plate is allowed to show."""
    chosen = gate if gate in GATES else "confirmed"
    if chosen == "all":
        return True
    if chosen == "confirmed":
        return has_birdnet and has_perch
    if chosen == "local":
        return (has_birdnet or has_perch) and is_local(distance_km, NEAR_KM)
    if chosen == "rare":
        return is_unexpected(has_birdnet, has_perch, distance_km, NEAR_KM, FAR_KM)
    return has_birdnet and has_perch


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


async def _proximity(session: AsyncSession, site_id: UUID | None) -> dict[str, float | None]:
    """scientific_name -> distance_km. Missing key means we never searched."""
    stmt = select(SpeciesSiteProximity.scientific_name, SpeciesSiteProximity.distance_km)
    if site_id is not None:
        stmt = stmt.where(col(SpeciesSiteProximity.site_id) == site_id)
    rows = (await session.execute(stmt)).all()
    out: dict[str, float | None] = {}
    for name, dist in rows:
        # None means searched and found nothing. Keep it.
        if name not in out or (out[name] is None and dist is not None):
            out[name] = dist
    return out


async def _model_rows(
    session: AsyncSession,
    start: datetime | None,
    end: datetime | None,
    site_id: UUID | None,
    species: str | None = None,
) -> list[Any]:
    heard = func.coalesce(Detection.start_time, Detection.created_at)
    real_common = func.max(Detection.common_name).filter(col(Detection.common_name) != PLACEHOLDER)
    stmt = (
        select(  # type: ignore[call-overload]
            Detection.scientific_name,
            Detection.model,
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
        .group_by(Detection.scientific_name, Detection.model)
    )
    if species is not None:
        stmt = stmt.where(col(Detection.scientific_name) == species)
    if site_id is not None:
        stmt = stmt.where(col(Microphone.site_id) == site_id)
    if start is not None:
        stmt = stmt.where(heard >= start)
    if end is not None:
        stmt = stmt.where(heard < end)
    return list((await session.execute(stmt)).all())


def _fold(rows: list[Any]) -> dict[str, dict[str, Any]]:
    """One record per species, with which models saw it."""
    folded: dict[str, dict[str, Any]] = {}
    for name, model, common, count, first, last, max_conf, avg_conf in rows:
        if not name or not is_binomial(name):
            continue
        rec = folded.setdefault(
            name,
            {
                "common": None,
                "count": 0,
                "first": None,
                "last": None,
                "max_conf": 0.0,
                "avg_sum": 0.0,
                "avg_n": 0,
                "birdnet": False,
                "perch": False,
            },
        )
        rec["count"] += int(count)
        rec["birdnet"] = rec["birdnet"] or model != "perch"
        rec["perch"] = rec["perch"] or model == "perch"
        real = _real_name(common, name)
        if real and not rec["common"]:
            rec["common"] = real
        if first is not None and (rec["first"] is None or first < rec["first"]):
            rec["first"] = first
        if last is not None and (rec["last"] is None or last > rec["last"]):
            rec["last"] = last
        rec["max_conf"] = max(rec["max_conf"], float(max_conf or 0))
        rec["avg_sum"] += float(avg_conf or 0) * int(count)
        rec["avg_n"] += int(count)
    return folded


@router.get("/analytics/species/summary")
async def species_summary(
    session: Annotated[AsyncSession, db_dep],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    site_id: Annotated[UUID | None, Query()] = None,
    gate: Annotated[str, Query()] = "confirmed",
) -> list[dict[str, Any]]:
    """Species and counts. No dates means all time. gate defaults to confirmed."""
    start, end = _window(start_date, end_date)
    rows = await _model_rows(session, start, end, site_id)
    folded = _fold(rows)
    proximity = await _proximity(session, site_id)

    kept = {
        name: rec
        for name, rec in folded.items()
        if passes_gate(gate, rec["birdnet"], rec["perch"], proximity.get(name))
    }
    missing = [name for name, rec in kept.items() if not rec["common"]]
    looked_up = _fill_common_names(missing)

    out = []
    for name, rec in kept.items():
        out.append(
            {
                "scientific_name": name,
                "common_name": rec["common"] or looked_up.get(name) or name,
                "count": rec["count"],
                "first_heard": _heard(rec["first"]),
                "last_heard": _heard(rec["last"]),
                "max_confidence": rec["max_conf"],
                "avg_confidence": rec["avg_sum"] / rec["avg_n"] if rec["avg_n"] else 0.0,
            }
        )
    out.sort(key=lambda r: r["count"], reverse=True)
    return out


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


async def _allowed(
    session: AsyncSession,
    species: str,
    start: datetime | None,
    end: datetime | None,
    site_id: UUID | None,
    gate: str,
) -> bool:
    """True if this species is a binomial and passes the gate in this window."""
    if not is_binomial(species):
        return False
    rows = await _model_rows(session, start, end, site_id, species)
    folded = _fold(rows)
    rec = folded.get(species)
    if rec is None:
        return False
    proximity = await _proximity(session, site_id)
    return passes_gate(gate, rec["birdnet"], rec["perch"], proximity.get(species))


@router.get("/analytics/time/distribution/hourly")
async def hourly(
    session: Annotated[AsyncSession, db_dep],
    species: Annotated[str, Query()],
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
    site_id: Annotated[UUID | None, Query()] = None,
    gate: Annotated[str, Query()] = "confirmed",
) -> list[dict[str, int]]:
    """Hour-of-day counts. Empty if the species fails the gate."""
    start, end = _window(start_date, end_date)
    if not await _allowed(session, species, start, end, site_id, gate):
        return []
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
    gate: Annotated[str, Query()] = "confirmed",
) -> dict[str, list[dict[str, Any]]]:
    """Calls per day. Empty if the species fails the gate."""
    start, end = _window(start_date, end_date)
    if not await _allowed(session, species, start, end, site_id, gate):
        return {"data": []}
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
    return {"scientific_name": scientific_name, "taxonomy": {}}


@router.get("/detections")
async def detections(
    session: Annotated[AsyncSession, db_dep],
    species: Annotated[str, Query()],
    numResults: Annotated[int, Query()] = 4,
    site_id: Annotated[UUID | None, Query()] = None,
    gate: Annotated[str, Query()] = "confirmed",
) -> list[dict[str, Any]]:
    """Latest detections. Empty if the species fails the gate."""
    if not await _allowed(session, species, None, None, site_id, gate):
        return []
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
