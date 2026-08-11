from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import UploadFile


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not found on PATH")
    return path


def require_ffprobe() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("ffprobe not found on PATH")
    return path


async def stream_upload_to_temp(upload: UploadFile, suffix: str) -> Path:
    """Stream upload to disk in 1MiB chunks — never hold full body in RAM."""
    fd, name = tempfile.mkstemp(prefix="sd_upload_", suffix=suffix)
    path = Path(name)
    try:
        with open(fd, "wb") as out:
            while chunk := await upload.read(1024 * 1024):
                out.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def probe_duration_seconds(path: Path) -> float | None:
    cmd = [
        require_ffprobe(),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    text = out.stdout.strip()
    return float(text) if text else None


def segment_audio(input_path: Path, segment_seconds: int = 900) -> list[Path]:
    """
    Split into fixed-length WAV segments on disk.
    Returns paths in order. Last segment may be shorter.
    """
    require_ffmpeg()
    out_dir = Path(tempfile.mkdtemp(prefix="sd_seg_"))
    pattern = out_dir / "seg_%03d.wav"
    subprocess.run(
        [
            require_ffmpeg(),
            "-y",
            "-i",
            str(input_path),
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-c:a",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "1",
            str(pattern),
        ],
        check=True,
        capture_output=True,
    )
    return sorted(out_dir.glob("seg_*.wav"))
