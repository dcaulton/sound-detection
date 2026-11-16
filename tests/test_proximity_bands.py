"""Tests for proximity bands and the unexpected flag.

Distances are kilometers. 160 km is about 100 miles; 800 km is about 500 miles.
"""

from __future__ import annotations

from sound_detection.knowledge.filtering import (
    confirmation_signal_count,
    is_local,
    is_unexpected,
    proximity_band,
)

NEAR = 160.0
FAR = 800.0


def test_near_band_is_verifying() -> None:
    assert proximity_band(7.0, NEAR, FAR) == "near"
    assert proximity_band(160.0, NEAR, FAR) == "near"
    assert is_local(48.0, NEAR)
    # single model + local iNat is two signals
    assert confirmation_signal_count(True, False, 20.0, NEAR, FAR) == 2


def test_mid_band_is_ignored() -> None:
    assert proximity_band(400.0, NEAR, FAR) == "mid"
    assert confirmation_signal_count(True, False, 400.0, NEAR, FAR) == 1
    assert not is_unexpected(True, True, 400.0, NEAR, FAR)


def test_far_band_with_both_models_is_unexpected() -> None:
    assert proximity_band(900.0, NEAR, FAR) == "far"
    assert confirmation_signal_count(True, True, 900.0, NEAR, FAR) == 2
    assert is_unexpected(True, True, 900.0, NEAR, FAR)
    assert not is_unexpected(True, False, 900.0, NEAR, FAR)


def test_not_found_is_unexpected_when_both_models_agree() -> None:
    # Lookup ran, nothing in radius. Savi's Warbler case.
    assert proximity_band(None, NEAR, FAR) == "not_found"
    assert not is_local(None, NEAR)
    assert is_unexpected(True, True, None, NEAR, FAR)
    assert not is_unexpected(True, False, None, NEAR, FAR)
