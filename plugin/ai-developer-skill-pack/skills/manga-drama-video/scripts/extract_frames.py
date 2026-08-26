#!/usr/bin/env python3
"""Extract first/last/interval frames from a video for long-shot chaining.

Usage:
    python extract_frames.py <video> --output <dir> [--first] [--last] [--every N]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path


def ffmpeg() -> str:
    path = tool_path("ffmpeg")
    if not path:
        raise SystemExit("ffmpeg is required")
    return path


def probe_duration(path: Path) -> float:
    probe = tool_path("ffprobe")
    if not probe:
        return 0.0
    result = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Extract frames from a video.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first", action="store_true")
    parser.add_argument("--last", action="store_true")
    parser.add_argument("--every", type=float, default=None, help="extract one frame every N seconds")
    args = parser.parse_args(argv)

    if not args.first and not args.last and args.every is None:
        print("choose --first, --last, or --every N")
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    exe = ffmpeg()
    base = args.video.stem
    ok = True
    if args.first:
        out = args.output / f"{base}_first.png"
        result = subprocess.run(
            [exe, "-y", "-loglevel", "error", "-i", str(args.video), "-frames:v", "1", str(out)],
            capture_output=True,
            text=True,
        )
        ok = ok and result.returncode == 0 and out.exists()
        print(f"wrote: {out}")
    if args.last:
        duration = probe_duration(args.video)
        if duration > 0:
            out = args.output / f"{base}_last.png"
            result = subprocess.run(
                [exe, "-y", "-loglevel", "error", "-sseof", "-0.1", "-i", str(args.video), "-frames:v", "1", str(out)],
                capture_output=True,
                text=True,
            )
            ok = ok and result.returncode == 0 and out.exists()
            print(f"wrote: {out}")
    if args.every is not None and args.every > 0:
        out_pattern = str(args.output / f"{base}_%03d.png")
        result = subprocess.run(
            [exe, "-y", "-loglevel", "error", "-i", str(args.video),
             "-vf", f"fps=1/{args.every}", str(out_pattern)],
            capture_output=True,
            text=True,
        )
        ok = ok and result.returncode == 0
        print(f"wrote frames to: {args.output}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
