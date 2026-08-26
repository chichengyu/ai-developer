#!/usr/bin/env python3
"""Probe durations for audio and video files.

Usage:
    python probe_durations.py <path> [--json]

If <path> is a directory, probe every *.mp3 *.wav *.m4a *.ogg *.mp4 *.mov inside it.
If <path> is a single file, probe only that file.

Output: prints either a human table or JSON array with {file, duration_ms}.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
ALL_EXTS = AUDIO_EXTS | VIDEO_EXTS


def probe_with_ffprobe(path: Path) -> int | None:
    ffprobe = tool_path("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, check=True, timeout=30,
        )
        seconds = float(result.stdout.strip())
        return int(seconds * 1000)
    except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired):
        return None


def probe_with_mutagen(path: Path) -> int | None:
    try:
        from mutagen.mp3 import MP3
        from mutagen.wave import WAVE
        from mutagen.oggvorbis import OggVorbis
        from mutagen.flac import FLAC
        from mutagen.mp4 import MP4
        ext = path.suffix.lower()
        if ext == ".mp3":
            return int(MP3(path).info.length * 1000)
        if ext == ".wav":
            return int(WAVE(path).info.length * 1000)
        if ext == ".ogg":
            return int(OggVorbis(path).info.length * 1000)
        if ext == ".flac":
            return int(FLAC(path).info.length * 1000)
        if ext == ".m4a":
            return int(MP4(path).info.length * 1000)
    except Exception:
        return None
    return None


def collect_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if not target.is_dir():
        return []
    files = []
    for p in sorted(target.rglob("*")):
        if p.is_file() and p.suffix.lower() in ALL_EXTS:
            files.append(p)
    return files


def probe_one(path: Path) -> dict:
    duration_ms = probe_with_ffprobe(path)
    method = "ffprobe" if duration_ms is not None else None
    if duration_ms is None and path.suffix.lower() in AUDIO_EXTS:
        duration_ms = probe_with_mutagen(path)
        if duration_ms is not None:
            method = "mutagen"
    return {
        "file": str(path),
        "duration_ms": duration_ms,
        "method": method,
        "missing_tool": None if duration_ms is not None else "ffprobe or mutagen",
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Probe audio/video durations.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true", help="emit JSON array")
    parser.add_argument("--video", action="store_true", help="include video files")
    args = parser.parse_args(argv)

    files = collect_files(args.path)
    if args.video:
        files = [f for f in files if f.suffix.lower() in VIDEO_EXTS]
    if not files:
        print(f"No probeable files in {args.path}", file=sys.stderr)
        return 1

    results = [probe_one(p) for p in files]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            if r["duration_ms"] is None:
                print(f"  {r['file']}  ->  MISSING ({r['missing_tool']})")
            else:
                print(f"  {r['file']}  ->  {r['duration_ms']} ms  ({r['method']})")
    return 0 if all(r["duration_ms"] is not None for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
