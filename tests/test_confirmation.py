"""Tests for 2-of-3 confirmation (BirdNET, Perch, proximity).

Distances are kilometers. 160 km is about 100 miles.
"""

from __future__ import annotations

from sound_detection.knowledge.filtering import confirmation_signal_count, is_confirmed_species

NEAR = 160.0
FAR = 800.0


def test_two_acoustic_models_confirm_without_proximity() -> None:
    signals = confirmation_signal_count(has_birdnet=True, has_perch=True, distance_km=None, near_km=NEAR, far_km=FAR)
    assert signals == 2
    assert is_confirmed_species(signals)


def test_single_model_plus_nearby_inat_confirms() -> None:
    signals = confirmation_signal_count(has_birdnet=True, has_perch=False, distance_km=7.0, near_km=NEAR, far_km=FAR)
    assert signals == 2
    assert is_confirmed_species(signals)

    signals = confirmation_signal_count(has_birdnet=False, has_perch=True, distance_km=20.0, near_km=NEAR, far_km=FAR)
    assert signals == 2
    assert is_confirmed_species(signals)


def test_all_three_signals() -> None:
    signals = confirmation_signal_count(has_birdnet=True, has_perch=True, distance_km=2.5, near_km=NEAR, far_km=FAR)
    assert signals == 3
    assert is_confirmed_species(signals)


def test_single_signal_stays_speculated() -> None:
    assert confirmation_signal_count(True, False, None, NEAR, FAR) == 1
    assert not is_confirmed_species(1)
    assert confirmation_signal_count(False, True, None, NEAR, FAR) == 1
    assert confirmation_signal_count(False, False, 8.0, NEAR, FAR) == 1


def test_proximity_outside_radius_does_not_count() -> None:
    signals = confirmation_signal_count(has_birdnet=True, has_perch=False, distance_km=240.0, near_km=NEAR, far_km=FAR)
    assert signals == 1
    assert not is_confirmed_species(signals)


def test_proximity_exactly_at_radius_counts() -> None:
    signals = confirmation_signal_count(has_birdnet=False, has_perch=True, distance_km=160.0, near_km=NEAR, far_km=FAR)
    assert signals == 2
    assert is_confirmed_species(signals)


def test_no_signals() -> None:
    assert confirmation_signal_count(False, False, None, NEAR, FAR) == 0
    assert not is_confirmed_species(0)


def test_min_signals_is_configurable() -> None:
    assert not is_confirmed_species(2, min_signals=3)
    assert is_confirmed_species(3, min_signals=3)
