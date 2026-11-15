"""Tests for proximity bands and the unexpected flag."""

from __future__ import annotations

from sound_detection.knowledge.filtering import (
    confirmation_signal_count,
    is_unexpected,
    proximity_band,
)


def test_near_band_is_verifying() -> None:
    assert proximity_band(4.2) == "near"
    assert proximity_band(100) == "near"
    # single model + near iNat is two signals
    assert confirmation_signal_count(True, False, 12.0, 100) == 2


def test_mid_band_is_ignored() -> None:
    assert proximity_band(250) == "mid"
    assert proximity_band(499) == "mid"
    # mid does not confirm a single model
    assert confirmation_signal_count(True, False, 250, 100) == 1
    assert not is_unexpected(True, True, 250)


def test_far_band_with_both_models_is_unexpected() -> None:
    assert proximity_band(800) == "far"
    # far does not confirm
    assert confirmation_signal_count(True, True, 800, 100) == 2
    assert is_unexpected(True, True, 800)
    # far + only one model is not the unexpected flag
    assert not is_unexpected(True, False, 800)


def test_unknown_proximity() -> None:
    assert proximity_band(None) == "unknown"
    assert confirmation_signal_count(True, True, None, 100) == 2
    assert not is_unexpected(True, True, None)
