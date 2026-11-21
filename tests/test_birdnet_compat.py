"""BirdNET-Go compatibility helpers."""

from datetime import UTC, datetime

from sound_detection.api.v1.routers.birdnet_compat import (
    _parse_day,
    _window,
    is_binomial,
    parse_clades,
    passes_clades,
    passes_gate,
)


def test_parse_day() -> None:
    assert _parse_day(None) is None
    assert _parse_day("2026-07-01") == datetime(2026, 7, 1, tzinfo=UTC)
    assert _parse_day("not-a-date") is None


def test_window_end_is_exclusive() -> None:
    start, end = _window("2026-07-01", "2026-07-30")
    assert start == datetime(2026, 7, 1, tzinfo=UTC)
    assert end == datetime(2026, 7, 31, tzinfo=UTC)


def test_window_all_time() -> None:
    assert _window(None, None) == (None, None)


def test_binomial_keeps_species() -> None:
    assert is_binomial("Turdus migratorius")
    assert is_binomial("Calypte anna")


def test_binomial_drops_noise() -> None:
    assert not is_binomial("Engine")
    assert not is_binomial("Dog")
    assert not is_binomial("Walk_and_footsteps")
    assert not is_binomial("Chime")
    assert not is_binomial("")


def test_gate_confirmed_needs_both_models() -> None:
    assert passes_gate("confirmed", True, True, None)
    assert not passes_gate("confirmed", True, False, 10.0)
    assert passes_gate("nope", True, True, None)  # unknown falls back to confirmed


def test_gate_local_needs_a_model_and_nearby_inat() -> None:
    assert passes_gate("local", True, False, 20.0)
    assert not passes_gate("local", True, True, 500.0)
    assert not passes_gate("local", False, False, 5.0)


def test_gate_rare_is_both_models_and_not_local() -> None:
    assert passes_gate("rare", True, True, None)
    assert passes_gate("rare", True, True, 900.0)
    assert not passes_gate("rare", True, True, 30.0)
    assert not passes_gate("rare", True, False, None)


def test_gate_all_keeps_a_single_model() -> None:
    assert passes_gate("all", True, False, None)
    assert passes_gate("all", False, True, 1000.0)


def test_parse_clades() -> None:
    assert parse_clades("Turdus, Strix, -Insecta") == (["Turdus", "Strix"], ["Insecta"])
    assert parse_clades(None) == ([], [])
    assert parse_clades("") == ([], [])


def test_passes_clades_prefix_and_ancestry() -> None:
    ancestry = ["Calypte anna", "Trochilidae", "Apodiformes", "Aves"]
    assert passes_clades("Calypte anna", ["Calypte"], [], ancestry)
    assert passes_clades("Calypte anna", ["Aves"], [], ancestry)
    assert not passes_clades("Calypte anna", ["Turdus"], [], ancestry)
    assert not passes_clades("Calypte anna", [], ["Apodiformes"], ancestry)
    assert passes_clades("Calypte anna", [], [], ancestry)
