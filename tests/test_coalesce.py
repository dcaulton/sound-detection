"""Unit tests for detection coalescence (adjacent + cross-model)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from sound_detection.api.v1.routers.detections import (  # or wherever you put them
    coalesce_across_models,
    coalesce_adjacent,
)

# Adjust these imports to match your project
from sound_detection.schemas.detection import Detection


def _det(
    *,
    species: str = "Cardinalis cardinalis",
    model: str,
    start: float,
    end: float,
    confidence: float = 0.8,
    common_name: str | None = None,
) -> Detection:
    """Minimal Detection factory for coalescence tests."""
    kwargs: dict[str, Any] = {
        "species": species,
        "scientific_name": species,
        "common_name": common_name or species,
        "confidence": confidence,
        "start_offset": start,
        "end_offset": end,
        "model": model,
        "confirmed_group_id": None,
    }
    # If your schema requires more fields, add defaults here
    return Detection(**kwargs)


# ---------------------------------------------------------------------------
# coalesce_adjacent
# ---------------------------------------------------------------------------


def test_coalesce_adjacent_merges_touching_perch_windows() -> None:
    """Twelve 5s Perch windows of the same species → one span."""
    dets = [
        _det(model="perch", start=float(i), end=float(i + 5), confidence=0.5 + idx * 0.02)
        for idx, i in enumerate(range(0, 60, 5))
    ]
    assert len(dets) == 12

    merged = coalesce_adjacent(dets)

    assert len(merged) == 1
    m = merged[0]
    assert m.model == "perch"
    assert m.start_offset == 0.0
    assert m.end_offset == 60.0
    assert m.confidence == pytest.approx(0.5 + 11 * 0.02)  # max confidence


def test_coalesce_adjacent_does_not_merge_across_gap() -> None:
    dets = [
        _det(model="perch", start=0.0, end=5.0),
        _det(model="perch", start=10.0, end=15.0),  # 5s gap > default max_gap
    ]
    merged = coalesce_adjacent(dets, max_gap_s=0.35)
    assert len(merged) == 2


def test_coalesce_adjacent_does_not_merge_different_species() -> None:
    dets = [
        _det(species="Cardinalis cardinalis", model="perch", start=0.0, end=5.0),
        _det(species="Turdus migratorius", model="perch", start=4.0, end=9.0),
    ]
    merged = coalesce_adjacent(dets)
    assert len(merged) == 2


def test_coalesce_adjacent_does_not_merge_different_models() -> None:
    """Adjacent merge is per-model; BirdNET + Perch stay separate here."""
    dets = [
        _det(model="birdnet", start=0.0, end=3.0),
        _det(model="perch", start=0.0, end=5.0),
    ]
    # If your coalesce_adjacent buckets by (model, species), this stays 2
    merged = coalesce_adjacent(dets)
    assert len(merged) == 2


def test_coalesce_adjacent_empty() -> None:
    assert coalesce_adjacent([]) == []


# ---------------------------------------------------------------------------
# coalesce_across_models
# ---------------------------------------------------------------------------


def test_coalesce_across_models_links_contained_intervals() -> None:
    """BirdNET window fully inside Perch span → shared confirmed_group_id."""
    birdnet = _det(
        model="birdnet",
        start=663.0,
        end=666.0,
        confidence=0.67,
        common_name="Northern Cardinal",
    )
    perch = _det(
        model="perch",
        start=640.0,
        end=680.0,
        confidence=0.88,
    )
    result = coalesce_across_models([birdnet, perch])

    assert result[0].confirmed_group_id is not None
    assert result[0].confirmed_group_id == result[1].confirmed_group_id
    assert isinstance(result[0].confirmed_group_id, uuid.UUID)


def test_coalesce_across_models_no_link_without_overlap() -> None:
    birdnet = _det(model="birdnet", start=0.0, end=3.0)
    perch = _det(model="perch", start=20.0, end=25.0)
    result = coalesce_across_models([birdnet, perch])

    assert result[0].confirmed_group_id is None
    assert result[1].confirmed_group_id is None


def test_coalesce_across_models_same_model_not_confirmed() -> None:
    """Two BirdNET-only rows: no cross-model confirmation."""
    a = _det(model="birdnet", start=0.0, end=3.0)
    b = _det(model="birdnet", start=2.0, end=5.0)
    result = coalesce_across_models([a, b])

    assert result[0].confirmed_group_id is None
    assert result[1].confirmed_group_id is None


def test_coalesce_across_models_different_species_not_linked() -> None:
    birdnet = _det(species="Cardinalis cardinalis", model="birdnet", start=0.0, end=3.0)
    perch = _det(species="Turdus migratorius", model="perch", start=0.0, end=5.0)
    result = coalesce_across_models([birdnet, perch])

    assert all(d.confirmed_group_id is None for d in result)


def test_pipeline_adjacent_then_across_models() -> None:
    """Realistic path: merge Perch windows, then confirm against BirdNET."""
    perch_raw = [
        _det(model="perch", start=640.0, end=645.0, confidence=0.7),
        _det(model="perch", start=645.0, end=650.0, confidence=0.88),
        _det(model="perch", start=650.0, end=655.0, confidence=0.8),
    ]
    birdnet = [
        _det(model="birdnet", start=646.0, end=649.0, confidence=0.66),
    ]

    perch = coalesce_adjacent(perch_raw)
    assert len(perch) == 1
    assert perch[0].start_offset == 640.0
    assert perch[0].end_offset == 655.0

    all_dets = coalesce_across_models(birdnet + perch)
    group_ids = {d.confirmed_group_id for d in all_dets}
    assert len(group_ids) == 1
    assert None not in group_ids
