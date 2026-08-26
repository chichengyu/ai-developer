#!/usr/bin/env python3
"""Export approved artifacts to a user-facing output root.

Usage:
    python export_outputs.py <project_dir> [--output-root <dir>]
      [--kind all|scripts|images|videos|audio] [--slug <name>] [--dry-run]

Reads:
  <project_dir>/00_meta.json

Writes when --output-root is given (or 00_meta.json has output_root):
  <output_root>/scripts/<slug>/...   brief, script, storyboard, art direction, manifests, SRT
  <output_root>/images/<slug>/...    refs, canonical refs, keyframes
  <output_root>/videos/<slug>/...    motion clips, lip sync, final renders
  <output_root>/audio/<slug>/...     voice lines
  <output_root>/manifest.json

If no output root is configured the script skips export; the existing
outputs/<slug>/ workspace remains the source of truth.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


SCRIPT_SUFFIXES = (".md", ".json", ".srt")
VIDEO_FINAL_PATTERNS = (
    "08_final.mp4",
    "08_final_with_subs.mp4",
    "09_final_enhanced.mp4",
    "09_final_enhanced_with_subs.mp4",
)


def load_meta(project: Path) -> Dict[str, Any]:
    path = project / "00_meta.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def find_series_root(project: Path) -> Optional[Path]:
    current = project
    while current != current.parent:
        if (current / "00_series.json").exists():
            return current
        current = current.parent
    return None


def unique_roots(*roots: Optional[Path]) -> List[Path]:
    seen = set()
    result: List[Path] = []
    for root in roots:
        if root is None:
            continue
        key = str(root.resolve()).lower()
        if key not in seen:
            seen.add(key)
            result.append(root)
    return result


def resolve_slug(project: Path, meta: Dict[str, Any], override: Optional[str]) -> str:
    if override:
        return override
    if meta.get("is_series") is True and meta.get("series_slug") and meta.get("episode_number"):
        return f"{meta['series_slug']}/{meta['episode_number']}"
    if meta.get("project_slug"):
        return str(meta["project_slug"])
    return project.name


def resolve_output_root(project: Path, meta: Dict[str, Any], override: Optional[Path]) -> Optional[Path]:
    if override is not None:
        return override.expanduser().resolve()
    value = meta.get("output_root")
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = project / path
    return path.expanduser().resolve()


def copy_tree(src: Path, dst: Path, dry_run: bool) -> List[str]:
    copied: List[str] = []
    if not src.is_dir():
        return copied
    for child in src.rglob("*"):
        if not child.is_file():
            continue
        rel = child.relative_to(src)
        target = dst / rel
        if dry_run:
            copied.append(str(rel))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(child, target)
        copied.append(str(rel))
    return copied


def export(project: Path, output_root: Path, slug: str, kinds: List[str], dry_run: bool) -> Dict[str, List[str]]:
    series_root = find_series_root(project)
    roots = unique_roots(project, series_root)
    base_scripts = output_root / "scripts" / slug
    base_images = output_root / "images" / slug
    base_videos = output_root / "videos" / slug
    base_audio = output_root / "audio" / slug
    summary: Dict[str, List[str]] = {"scripts": [], "images": [], "videos": [], "audio": []}

    if "scripts" in kinds:
        for root in roots:
            for src in root.iterdir():
                if not src.is_file() or src.suffix.lower() not in SCRIPT_SUFFIXES:
                    continue
                target = base_scripts / src.name
                if dry_run:
                    summary["scripts"].append(f"{root.name}/{src.name}")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target)
                    summary["scripts"].append(f"{root.name}/{src.name}")

    if "images" in kinds:
        for root in roots:
            for sub in ("refs", "05_images"):
                src = root / sub
                if src.is_dir():
                    summary["images"].extend(copy_tree(src, base_images / sub, dry_run))

    if "videos" in kinds:
        for sub in ("05_video", "06_face"):
            src = project / sub
            if src.is_dir():
                summary["videos"].extend(copy_tree(src, base_videos / sub, dry_run))
        for pattern in VIDEO_FINAL_PATTERNS:
            for src in project.glob(pattern):
                if src.is_file():
                    target = base_videos / src.name
                    if dry_run:
                        summary["videos"].append(src.name)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, target)
                        summary["videos"].append(src.name)

    if "audio" in kinds:
        src = project / "06_voice"
        if src.is_dir():
            summary["audio"].extend(copy_tree(src, base_audio / "06_voice", dry_run))

    if not dry_run:
        manifest = {
            "export_version": 1,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "slug": slug,
            "output_root": str(output_root),
            "source_project": str(project.resolve()),
            "categories": summary,
        }
        manifest_path = output_root / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Export artifacts to a user-facing directory.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--kind", choices=("all", "scripts", "images", "videos", "audio"), default="all")
    parser.add_argument("--slug", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project = args.project_dir.resolve()
    if not project.is_dir():
        print(f"project directory not found: {project}")
        return 1
    meta = load_meta(project)
    output_root = resolve_output_root(project, meta, args.output_root)
    if output_root is None:
        print("no output_root configured; export skipped (pass --output-root or set output_root in 00_meta.json)")
        return 0
    slug = resolve_slug(project, meta, args.slug)
    kinds = ["scripts", "images", "videos", "audio"] if args.kind == "all" else [args.kind]
    summary = export(project, output_root, slug, kinds, args.dry_run)
    for kind in kinds:
        count = len(summary[kind])
        mode = "would copy" if args.dry_run else "copied"
        print(f"{kind}: {mode} {count} file(s) -> {output_root / kind / slug}")
    if not args.dry_run:
        print(f"wrote: {output_root / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
