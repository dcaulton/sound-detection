"""background_analyze behavior without real BirdNET/Perch."""

from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sound_detection.api.v1.routers.detections import background_analyze
from sound_detection.db.models import Detection, Recording
from sound_detection.db.repositories import RecordingRepository
from sound_detection.schemas.detection import Detection as SchemaDetection


def _det(species: str, start: float, end: float, model: str) -> SchemaDetection:
    """Build a minimal schema detection — adjust fields to match your schema."""
    return SchemaDetection(
        species=species,
        scientific_name=species,
        common_name=species,
        confidence=0.9,
        start_offset=start,
        end_offset=end,
        model=model,
    )


class _FakeResponse:
    def __init__(self, detections: list[SchemaDetection], file_duration: float | None = 10.0) -> None:
        self.detections = detections
        self.file_duration = file_duration


@pytest.mark.asyncio
async def test_background_analyze_marks_failed(async_session: AsyncSession) -> None:
    work_dir = Path(tempfile.mkdtemp(prefix="sd_fail_"))
    work_path = work_dir / "x.wav"
    work_path.write_bytes(b"not-real-audio")

    repo = RecordingRepository(async_session)
    mic = await repo.get_or_create_default_microphone()
    rec = Recording(
        microphone_id=mic.id,
        filename="x.wav",
        file_path=str(work_path),
        status="pending",
        recorded_at=datetime.now(UTC),
    )
    async_session.add(rec)
    await async_session.commit()
    await async_session.refresh(rec)

    with patch(
        "sound_detection.api.v1.routers.detections.analyze_with_perch",
        side_effect=RuntimeError("boom"),
    ):
        await background_analyze(
            recording_id=rec.id,
            audio_path=str(work_path),
            filename="x.wav",
            session=async_session,
        )

    result = await async_session.execute(
        select(Recording).where(Recording.id == rec.id)  # type: ignore[arg-type]
    )
    updated = result.scalar_one()
    assert updated.status == "failed"
    shutil.rmtree(work_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_segment_offsets_shifted(async_session: AsyncSession) -> None:
    """Two segments: second segment's offsets must include base 900s."""
    work_dir = Path(tempfile.mkdtemp(prefix="sd_seg_"))
    work_path = work_dir / "long.wav"
    work_path.write_bytes(b"x" * 100)

    repo = RecordingRepository(async_session)
    mic = await repo.get_or_create_default_microphone()
    rec = Recording(
        microphone_id=mic.id,
        filename="long.wav",
        file_path=str(work_path),
        status="pending",
        recorded_at=datetime.now(UTC),
    )
    async_session.add(rec)
    await async_session.commit()
    await async_session.refresh(rec)

    seg0 = work_dir / "seg_000.wav"
    seg1 = work_dir / "seg_001.wav"
    seg0.write_bytes(b"a")
    seg1.write_bytes(b"b")

    call_count = {"n": 0}

    def fake_perch(audio_bytes: bytes, filename: str | None = None, **kwargs: object) -> _FakeResponse:
        # first segment call vs second — both models called per segment
        return _FakeResponse([_det("Turdus migratorius", 1.0, 2.0, "perch")])

    def fake_birdnet(audio_bytes: bytes, filename: str = "", **kwargs: object) -> _FakeResponse:
        call_count["n"] += 1
        return _FakeResponse([_det("Turdus migratorius", 1.0, 2.0, "birdnet")], file_duration=10.0)

    with (
        patch(
            "sound_detection.api.v1.routers.detections.segment_audio",
            return_value=[seg0, seg1],
        ),
        patch(
            "sound_detection.api.v1.routers.detections.probe_duration_seconds",
            return_value=1800.0,
        ),
        patch(
            "sound_detection.api.v1.routers.detections.analyze_with_perch",
            side_effect=fake_perch,
        ),
        patch(
            "sound_detection.api.v1.routers.detections.analyze_with_birdnet",
            side_effect=fake_birdnet,
        ),
        # force multi-segment path even if file is tiny
        patch(
            "sound_detection.api.v1.routers.detections.Path.stat",
            return_value=MagicMock(st_size=100 * 1024 * 1024),  # 100MB
        ),
    ):
        await background_analyze(
            recording_id=rec.id,
            audio_path=str(work_path),
            filename="long.wav",
            session=async_session,
            segment_seconds=900,
        )

    det_result = await async_session.execute(
        select(Detection).where(Detection.recording_id == rec.id)  # type: ignore[arg-type]
    )
    dets = list(det_result.scalars().all())
    assert len(dets) >= 1
    # At least one detection should reflect second segment shift
    assert any(float(d.start_offset) >= 900.0 for d in dets)

    rec_result = await async_session.execute(
        select(Recording).where(Recording.id == rec.id)  # type: ignore[arg-type]
    )
    updated = rec_result.scalar_one()
    assert updated.status == "completed"
    assert updated.duration_seconds == 1800.0

    shutil.rmtree(work_dir, ignore_errors=True)
