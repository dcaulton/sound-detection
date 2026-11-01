"""Unit tests for scoring and filtering helpers."""

from typing import Any

from sound_detection.knowledge.scoring import (
    bucket_taxa,
    passes_filters,
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


def test_passes_filters_drops_non_species() -> None:
    criteria = {"confirmation": {"min_signals": 2}, "clades_to_consider": "all"}
    assert not passes_filters("dog", 5, criteria, drop_singles=False)
    assert not passes_filters("power tools", 3, criteria, drop_singles=False)


def test_passes_filters_requires_binomial() -> None:
    criteria = {"confirmation": {"min_signals": 2}}
    assert not passes_filters("robin", 5, criteria)  # no space / not capitalized
    assert passes_filters("Turdus migratorius", 5, criteria, neo4j_driver=None)


def test_passes_filters_min_signals() -> None:
    criteria = {"confirmation": {"min_signals": 3}}
    assert passes_filters("Turdus migratorius", 1, criteria, drop_singles=False)
    assert not passes_filters("Turdus migratorius", 1, criteria, drop_singles=True)
    assert passes_filters("Turdus migratorius", 5, criteria, drop_singles=True)


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
