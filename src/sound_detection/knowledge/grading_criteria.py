"""Grading criteria for biome summaries.

A plain dict (loaded from YAML or constructed in code). It can grow
into a small DSL later; for now it is just data that the service reads.

Example:

    clades_to_consider: all
    clades_of_interest:
      Phoenicopteriformes:
        weight: 1.5
      Otidimorphae:
        weight: 3.3
      Orthoptera:
      Turdus migratorius:
        weight: 0.3
    proximity:
      source: inaturalist
      radius_miles: 100
      quality_grade: research
    confirmation:
      min_signals: 2
"""

from __future__ import annotations

from typing import Any

DEFAULT_CRITERIA: dict[str, Any] = {
    "clades_to_consider": "all",
    "clades_of_interest": {
        # empty by default — no hardcoded owl/raptor bias
    },
    "proximity": {
        "source": "inaturalist",
        "radius_miles": 100,
        "quality_grade": "research",
    },
    "confirmation": {
        "min_signals": 2,
    },
}


def normalize_clade_name(name: str) -> str:
    """Case-insensitive match key. Species names keep their space."""
    return name.strip().lower()


def get_interest_weight(ancestry_names: list[str], criteria: dict[str, Any]) -> float:
    """Return the highest matching weight, or 1.0 if the species is in scope but unlisted.

    ancestry_names should include the species itself so a species-level
    entry (clade of size 1) matches.
    """
    interest = criteria.get("clades_of_interest") or {}
    if not interest:
        return 1.0

    names_lower = {normalize_clade_name(n) for n in ancestry_names}
    best = 1.0
    matched = False
    for clade, spec in interest.items():
        if normalize_clade_name(clade) in names_lower:
            matched = True
            weight = 1.0
            if isinstance(spec, dict):
                weight = float(spec.get("weight", 1.0))
            elif isinstance(spec, (int | float)):
                weight = float(spec)
            best = max(best, weight)
    return best if matched else 1.0


def in_scope(ancestry_names: list[str], criteria: dict[str, Any]) -> bool:
    """True if the species should be considered at all."""
    consider = criteria.get("clades_to_consider", "all")
    if consider == "all" or consider is None:
        return True
    if isinstance(consider, str):
        consider = [consider]
    names_lower = {normalize_clade_name(n) for n in ancestry_names}
    return any(normalize_clade_name(c) in names_lower for c in consider)
