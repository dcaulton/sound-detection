"""Bioacoustics inference service using BirdNET."""

import datetime
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

import structlog
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer
from birdnetlib.exceptions import AudioFormatError

from sound_detection.core.config import settings
from sound_detection.schemas.detection import AnalyzeAudioResponse, Detection

log = structlog.get_logger()

# Singleton analyzer (loads model once at startup)
_analyzer: Analyzer | None = None


def get_analyzer() -> Analyzer:
    """Lazy-load and cache the BirdNET analyzer."""
    global _analyzer
    if _analyzer is None:
        log.info("Loading BirdNET analyzer (this happens once)...")
        _analyzer = Analyzer()
        log.info("BirdNET analyzer ready")
    return _analyzer


def analyze_audio(
    audio_bytes: bytes,
    filename: str,
    mic_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    recording_date: datetime.datetime | None = None,
) -> AnalyzeAudioResponse:
    """Analyze audio file and return detections."""
    start_time = time.perf_counter()

    with NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(audio_bytes)

    try:
        analyzer = get_analyzer()

        recording = Recording(
            analyzer=analyzer,
            path=tmp_path,
            lat=latitude,
            lon=longitude,
            date=recording_date,
            min_conf=settings.default_confidence_threshold,
        )

        recording.analyze()

        detections: list[Detection] = []
        for det in recording.detections:
            detections.append(
                Detection(
                    species=det["scientific_name"],
                    common_name=det["common_name"],
                    scientific_name=det["scientific_name"],
                    confidence=det["confidence"],
                    start_time=det["start_time"],
                    end_time=det["end_time"],
                    mic_id=mic_id,
                )
            )

        duration = getattr(recording, "duration", 0.0)

        return AnalyzeAudioResponse(
            detections=detections,
            file_duration=duration,
            processing_time_seconds=round(time.perf_counter() - start_time, 3),
        )

    except AudioFormatError:
        log.error("Unsupported audio format", filename=filename)
        raise
    except Exception:
        log.exception("Analysis failed")
        raise
    finally:
        Path(tmp_path).unlink(missing_ok=True)
