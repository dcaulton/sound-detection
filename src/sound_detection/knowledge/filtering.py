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
