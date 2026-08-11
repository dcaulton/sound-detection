"""Disk / ffmpeg helpers — mock subprocess where needed."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile

# Adjust module path to match where you put the helpers
from sound_detection.utils.audio_io import (
    require_ffmpeg,
    segment_audio,
    stream_upload_to_temp,
)


@pytest.mark.asyncio
async def test_stream_upload_writes_temp_file(tmp_path: Path) -> None:
    payload = b"abc" * 1000
    upload = UploadFile(filename="clip.wav", file=MagicMock())
    upload.file = MagicMock()
    # UploadFile.read is async in Starlette
    chunks = [payload[i : i + 1024] for i in range(0, len(payload), 1024)] + [b""]

    async def fake_read(size: int = -1) -> bytes:
        return chunks.pop(0) if chunks else b""

    upload.read = fake_read  # type: ignore[method-assign]

    path = await stream_upload_to_temp(upload, suffix=".wav")
    try:
        assert path.is_file()
        assert path.read_bytes() == payload
        assert path.suffix == ".wav"
    finally:
        path.unlink(missing_ok=True)


def test_require_ffmpeg_raises_when_missing() -> None:
    with patch("sound_detection.utils.audio_io.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="ffmpeg"):
            require_ffmpeg()


def test_segment_audio_returns_ordered_paths(tmp_path: Path) -> None:
    """Avoid real ffmpeg: plant output files and mock subprocess."""
    input_path = tmp_path / "day.wav"
    input_path.write_bytes(b"RIFF")

    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    (seg_dir / "seg_000.wav").write_bytes(b"a")
    (seg_dir / "seg_001.wav").write_bytes(b"b")

    with (
        patch("sound_detection.utils.audio_io.require_ffmpeg", return_value="ffmpeg"),
        patch("sound_detection.utils.audio_io.tempfile.mkdtemp", return_value=str(seg_dir)),
        patch("sound_detection.utils.audio_io.subprocess.run") as run,
    ):
        run.return_value = MagicMock(returncode=0)
        paths = segment_audio(input_path, segment_seconds=900)

    assert [p.name for p in paths] == ["seg_000.wav", "seg_001.wav"]
