#!/usr/bin/env python3
"""Build the 9-image / 3-video / 3-audio mixed reference bundle.

Usage:
    python process_reference_bundle.py <project_dir> [--input <dir>] [--dry-run]

Scans <project_dir>/resources/ (or --input) for reference assets and writes:
    <project_dir>/reference_bundle.json
    <project_dir>/reference_bundle_report.md
    <project_dir>/refs/<slot>.<ext>

Keyword matching:
    images: front, three-quarter/3q, side, expression, action,
            scene-wide/wide, scene-detail/detail, style, composition
    videos: motion, action, camera
    audio:  voice, emotion, ambience/sfx
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path
from probe_durations import probe_one


IMAGE_SLOTS = [
    ("character_front", ("front",)),
    ("character_three_quarter", ("three-quarter", "three_quarter", "3q", "threequarter")),
    ("character_side", ("side",)),
    ("character_expression", ("expression", "emotion", "face")),
    ("character_action", ("action", "pose", "fighting")),
    ("scene_wide", ("scene-wide", "scenewide", "wide", "establishing")),
    ("scene_detail", ("scene-detail", "scenedetail", "detail")),
    ("style_reference", ("style", "art-style", "artstyle", "painting")),
    ("composition_reference", ("composition", "layout", "blocking")),
]
VIDEO_SLOTS = [
    ("motion_primary", ("motion", "movement", "primary")),
    ("action_beat", ("action", "fight", "beat")),
    ("camera_move", ("camera", "camera-move", "orbit", "push")),
]
AUDIO_SLOTS = [
    ("voice_timbre", ("voice", "timbre", "vocal")),
    ("emotion_line", ("emotion", "line", "tone")),
    ("ambience_sfx", ("ambience", "sfx", "sound", "bgm")),
]


def ffmpeg() -> Optional[str]:
    return tool_path("ffmpeg")


def normalize_image(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".png":
        shutil.copy2(src, dest)
        return True
    exe = ffmpeg()
    if not exe:
        return False
    result = subprocess.run(
        [exe, "-y", "-loglevel", "error", "-i", str(src), str(dest)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and dest.exists()


def normalize_media(src: Path, dest: Path, kind: str) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == dest.suffix.lower():
        shutil.copy2(src, dest)
        return True
    exe = ffmpeg()
    if not exe:
        return False
    codec = []
    if kind == "video":
        codec = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]
    elif kind == "audio":
        codec = ["-c:a", "libmp3lame", "-q:a", "2"]
    result = subprocess.run(
        [exe, "-y", "-loglevel", "error", "-i", str(src), *codec, str(dest)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and dest.exists()


def match_slot(name: str, slots: List[tuple[str, tuple[str, ...]]]) -> Optional[str]:
    lower = name.lower()
    for slot, keywords in slots:
        if any(key in lower for key in keywords):
            return slot
    return None


def collect_inputs(input_dir: Path) -> Dict[str, List[Path]]:
    files = sorted(input_dir.rglob("*")) if input_dir.is_dir() else []
    images = [p for p in files if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
    videos = [p for p in files if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".avi")]
    audio = [p for p in files if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac")]
    return {"images": images, "videos": videos, "audio": audio}


def build_bundle(project: Path, input_dir: Path, dry_run: bool) -> Dict[str, Any]:
    collected = collect_inputs(input_dir)
    bundle: Dict[str, Any] = {
        "bundle_version": 1,
        "type": "mixed-reference",
        "images": {},
        "videos": {},
        "audio": {},
    }
    report: List[str] = ["# Reference Bundle Report", ""]
    refs_dir = project / "refs"
    matched: Dict[str, Path] = {}

    for slot, keywords in IMAGE_SLOTS:
        found = next((p for p in collected["images"] if match_slot(p.stem, [(slot, keywords)]) == slot), None)
        if found is not None:
            dest = refs_dir / f"{slot}.png"
            if not dry_run:
                normalize_image(found, dest)
            bundle["images"][slot] = f"refs/{slot}.png"
            matched[slot] = found
            report.append(f"- image {slot}: {found.name}")
        else:
            bundle["images"][slot] = None
            report.append(f"- image {slot}: missing")

    for slot, keywords in VIDEO_SLOTS:
        found = next((p for p in collected["videos"] if match_slot(p.stem, [(slot, keywords)]) == slot), None)
        if found is not None:
            dest = refs_dir / f"{slot}.mp4"
            if not dry_run:
                normalize_media(found, dest, "video")
            bundle["videos"][slot] = f"refs/{slot}.mp4"
            matched[slot] = found
            report.append(f"- video {slot}: {found.name}")
        else:
            bundle["videos"][slot] = None
            report.append(f"- video {slot}: missing")

    for slot, keywords in AUDIO_SLOTS:
        found = next((p for p in collected["audio"] if match_slot(p.stem, [(slot, keywords)]) == slot), None)
        if found is not None:
            dest = refs_dir / f"{slot}.mp3"
            if not dry_run:
                normalize_media(found, dest, "audio")
            bundle["audio"][slot] = f"refs/{slot}.mp3"
            matched[slot] = found
            report.append(f"- audio {slot}: {found.name}")
        else:
            bundle["audio"][slot] = None
            report.append(f"- audio {slot}: missing")

    report.append("")
    for slot, src in matched.items():
        if src.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".mp3", ".wav", ".m4a", ".ogg", ".flac"):
            info = probe_one(src)
            report.append(f"- {slot}: {info.get('duration_ms')} ms ({info.get('method')})")
        else:
            report.append(f"- {slot}: image asset")

    if not dry_run:
        (project / "reference_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (project / "reference_bundle_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return bundle


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build mixed reference bundle.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project = args.project_dir
    project.mkdir(parents=True, exist_ok=True)
    input_dir = args.input or project / "resources"
    if not input_dir.exists():
        print(f"input dir not found: {input_dir}")
        return 1
    bundle = build_bundle(project, input_dir, args.dry_run)
    counts = (
        sum(1 for v in bundle["images"].values() if v),
        sum(1 for v in bundle["videos"].values() if v),
        sum(1 for v in bundle["audio"].values() if v),
    )
    print(f"bundle: {counts[0]} images / {counts[1]} videos / {counts[2]} audio")
    if not args.dry_run:
        print(f"wrote: {project / 'reference_bundle.json'}")
        print(f"wrote: {project / 'reference_bundle_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
