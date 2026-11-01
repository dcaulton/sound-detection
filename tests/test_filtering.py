"""Tests for criteria-driven filtering."""

from __future__ import annotations

from sound_detection.knowledge.filtering import filter_species, passes_filters


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
