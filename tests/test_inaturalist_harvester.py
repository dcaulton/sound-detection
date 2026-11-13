"""Tests for the iNaturalist nearest-observation harvester."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from sound_detection.knowledge.harvesters.inaturalist import (
    InaturalistHarvester,
    haversine_km,
    km_to_miles,
)


def test_haversine_known_distance() -> None:
    # Chicago to a point ~1 degree north is roughly 111 km
    km = haversine_km(41.8781, -87.6298, 42.8781, -87.6298)
    assert 110 < km < 112
    assert abs(km_to_miles(km) - km / 1.609344) < 0.01


def test_nearest_observation_picks_closest() -> None:
    harvester = InaturalistHarvester()

    taxa_resp = MagicMock()
    taxa_resp.raise_for_status.return_value = None
    taxa_resp.json.return_value = {"results": [{"id": 12345, "name": "Turdus migratorius"}]}

    # Two observations: one far, one close. Order in the payload is not distance order.
    obs_resp = MagicMock()
    obs_resp.raise_for_status.return_value = None
    obs_resp.json.return_value = {
        "results": [
            {
                "id": 1,
                "location": "43.0,-87.6",
                "observed_on": "2026-06-01",
                "quality_grade": "research",
                "place_guess": "Far away",
            },
            {
                "id": 2,
                "location": "41.90,-87.63",
                "observed_on": "2026-05-15",
                "quality_grade": "research",
                "place_guess": "Nearby",
            },
        ]
    }

    with patch.object(harvester.session, "get", side_effect=[taxa_resp, obs_resp]):
        result = harvester.nearest_observation("Turdus migratorius", lat=41.8781, lon=-87.6298, radius_km=160)

    assert result is not None
    assert result["observation_id"] == 2
    assert result["place_guess"] == "Nearby"
    assert result["observed_on"] == date(2026, 5, 15)
    assert result["distance_km"] < 10
    assert result["distance_miles"] < result["distance_km"]


def test_nearest_observation_none_when_empty() -> None:
    harvester = InaturalistHarvester()

    taxa_resp = MagicMock()
    taxa_resp.raise_for_status.return_value = None
    taxa_resp.json.return_value = {"results": []}

    obs_resp = MagicMock()
    obs_resp.raise_for_status.return_value = None
    obs_resp.json.return_value = {"results": []}

    with patch.object(harvester.session, "get", side_effect=[taxa_resp, obs_resp]):
        result = harvester.nearest_observation("No such species", lat=0.0, lon=0.0)

    assert result is None


def test_nearest_observation_uses_geojson_fallback() -> None:
    harvester = InaturalistHarvester()

    taxa_resp = MagicMock()
    taxa_resp.raise_for_status.return_value = None
    taxa_resp.json.return_value = {"results": [{"id": 99, "name": "Sturnella magna"}]}

    obs_resp = MagicMock()
    obs_resp.raise_for_status.return_value = None
    obs_resp.json.return_value = {
        "results": [
            {
                "id": 7,
                "geojson": {"type": "Point", "coordinates": [-87.63, 41.90]},
                "observed_on": "2026-04-01",
                "quality_grade": "research",
                "place_guess": "Prairie",
            }
        ]
    }

    with patch.object(harvester.session, "get", side_effect=[taxa_resp, obs_resp]):
        result = harvester.nearest_observation("Sturnella magna", lat=41.8781, lon=-87.6298)

    assert result is not None
    assert result["observation_id"] == 7
    assert result["observation_lat"] == 41.90
    assert result["observation_lon"] == -87.63
