#!/usr/bin/env python3
"""
Optional compaction stage for AudioMoth short recordings.

Scans a directory containing many YYYYMMDD_HHMMSS.WAV (or prefixed) files
spanning multiple days, groups them by start-date, and produces one
time-aligned FLAC per day with digital silence filling the gaps.

Upload those FLACs to POST /detections/analyze; the API streams and
segments them without loading the full PCM into memory.

Run on the workstation that holds the raw WAVs — not in the API container.

Usage:
    python merge_audiomoth_days.py /path/to/raw_audio
    python merge_audiomoth_days.py /path/to/raw_audio --dry-run
    python merge_audiomoth_days.py /path/to/raw_audio --force --output-dir /elsewhere
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import soundfile as sf  # type: ignore[import-untyped]

# Matches optional prefix + YYYYMMDD_HHMMSS (+ optional suffix) + .WAV/.wav
AM_PATTERN = re.compile(
    r"^(?:(?P<prefix>[A-Za-z0-9]+)_)?"
    r"(?P<date>\d{8})_(?P<time>\d{6})"
    r"(?:_[A-Za-z0-9]+)?"
    r"\.(?P<ext>wav|WAV)$"
)


def parse_start(path: Path) -> datetime | None:
    m = AM_PATTERN.match(path.name)
    if not m:
        return None
    return datetime.strptime(f"{m.group('date')}_{m.group('time')}", "%Y%m%d_%H%M%S")


def collect_clips(src: Path) -> dict[str, list[tuple[datetime, Path, float, int, int]]]:
    """
    Returns { 'YYYY-MM-DD': [(start, path, duration_s, sr, channels), ...] }
    sorted by start time inside each day.
    """
    by_day: dict[str, list] = defaultdict(list)

    for p in sorted(src.iterdir()):
        if not p.is_file():
            continue
        start = parse_start(p)
        if start is None:
            continue
        try:
            info = sf.info(p)
        except Exception as e:
            print(f"  skip unreadable {p.name}: {e}", file=sys.stderr)
            continue

        duration = info.frames / info.samplerate
        day_key = start.strftime("%Y-%m-%d")
        by_day[day_key].append((start, p, duration, info.samplerate, info.channels))

    for day in by_day:
        by_day[day].sort(key=lambda x: x[0])
    return by_day


def write_day_flac(
    clips: list[tuple[datetime, Path, float, int, int]],
    out_path: Path,
    dry_run: bool = False,
) -> None:
    if not clips:
        return

    # Consistency check
    sr0, ch0 = clips[0][3], clips[0][4]
    for _start, path, _dur, sr, ch in clips[1:]:
        if sr != sr0 or ch != ch0:
            raise ValueError(f"Sample-rate / channel mismatch on {path.name} (expected {sr0}/{ch0}, got {sr}/{ch})")

    earliest = clips[0][0]
    print(f"  {len(clips)} clips  first={earliest}  → {out_path.name}")

    if dry_run:
        return

    # Detect overlaps
    cursor = earliest
    for start, path, dur, *_ in clips:
        gap = (start - cursor).total_seconds()
        if gap < -0.05:
            print(f"  WARNING: possible overlap involving {path.name} (gap={gap:.2f}s)")
        cursor = start + timedelta(seconds=dur)

    with sf.SoundFile(
        out_path,
        mode="w",
        samplerate=sr0,
        channels=ch0,
        format="FLAC",
        subtype="PCM_16",
    ) as out:
        cursor = earliest
        total_audio = 0.0
        total_silence = 0.0

        for start, path, dur, *_ in clips:
            gap = (start - cursor).total_seconds()
            if gap > 0.001:
                n_samples = round(gap * sr0)
                total_silence += gap
                # write silence in 30 s chunks so RAM stays flat
                chunk = sr0 * 30
                zeros = np.zeros((min(chunk, n_samples), ch0), dtype=np.int16)
                remaining = n_samples
                while remaining > 0:
                    n = min(chunk, remaining)
                    if n != zeros.shape[0]:
                        zeros = np.zeros((n, ch0), dtype=np.int16)
                    out.write(zeros)
                    remaining -= n

            data, _ = sf.read(path, dtype="int16")
            out.write(data)
            total_audio += dur
            cursor = start + timedelta(seconds=dur)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(
        f"    wrote {out_path.name}  "
        f"audio={total_audio / 60:.1f} min  silence={total_silence / 60:.1f} min  "
        f"size={size_mb:.1f} MB"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Compact AudioMoth short WAVs into one time-aligned FLAC per day.")
    ap.add_argument("source_dir", type=Path, help="Directory containing the WAV files")
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write the merged FLACs (default: same as source)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    ap.add_argument("--force", action="store_true", help="Overwrite existing merged files")
    ap.add_argument(
        "--min-files",
        type=int,
        default=1,
        help="Skip days that have fewer than this many clips (default: 1)",
    )
    args = ap.parse_args()

    src = args.source_dir.resolve()
    if not src.is_dir():
        sys.exit(f"Not a directory: {src}")

    out_dir = (args.output_dir or src).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scanning {src} …")
    by_day = collect_clips(src)
    if not by_day:
        print("No matching AudioMoth WAVs found.")
        return

    print(f"Found {sum(len(v) for v in by_day.values())} clips across {len(by_day)} day(s)\n")

    for day_key in sorted(by_day):
        clips = by_day[day_key]
        if len(clips) < args.min_files:
            print(f"{day_key}: only {len(clips)} file(s) - skipped")
            continue

        earliest = clips[0][0]
        out_name = f"{earliest.strftime('%Y%m%d_%H%M%S')}_merged_allday.flac"
        out_path = out_dir / out_name

        if out_path.exists() and not args.force:
            print(f"{day_key}: {out_name} already exists - skipped (use --force)")
            continue

        print(f"{day_key}:")
        try:
            write_day_flac(clips, out_path, dry_run=args.dry_run)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)

    print("\nDone.")


if __name__ == "__main__":
    main()
