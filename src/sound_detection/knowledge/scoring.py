"""Scoring and bucketing for biome summaries.

Kept separate from BiomeSummaryService so the service can stay focused on
orchestration (SQL → enrich → narrate → persist).
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, TypedDict


class ScoredTaxon(TypedDict):
    scientific_name: str
    common_name: str
    count: int
    score: float
    clade: str | None
    context: dict[str, Any]


def score_taxon(
    scientific_name: str,
    count: int,
    context: dict[str, Any] | None = None,
    current_month: int | None = None,
) -> float:
    """Deterministic interestingness score. Higher = more worth highlighting."""
    context = context or {}
    score = 0.0

    if current_month is None:
        current_month = datetime.now().month

    score += min(math.log1p(count) * 2.5, 12.0)

    weight = float(context.get("interest_weight") or 1.0)
    score *= weight

    if context.get("recorded_in_illinois") is False:
        score += 6.0

    residency = (context.get("residency_status") or "").lower()
    if any(k in residency for k in ("vagrant", "rare", "accidental")):
        score += 5.0
    if "migrant" in residency:
        score += 2.0

    peak_months: list[int] = context.get("migration_peak_months") or context.get("peak_months") or []
    if peak_months and current_month not in peak_months:
        score += 4.0

    if context.get("is_indicator") or context.get("indicator_for_habitats"):
        score += 7.0

    return round(score, 2)


def bucket_taxa(
    taxon_counts: dict[str, int],
    taxon_contexts: dict[str, dict[str, Any]],
    current_month: int | None = None,
) -> dict[str, list[ScoredTaxon]]:
    scored: list[ScoredTaxon] = []
    for name, count in taxon_counts.items():
        if count <= 1:
            continue

        context = taxon_contexts.get(name, {})
        score = score_taxon(name, count, context, current_month)
        common_name = context.get("common_name") or ""

        scored.append(
            {
                "scientific_name": name,
                "common_name": common_name,
                "count": count,
                "score": score,
                "clade": context.get("matched_clade"),
                "context": context,
            }
        )

    by_score = sorted(scored, key=lambda x: x["score"], reverse=True)
    by_count = sorted(scored, key=lambda x: x["count"], reverse=True)

    return {
        "table_rows": by_count,
        "high_interest": [s for s in by_score if s["score"] >= 12][:12],
        "rare_vagrant": [
            s
            for s in by_score
            if s["count"] <= 4 and (s["context"].get("recorded_in_illinois") is False or s["score"] >= 10)
        ][:10],
        "dominant": by_count[:8],
    }
