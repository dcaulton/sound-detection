"""Criteria-driven filtering for biome summaries.

This is the place that interprets the criteria object. As the criteria
DSL grows (proximity, seasonality, quality grades, etc.), the new rules
belong here rather than in the service.
"""

from __future__ import annotations

from typing import Any

import structlog
from neo4j import Driver

from sound_detection.knowledge.grading_criteria import in_scope
from sound_detection.knowledge.taxonomy import ancestry_names

log = structlog.get_logger(__name__)

NON_SPECIES_LABELS = {
    "power tools",
    "fireworks",
    "engine",
    "human vocal",
    "gun",
    "siren",
    "dog",
    "cat",
    "vehicle",
    "airplane",
    "helicopter",
    "chainsaw",
    "lawn mower",
    "human non-vocal",
    # add more as we discover them
}


def passes_filters(
    name: str,
    count: int,
    criteria: dict[str, Any],
    neo4j_driver: Driver | None = None,
    *,
    drop_singles: bool = False,
) -> bool:
    """True if the species should be kept for enrichment / scoring.

    Drop non-species labels, enforce min_signals when requested,
    require a binomial scientific name, and optionally check taxonomy scope.
    """
    name_lower = name.lower().strip()
    if name_lower in NON_SPECIES_LABELS:
        return False

    min_signals = (criteria.get("confirmation") or {}).get("min_signals", 2)
    if drop_singles and count < min_signals:
        return False

    if " " not in name or not name[0].isupper():
        return False

    if neo4j_driver is None:
        return True

    chain = ancestry_names(neo4j_driver, name)
    if not chain:
        # Missing ancestry is treated as in-scope so we don't silently drop
        # species whose taxonomy hasn't been backfilled yet. Caller may log.
        return True

    return in_scope(chain, criteria)


def proximity_band(
    distance_km: float | None,
    near_km: float,
    far_km: float,
) -> str:
    """Classify a nearest-iNat distance. Inputs are kilometers.

    near     (<= near_km): local. Verifies a single acoustic model.
    mid      (near < d < far): ignored.
    far      (>= far_km): out of known range.
    not_found (None): lookup ran and found nothing in the search radius.
              Treated as not-local, same as far, for the unexpected flag.
    """
    if distance_km is None:
        return "not_found"
    if distance_km <= near_km:
        return "near"
    if distance_km >= far_km:
        return "far"
    return "mid"


def is_local(distance_km: float | None, near_km: float) -> bool:
    """True when iNat has a research-grade observation within the near band."""
    return proximity_band(distance_km, near_km, near_km * 5) == "near"


def confirmation_signal_count(
    has_birdnet: bool,
    has_perch: bool,
    distance_km: float | None,
    near_km: float,
    far_km: float,
) -> int:
    """Confirming signals: BirdNET, Perch, and a local iNat observation.

    A far or missing observation does not confirm. The mid band is ignored.
    """
    signals = int(has_birdnet) + int(has_perch)
    if proximity_band(distance_km, near_km, far_km) == "near":
        signals += 1
    return signals


def is_unexpected(
    has_birdnet: bool,
    has_perch: bool,
    distance_km: float | None,
    near_km: float,
    far_km: float,
) -> bool:
    """Both models agree, and iNat does not place the species nearby.

    Far (>= far_km) or not_found (no observation in the search radius) both
    count. This is how a European warbler with no local iNat record is flagged,
    while Anna's at 30 miles is not.
    """
    if not (has_birdnet and has_perch):
        return False
    band = proximity_band(distance_km, near_km, far_km)
    return band in {"far", "not_found"}


def is_confirmed_species(signal_count: int, min_signals: int = 2) -> bool:
    """True when the species has enough independent signals to be confirmed."""
    return signal_count >= min_signals


def filter_species(
    confirmed_counts: dict[str, int],
    speculated_counts: dict[str, int],
    species_contexts: dict[str, dict[str, Any]],
    criteria: dict[str, Any],
    neo4j_driver: Driver | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply criteria filters and return (confirmed_species, speculated_species).

    Confirmed detections keep singles (agreement is already a strong signal).
    Speculated detections drop anything below confirmation.min_signals.
    """
    confirmed_species: list[dict[str, Any]] = []
    for name, count in confirmed_counts.items():
        if not passes_filters(name, count, criteria, neo4j_driver, drop_singles=False):
            continue
        if neo4j_driver is not None and not ancestry_names(neo4j_driver, name):
            log.warning("no_taxonomy_ancestry", species=name)
        confirmed_species.append(
            {
                "scientific_name": name,
                "count": count,
                "confirmation": "confirmed",
                "context": species_contexts.get(name, {}),
            }
        )

    speculated_species: list[dict[str, Any]] = []
    for name, count in speculated_counts.items():
        if not passes_filters(name, count, criteria, neo4j_driver, drop_singles=True):
            continue
        if neo4j_driver is not None and not ancestry_names(neo4j_driver, name):
            log.warning("no_taxonomy_ancestry", species=name)
        speculated_species.append(
            {
                "scientific_name": name,
                "count": count,
                "confirmation": "speculated",
                "context": species_contexts.get(name, {}),
            }
        )

    return confirmed_species, speculated_species
