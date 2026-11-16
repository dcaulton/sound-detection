"""iNaturalist nearest-observation lookup.

Given a site's coordinates and a scientific name, find the closest
research-grade observation within a search radius and return the distance.
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import Any

import requests

logger = logging.getLogger(__name__)

INAT_OBSERVATIONS_URL = "https://api.inaturalist.org/v1/observations"
INAT_TAXA_URL = "https://api.inaturalist.org/v1/taxa"

# ~100 miles. iNat radius param is in km.
DEFAULT_RADIUS_KM = 160.0
KM_PER_MILE = 1.609344
EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def km_to_miles(km: float) -> float:
    return km / KM_PER_MILE


def miles_to_km(miles: float) -> float:
    return miles * KM_PER_MILE


class InaturalistHarvester:
    """Find the nearest iNaturalist observation of a species to a point."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "sound-detection/0.2 (https://github.com/dcaulton/sound-detection; bioacoustics research)"
        )

    def nearest_observation(
        self,
        scientific_name: str,
        lat: float,
        lon: float,
        radius_km: float = DEFAULT_RADIUS_KM,
        quality_grade: str = "research",
        per_page: int = 30,
    ) -> dict[str, Any] | None:
        """Return the closest matching observation, or None if nothing is in range.

        Result keys:
            scientific_name, distance_km, distance_miles, observation_id,
            observed_on, observation_lat, observation_lon, quality_grade,
            place_guess, search_radius_km
        """
        taxon_id = self._resolve_taxon_id(scientific_name)
        params: dict[str, str | int | float] = {
            "lat": lat,
            "lng": lon,
            "radius": radius_km,
            "quality_grade": quality_grade,
            "per_page": per_page,
            "order_by": "observed_on",
            "order": "desc",
            "geo": "true",
        }
        if taxon_id is not None:
            params["taxon_id"] = taxon_id
        else:
            params["taxon_name"] = scientific_name

        try:
            resp = self.session.get(INAT_OBSERVATIONS_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("iNat observations lookup failed for %s: %s", scientific_name, exc)
            return None

        results = resp.json().get("results") or []
        closest = self._closest(results, lat, lon)
        if closest is None:
            return None

        dist_km = closest["distance_km"]
        return {
            "scientific_name": scientific_name,
            "distance_km": round(dist_km, 2),
            "distance_miles": round(km_to_miles(dist_km), 2),
            "observation_id": closest["id"],
            "observed_on": closest["observed_on"],
            "observation_lat": closest["lat"],
            "observation_lon": closest["lon"],
            "quality_grade": closest["quality_grade"],
            "place_guess": closest["place_guess"],
            "search_radius_km": radius_km,
        }

    def _resolve_taxon_id(self, scientific_name: str) -> int | None:
        """Best-effort taxon id so the observation query is precise."""
        taxa_params: dict[str, str] = {
            "q": scientific_name,
            "is_active": "true",
            "per_page": "5",
            "rank": "species",
        }
        try:
            resp = self.session.get(
                INAT_TAXA_URL,
                params=taxa_params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("iNat taxon resolve failed for %s: %s", scientific_name, exc)
            return None

        name_lower = scientific_name.lower()
        for taxon in resp.json().get("results") or []:
            if (taxon.get("name") or "").lower() == name_lower:
                return int(taxon["id"])
        results = resp.json().get("results") or []
        if results and results[0].get("id"):
            return int(results[0]["id"])
        return None

    @staticmethod
    def _closest(results: list[dict[str, Any]], lat: float, lon: float) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_km = float("inf")
        for obs in results:
            point = _observation_point(obs)
            if point is None:
                continue
            obs_lat, obs_lon = point
            dist = haversine_km(lat, lon, obs_lat, obs_lon)
            if dist < best_km:
                best_km = dist
                best = {
                    "id": obs.get("id"),
                    "lat": obs_lat,
                    "lon": obs_lon,
                    "distance_km": dist,
                    "observed_on": _parse_date(obs.get("observed_on")),
                    "quality_grade": obs.get("quality_grade"),
                    "place_guess": obs.get("place_guess"),
                }
        return best


def _observation_point(obs: dict[str, Any]) -> tuple[float, float] | None:
    """Extract (lat, lon) from an iNat observation payload."""
    location = obs.get("location")  # "lat,lng"
    if isinstance(location, str) and "," in location:
        try:
            lat_s, lon_s = location.split(",", 1)
            return float(lat_s), float(lon_s)
        except ValueError:
            pass
    geojson = obs.get("geojson") or {}
    coords = geojson.get("coordinates")
    if isinstance(coords, list) and len(coords) == 2:
        # GeoJSON is [lon, lat]
        try:
            return float(coords[1]), float(coords[0])
        except (TypeError, ValueError):
            return None
    return None


def _parse_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
