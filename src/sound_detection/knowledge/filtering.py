"""Criteria-driven filtering for biome summaries.

This is the place that interprets the criteria object. As the criteria
DSL grows (proximity, seasonality, quality grades, etc.), the new rules
belong here rather than in the service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from neo4j import Driver

from sound_detection.knowledge.grading_criteria import in_scope, public_criteria
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

# Why Phase 1 filtering can drop a candidate. Dry runs report these so the
# caller can see what a full run would exclude without re-running the rules.
REASON_NON_SPECIES_LABEL = "non_species_label"
REASON_BELOW_MIN_SIGNALS = "below_min_signals"
REASON_NOT_A_BINOMIAL = "not_a_binomial"
REASON_OUT_OF_TAXONOMIC_SCOPE = "out_of_taxonomic_scope"


def filter_rejection_reason(
    name: str,
    count: int,
    criteria: dict[str, Any],
    neo4j_driver: Driver | None = None,
    *,
    drop_singles: bool = False,
) -> str | None:
    """The reason this species would be dropped, or None when it is kept.

    Same rules, checked in the same order, as :func:`passes_filters` — the
    first matching reason wins, so a report names the rule that actually fired.
    """
    name_lower = name.lower().strip()
    if name_lower in NON_SPECIES_LABELS:
        return REASON_NON_SPECIES_LABEL

    min_signals = (criteria.get("confirmation") or {}).get("min_signals", 2)
    if drop_singles and count < min_signals:
        return REASON_BELOW_MIN_SIGNALS

    if " " not in name or not name[0].isupper():
        return REASON_NOT_A_BINOMIAL

    if neo4j_driver is None:
        return None

    chain = ancestry_names(neo4j_driver, name)
    if not chain:
        # Missing ancestry is treated as in-scope so we don't silently drop
        # species whose taxonomy hasn't been backfilled yet. Caller may log.
        return None

    if not in_scope(chain, criteria):
        return REASON_OUT_OF_TAXONOMIC_SCOPE
    return None


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
    reason = filter_rejection_reason(
        name,
        count,
        criteria,
        neo4j_driver,
        drop_singles=drop_singles,
    )
    return reason is None


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
    confirmed_species, speculated_species, _ = filter_species_with_report(
        confirmed_counts,
        speculated_counts,
        species_contexts,
        criteria,
        neo4j_driver,
    )
    return confirmed_species, speculated_species


def filter_species_with_report(
    confirmed_counts: dict[str, int],
    speculated_counts: dict[str, int],
    species_contexts: dict[str, dict[str, Any]],
    criteria: dict[str, Any],
    neo4j_driver: Driver | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Filter species and explain what the filters excluded.

    Returns (confirmed_species, speculated_species, filter_report). The species
    lists are identical to what filter_species returns; the report is::

        {
            "total_candidates": int,
            "kept": {"confirmed": int, "speculated": int, "total": int},
            "dropped": {"confirmed": int, "speculated": int, "total": int},
            "dropped_by_reason": {
                "confirmed": {reason: count},
                "speculated": {reason: count},
            },
            "dropped_samples": {
                "confirmed": [{"scientific_name", "count", "reason"}],
                "speculated": [...],
            },
        }

    dropped_samples is capped at max_samples per pass so the report stays small
    over a year of recordings.
    """
    confirmed_species: list[dict[str, Any]] = []
    confirmed_dropped: list[dict[str, Any]] = []
    for name, count in confirmed_counts.items():
        reason = filter_rejection_reason(name, count, criteria, neo4j_driver, drop_singles=False)
        if reason is not None:
            confirmed_dropped.append({"scientific_name": name, "count": count, "reason": reason})
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
    speculated_dropped: list[dict[str, Any]] = []
    for name, count in speculated_counts.items():
        reason = filter_rejection_reason(name, count, criteria, neo4j_driver, drop_singles=True)
        if reason is not None:
            speculated_dropped.append({"scientific_name": name, "count": count, "reason": reason})
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

    report = build_filter_report(
        confirmed_counts=confirmed_counts,
        speculated_counts=speculated_counts,
        confirmed_species=confirmed_species,
        speculated_species=speculated_species,
        confirmed_dropped=confirmed_dropped,
        speculated_dropped=speculated_dropped,
    )
    return confirmed_species, speculated_species, report


def build_filter_report(
    *,
    confirmed_counts: dict[str, int],
    speculated_counts: dict[str, int],
    confirmed_species: list[dict[str, Any]],
    speculated_species: list[dict[str, Any]],
    confirmed_dropped: list[dict[str, Any]],
    speculated_dropped: list[dict[str, Any]],
    max_samples: int = 10,
) -> dict[str, Any]:
    """Aggregate kept/dropped species (with reasons) into a JSON-safe report."""
    dropped_by_reason = {
        "confirmed": _count_by_reason(confirmed_dropped),
        "speculated": _count_by_reason(speculated_dropped),
    }
    return {
        "total_candidates": len(confirmed_counts) + len(speculated_counts),
        "kept": {
            "confirmed": len(confirmed_species),
            "speculated": len(speculated_species),
            "total": len(confirmed_species) + len(speculated_species),
        },
        "dropped": {
            "confirmed": len(confirmed_dropped),
            "speculated": len(speculated_dropped),
            "total": len(confirmed_dropped) + len(speculated_dropped),
        },
        "dropped_by_reason": dropped_by_reason,
        "dropped_samples": {
            "confirmed": confirmed_dropped[:max_samples],
            "speculated": speculated_dropped[:max_samples],
        },
    }


def _count_by_reason(dropped: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in dropped:
        reason = str(entry.get("reason", "unknown"))
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def build_dry_run_report(
    *,
    summary_id: object,
    site_id: object,
    window_days: int,
    criteria: dict[str, Any] | None,
    filter_report: dict[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    """
    Assemble the dry-run payload: the filtering report and nothing else.

    A dry run answers "what would the filters keep or throw away, and why".
    Species contexts, enrichment payloads and narrative material stay out of
    this payload — the verbose species-context dump belongs to the interactive
    run only.
    """
    public = dict(public_criteria(criteria) or {})
    # generate_summary() pops "_dry_run" off its working copy of the criteria,
    # so the payload — not the stored dict — is what records the run's kind.
    public["dry_run"] = True
    return {
        "dry_run": True,
        "summary_id": str(summary_id),
        "site_id": str(site_id),
        "window_days": window_days,
        "criteria": public,
        "filter_report": filter_report,
        "generated_at": generated_at.isoformat(),
    }
