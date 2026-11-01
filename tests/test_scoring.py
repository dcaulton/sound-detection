"""Unit tests for scoring helpers."""

from typing import Any

from sound_detection.knowledge.scoring import (
    bucket_taxa,
    score_taxon,
)


def test_score_taxon_basic() -> None:
    score = score_taxon("Turdus migratorius", count=10, context={"interest_weight": 1.0})
    assert score > 0
    # Log component is capped
    high = score_taxon("Something", count=10_000, context={})
    assert high <= 12.0 * 1.0 + 20  # generous upper bound with bonuses


def test_score_taxon_vagrant_bonus() -> None:
    base = score_taxon("Rare Bird", 5, {"residency_status": "resident"})
    vagrant = score_taxon("Rare Bird", 5, {"residency_status": "vagrant"})
    assert vagrant > base


def test_bucket_taxa_skips_singles_and_sorts() -> None:
    counts = {"A species": 10, "B species": 1, "C species": 50}
    contexts: dict[str, dict[str, Any]] = {
        "A species": {"common_name": "A", "interest_weight": 2.0},
        "C species": {"common_name": "C"},
    }
    buckets = bucket_taxa(counts, contexts)
    names = [r["scientific_name"] for r in buckets["table_rows"]]
    assert "B species" not in names
    assert names[0] == "C species"  # highest count
    assert buckets["dominant"]
