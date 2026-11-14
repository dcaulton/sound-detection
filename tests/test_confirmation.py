"""Tests for 2-of-3 confirmation (BirdNET, Perch, proximity)."""

from __future__ import annotations

from sound_detection.knowledge.filtering import confirmation_signal_count, is_confirmed_species


def test_two_acoustic_models_confirm_without_proximity() -> None:
    signals = confirmation_signal_count(has_birdnet=True, has_perch=True, distance_miles=None, radius_miles=100)
    assert signals == 2
    assert is_confirmed_species(signals)


def test_single_model_plus_nearby_inat_confirms() -> None:
    signals = confirmation_signal_count(has_birdnet=True, has_perch=False, distance_miles=4.2, radius_miles=100)
    assert signals == 2
    assert is_confirmed_species(signals)

    signals = confirmation_signal_count(has_birdnet=False, has_perch=True, distance_miles=12.0, radius_miles=100)
    assert signals == 2
    assert is_confirmed_species(signals)


def test_all_three_signals() -> None:
    signals = confirmation_signal_count(has_birdnet=True, has_perch=True, distance_miles=1.5, radius_miles=100)
    assert signals == 3
    assert is_confirmed_species(signals)


def test_single_signal_stays_speculated() -> None:
    assert confirmation_signal_count(True, False, None, 100) == 1
    assert not is_confirmed_species(1)
    assert confirmation_signal_count(False, True, None, 100) == 1
    assert confirmation_signal_count(False, False, 5.0, 100) == 1


def test_proximity_outside_radius_does_not_count() -> None:
    signals = confirmation_signal_count(has_birdnet=True, has_perch=False, distance_miles=150.0, radius_miles=100)
    assert signals == 1
    assert not is_confirmed_species(signals)


def test_proximity_exactly_at_radius_counts() -> None:
    signals = confirmation_signal_count(has_birdnet=False, has_perch=True, distance_miles=100.0, radius_miles=100)
    assert signals == 2
    assert is_confirmed_species(signals)


def test_no_signals() -> None:
    assert confirmation_signal_count(False, False, None, 100) == 0
    assert not is_confirmed_species(0)


def test_min_signals_is_configurable() -> None:
    # A stricter bar would require all three
    assert not is_confirmed_species(2, min_signals=3)
    assert is_confirmed_species(3, min_signals=3)
