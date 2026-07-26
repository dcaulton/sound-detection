"""Perch v2 inference — 5s windows @ 32 kHz."""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import tensorflow as tf  # type: ignore[import-untyped]

from sound_detection.schemas.detection import AnalyzeAudioResponse, Detection

log = logging.getLogger(__name__)

SAMPLE_RATE = 32_000
WINDOW_SAMPLES = 160_000  # 5.0 s
WINDOW_S = WINDOW_SAMPLES / SAMPLE_RATE
HOP_S = 5.0  # non-overlapping for v1; can overlap later


# ml/perch_inference.py → ml/
_ML_DIR = Path(__file__).resolve().parent

# SavedModel directory (contains saved_model.pb + variables/ + assets/)
PERCH_MODEL_DIR = _ML_DIR / "perch"

# Labels shipped with the model
PERCH_LABELS_PATH = PERCH_MODEL_DIR / "assets" / "labels.csv"
PERCH_EBIRD_CLASSES_PATH = PERCH_MODEL_DIR / "assets" / "perch_v2_ebird_classes.csv"


# Official Perch v2 CPU SavedModel on Kaggle Models / TF-Hub style URL
PERCH_MODEL_URL = (
    "https://www.kaggle.com/models/google/bird-vocalization-classifier/"
    "frameworks/TensorFlow2/variations/perch_v2_cpu/versions/1"
)

# Ship or download labels next to the model; path configurable
DEFAULT_LABELS_PATH = Path(__file__).resolve().parent / "perch_labels.csv"


@dataclass
class PerchDetection:
    scientific_name: str
    common_name: str | None
    confidence: float
    start_offset: float  # seconds into the file
    end_offset: float
    model: str = "perch"


@lru_cache(maxsize=1)
def _load_model() -> Any | None:
    if not (PERCH_MODEL_DIR / "saved_model.pb").exists():
        log.error(f"Perch SavedModel not found at {PERCH_MODEL_DIR}. Expected saved_model.pb in that directory.")
        return None
    log.info("Loading Perch SavedModel from %s", PERCH_MODEL_DIR)
    model = tf.saved_model.load(str(PERCH_MODEL_DIR))
    if hasattr(model, "signatures") and model.signatures:
        sig = model.signatures.get("serving_default")
        if sig is None:
            sig = next(iter(model.signatures.values()))
        return sig
    return model


@lru_cache(maxsize=1)
def _load_labels() -> list[dict] | None:
    path = PERCH_LABELS_PATH
    if not path.exists():
        log.error(f"Perch labels not found: {path}")
        return None

    labels: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if not name:
            continue
        if name == "inat2024_fsd50k":
            continue
        labels.append({"scientific_name": name, "common_name": None})

    log.info("Loaded %d Perch labels from %s", len(labels), path)
    return labels


def _load_audio_mono_32k(audio_bytes: bytes) -> np.ndarray:
    """Decode arbitrary audio bytes → mono float32 @ 32 kHz."""
    y, _ = librosa.load(io.BytesIO(audio_bytes), sr=SAMPLE_RATE, mono=True)
    return y.astype(np.float32)


def _window_audio(y: np.ndarray) -> list[tuple[float, np.ndarray]]:
    """Yield (start_offset_s, window) for each 5 s chunk. Pad last window if short."""
    windows: list[tuple[float, np.ndarray]] = []
    hop = int(HOP_S * SAMPLE_RATE)
    if len(y) == 0:
        return windows

    for start in range(0, max(len(y), 1), hop):
        chunk = y[start : start + WINDOW_SAMPLES]
        if len(chunk) < WINDOW_SAMPLES:
            if len(chunk) < SAMPLE_RATE * 0.5:
                # skip tiny trailing sliver
                break
            chunk = np.pad(chunk, (0, WINDOW_SAMPLES - len(chunk)))
        windows.append((start / SAMPLE_RATE, chunk))
    return windows


def _scores_from_output(out: Any) -> np.ndarray:
    """Normalize TF output dict/tensor → 1D score vector."""
    if isinstance(out, dict):
        # Common keys across Perch versions
        for key in ("label", "probabilities", "scores", "logits", "output_0"):
            if key in out:
                t = out[key]
                break
        else:
            # first tensor-like value
            t = next(iter(out.values()))
    else:
        t = out

    arr = np.asarray(t).squeeze()
    if arr.ndim > 1:
        arr = arr[0]
    # If logits, convert to probabilities
    if arr.min() < 0 or arr.max() > 1.5:
        arr = tf.nn.softmax(arr).numpy()
    return arr.astype(np.float32)


def analyze_with_perch(
    audio_bytes: bytes,
    filename: str | None,
    min_confidence: float = 0.25,
    top_k: int = 5,
    labels_path: str | None = None,
) -> AnalyzeAudioResponse:
    """
    Run Perch on an audio file (bytes).
    Returns detections compatible with your Detection rows (model='perch').
    """
    start_time = time.perf_counter()
    y = _load_audio_mono_32k(audio_bytes)
    windows = _window_audio(y)
    if not windows:
        return AnalyzeAudioResponse(
            detections=[],
            file_duration=0,
            processing_time_seconds=round(time.perf_counter() - start_time, 3),
        )

    model = _load_model()
    labels = _load_labels()
    if model is None or labels is None:  # gracefully return no detections if the model isn't present
        return AnalyzeAudioResponse(
            detections=[],
            file_duration=0,
            processing_time_seconds=round(time.perf_counter() - start_time, 3),
        )
    detections: list[Detection] = []

    for start_s, chunk in windows:
        # Model input: [batch, 160000]
        inp = tf.constant(chunk.reshape(1, -1), dtype=tf.float32)

        out = model(inputs=inp)
        scores = _scores_from_output(out)

        if scores.shape[0] > len(labels):
            scores = scores[: len(labels)]
        elif scores.shape[0] < len(labels):
            log.warning(
                "Score dim %s < label count %s — truncating labels",
                scores.shape[0],
                len(labels),
            )

        top_idx = np.argsort(scores)[::-1][:top_k]
        for idx in top_idx:
            conf = float(scores[idx])
            if conf < min_confidence:
                continue
            meta = (
                labels[int(idx)]
                if int(idx) < len(labels)
                else {
                    "scientific_name": f"class_{idx}",
                    "common_name": None,
                }
            )
            sci = meta["scientific_name"]
            if not sci or sci.lower() in {"inat2024_fsd50k", "nocall", "no call", "background"}:
                continue
            detections.append(
                Detection(
                    species=sci,
                    common_name="NEEDS COMMON NAME",
                    scientific_name=sci,
                    confidence=conf,
                    start_offset=start_s,
                    end_offset=start_s + WINDOW_S,
                    model="perch",
                )
            )

    log.info("Perch produced %d detections (min_confidence=%.2f)", len(detections), min_confidence)
    # compute duration from audio length
    duration = len(y) / SAMPLE_RATE
    return AnalyzeAudioResponse(
        detections=detections,
        file_duration=duration,
        processing_time_seconds=round(time.perf_counter() - start_time, 3),
    )
