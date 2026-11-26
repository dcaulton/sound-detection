"""Tests for criteria-driven filtering."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from unittest.mock import patch
from uuid import UUID

from neo4j import Driver

from sound_detection.knowledge.filtering import (
    build_dry_run_report,
    filter_rejection_reason,
    filter_species,
    filter_species_with_report,
    passes_filters,
)
from sound_detection.knowledge.grading_criteria import public_criteria


def _stub_driver() -> Driver:
    """Stand-in driver for the taxonomy scope check.

    The tests that use it patch ``ancestry_names``, so the driver is only ever
    passed through — it is never asked for a session.
    """
    return cast(Driver, object())


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


def test_filter_species_confirmed_keeps_singles_speculated_drops() -> None:
    criteria = {"confirmation": {"min_signals": 2}, "clades_to_consider": "all"}
    confirmed = {"Turdus migratorius": 1, "dog": 10, "Sturnella magna": 4}
    speculated = {"Cathartes aura": 1, "Buteo jamaicensis": 3, "engine": 5}
    contexts = {
        "Turdus migratorius": {"common_name": "American Robin"},
        "Sturnella magna": {"common_name": "Eastern Meadowlark"},
        "Buteo jamaicensis": {"common_name": "Red-tailed Hawk"},
    }

    confirmed_species, speculated_species = filter_species(confirmed, speculated, contexts, criteria, neo4j_driver=None)

    confirmed_names = {s["scientific_name"] for s in confirmed_species}
    speculated_names = {s["scientific_name"] for s in speculated_species}

    # Confirmed: singles kept, non-species dropped
    assert confirmed_names == {"Turdus migratorius", "Sturnella magna"}
    # Speculated: below min_signals dropped, non-species dropped
    assert speculated_names == {"Buteo jamaicensis"}

    robin = next(s for s in confirmed_species if s["scientific_name"] == "Turdus migratorius")
    assert robin["confirmation"] == "confirmed"
    assert robin["context"]["common_name"] == "American Robin"


def test_rejection_reasons_are_stable() -> None:
    criteria = {"confirmation": {"min_signals": 2}, "clades_to_consider": "all"}

    assert filter_rejection_reason("dog", 5, criteria) == "non_species_label"
    assert filter_rejection_reason("Turdus migratorius", 1, criteria, drop_singles=True) == "below_min_signals"
    assert filter_rejection_reason("Turdus migratorius", 1, criteria, drop_singles=False) is None
    assert filter_rejection_reason("robin", 5, criteria) == "not_a_binomial"
    assert filter_rejection_reason("Turdus migratorius", 5, criteria) is None


def test_rejection_reason_reports_out_of_scope_taxa() -> None:
    driver = _stub_driver()
    criteria = {"confirmation": {"min_signals": 2}, "clades_to_consider": ["Anseriformes"]}

    def fake_ancestry(_driver: object, name: str) -> list[str]:
        return ["Aves", "Anseriformes"] if name == "Anas platyrhynchos" else ["Aves", "Passeriformes"]

    with patch("sound_detection.knowledge.filtering.ancestry_names", side_effect=fake_ancestry):
        assert filter_rejection_reason("Anas platyrhynchos", 5, criteria, driver) is None
        assert filter_rejection_reason("Passer domesticus", 5, criteria, driver) == "out_of_taxonomic_scope"


def test_missing_taxonomy_is_kept_and_in_scope() -> None:
    criteria = {"confirmation": {"min_signals": 2}, "clades_to_consider": ["Anseriformes"]}
    with patch("sound_detection.knowledge.filtering.ancestry_names", return_value=[]):
        assert filter_rejection_reason("Turdus migratorius", 5, criteria, _stub_driver()) is None


def test_filter_species_with_report_accounts_for_every_candidate() -> None:
    criteria = {"confirmation": {"min_signals": 2}, "clades_to_consider": "all"}
    confirmed = {"Turdus migratorius": 1, "dog": 10, "Sturnella magna": 4}
    speculated = {"Cathartes aura": 1, "Buteo jamaicensis": 3, "engine": 5}
    contexts: dict[str, dict] = {}

    confirmed_species, speculated_species, report = filter_species_with_report(
        confirmed, speculated, contexts, criteria, neo4j_driver=None
    )

    assert {s["scientific_name"] for s in confirmed_species} == {"Turdus migratorius", "Sturnella magna"}
    assert {s["scientific_name"] for s in speculated_species} == {"Buteo jamaicensis"}

    assert report["total_candidates"] == 6
    assert report["kept"]["total"] == 3
    assert report["dropped"]["total"] == 3
    assert report["dropped"]["confirmed"] == 1
    assert report["dropped"]["speculated"] == 2
    assert report["dropped_by_reason"]["confirmed"] == {"non_species_label": 1}
    assert report["dropped_by_reason"]["speculated"] == {"below_min_signals": 1, "non_species_label": 1}

    kept = len(confirmed_species) + len(speculated_species)
    dropped = len(report["dropped_samples"]["confirmed"]) + len(report["dropped_samples"]["speculated"])
    assert kept + dropped == report["total_candidates"]

    dog = next(s for s in report["dropped_samples"]["confirmed"] if s["scientific_name"] == "dog")
    assert dog["reason"] == "non_species_label"
    assert dog["count"] == 10
    # Reports are name/count accounting — no enrichment payload rides along.
    assert "context" not in dog


def test_dry_run_report_records_its_own_kind_after_the_internal_key_is_popped() -> None:
    # generate_summary() pops "_dry_run" off its working copy of the criteria
    # before building the payload, so the report cannot rely on seeing it.
    report = build_dry_run_report(
        summary_id=UUID(int=0),
        site_id=UUID(int=1),
        window_days=30,
        criteria={},
        filter_report={"kept": {"total": 0}},
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert report["dry_run"] is True
    assert report["criteria"] == {"dry_run": True}
    json.dumps(report)


def test_build_dry_run_report_is_a_concise_filtering_accounting() -> None:
    criteria = {"confirmation": {"min_signals": 2}, "_dry_run": True, "_start_date": "2026-01-01"}
    confirmed_species, speculated_species, report = filter_species_with_report(
        {"Turdus migratorius": 1, "dog": 10},
        {"Cathartes aura": 2},
        {"Turdus migratorius": {"common_name": "American Robin", "wikipedia_summary": "long prose"}},
        {"confirmation": {"min_signals": 2}, "clades_to_consider": "all"},
        neo4j_driver=None,
    )

    payload = build_dry_run_report(
        summary_id=UUID(int=1),
        site_id=UUID(int=2),
        window_days=30,
        criteria=criteria,
        filter_report=report,
        generated_at=datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC),
    )

    assert confirmed_species and speculated_species
    assert payload["dry_run"] is True
    assert payload["summary_id"] == str(UUID(int=1))
    assert payload["site_id"] == str(UUID(int=2))
    assert payload["window_days"] == 30
    assert payload["generated_at"] == "2026-01-31T12:00:00+00:00"
    # Criteria come back as a documented field rather than internal storage keys.
    assert payload["criteria"]["dry_run"] is True
    assert payload["criteria"]["start_date"] == "2026-01-01"
    assert "_dry_run" not in payload["criteria"]
    assert "_start_date" not in payload["criteria"]
    assert payload["filter_report"] == report
    # The verbose species-context blob is not part of the dry-run contract.
    assert "species_contexts" not in payload
    assert "wikipedia_summary" not in json.dumps(payload)


def test_public_criteria_promotes_internal_run_keys() -> None:
    promoted = public_criteria({"clades_to_consider": "all", "_dry_run": True, "_start_date": "2026-01-01"})
    assert promoted == {"clades_to_consider": "all", "dry_run": True, "start_date": "2026-01-01"}
    assert public_criteria(None) == {}
    assert public_criteria({"clades_to_consider": "all"}) == {"clades_to_consider": "all"}


def test_dry_run_report_carries_no_enrichment_context() -> None:
    report = {
        "total_candidates": 2,
        "kept": {"confirmed": 1, "speculated": 0, "total": 1},
        "dropped": {"confirmed": 0, "speculated": 1, "total": 1},
        "dropped_by_reason": {"confirmed": {}, "speculated": {"non_species_label": 1}},
        "dropped_samples": {
            "confirmed": [],
            "speculated": [{"scientific_name": "engine", "count": 4, "reason": "non_species_label"}],
        },
    }
    payload = build_dry_run_report(
        summary_id=UUID(int=3),
        site_id=UUID(int=4),
        window_days=7,
        criteria={"_dry_run": True},
        filter_report=report,
        generated_at=datetime(2026, 1, 31, tzinfo=UTC),
    )
    assert payload["filter_report"]["dropped_samples"]["speculated"][0]["reason"] == "non_species_label"
    dumped = json.dumps(payload)
    # Enrichment prose and context never ride along in a dry-run payload.
    assert "wikipedia_summary" not in dumped
    assert "common_name" not in dumped
