#!/usr/bin/env python3
"""Scaffold a manga-drama-video-helper project or series episode."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def create_project_dirs(root):
    dirs = [
        root,
        root / "scripts",
        root / "assets" / "characters",
        root / "assets" / "scenes",
        root / "assets" / "style",
        root / "assets" / "motion",
        root / "audio" / "voice",
        root / "audio" / "bgm",
        root / "audio" / "sfx",
        root / "video" / "shots",
        root / "video" / "final",
    ]
    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_series_manifest(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_model_config(root, provider=None, model=None):
    path = root / "model_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        config = json.loads(path.read_text(encoding="utf-8"))
    else:
        config = {
            "version": 1,
            "current": {
                "provider": None,
                "model": None,
                "roles": [],
                "selected_at": None,
                "note": None,
            },
            "history": [],
        }
    if provider:
        config["current"]["provider"] = provider
    if model:
        config["current"]["model"] = model
    if provider or model:
        config["current"]["selected_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(path, config)


def main(argv):
    parser = argparse.ArgumentParser(
        description="Create the output directory structure for a manga-drama-video-helper project or series episode."
    )
    parser.add_argument("--output-dir", required=True, help="User-specified project/series root output directory.")
    parser.add_argument("--slug", required=True, help="Lowercase hyphenated project or series slug.")
    parser.add_argument("--aspect", default="9:16", choices=["9:16", "16:9", "1:1"])
    parser.add_argument("--style", default="写实动漫", help="Character/art style.")
    parser.add_argument("--target-length", type=int, default=30)
    parser.add_argument("--series", action="store_true", help="Scaffold a series root plus one episode.")
    parser.add_argument("--episode", default="EP01", help="Episode folder name when --series is used.")
    parser.add_argument("--auto", action="store_true", help="Set flow_mode to auto_review for user-review-only mode.")
    parser.add_argument("--model-provider", default="current", help="Current model provider, e.g. minimax-hailuo.")
    parser.add_argument("--model", default="", help="Current model name, e.g. hailuo-02.")
    parser.add_argument("--force", action="store_true", help="Overwrite episode manifest.json if it exists.")
    args = parser.parse_args(argv)

    slug = args.slug.strip().lower().replace("_", "-")
    if not slug:
        print("error: slug must not be empty", file=sys.stderr)
        return 1

    root = Path(args.output_dir).resolve()
    episode = args.episode.strip().upper()
    if not episode.startswith("EP"):
        episode = f"EP{episode}"
    flow_mode = "auto_review" if args.auto else "manual"

    if args.series:
        ensure_model_config(root, args.model_provider if args.model_provider != "current" else None, args.model or None)
        create_project_dirs(root / "episodes" / episode)
        series_path = root / "00_series.json"
        series = load_series_manifest(series_path)
        if series is None:
            series = {
                "series_slug": slug,
                "output_root": str(root),
                "continuity_version": 1,
                "episodes": [],
                "last_episode": None,
                "model_config_file": "model_config.json",
                "flow_mode": flow_mode,
                "engine_overrides": {},
                "characters": {},
                "scenes": {}
            }
        if episode not in series["episodes"]:
            series["episodes"].append(episode)
        series["last_episode"] = episode
        if args.auto:
            series["flow_mode"] = flow_mode
        write_json(series_path, series)

        project_root = root / "episodes" / episode
        manifest_path = project_root / "manifest.json"
        if manifest_path.exists() and not args.force:
            print(f"exists: {manifest_path}")
            print("use --force to overwrite episode manifest.json")
            return 0

        manifest = {
            "project_slug": slug,
            "series_slug": slug,
            "episode_number": episode,
            "continuity_version": series["continuity_version"],
            "flow_mode": flow_mode,
            "model_config_file": "model_config.json",
            "output_root": str(project_root),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "aspect_ratio": args.aspect,
            "character_style": args.style,
            "target_length_sec": args.target_length,
            "phases": {
                "phase_1_script": "pending",
                "phase_2_assets": "pending",
                "phase_3_video": "pending"
            },
            "engines": {}
        }
        write_json(manifest_path, manifest)
        print(f"wrote: {manifest_path}")
        print(f"series root: {root}")
        print(f"episode root: {project_root}")
        return 0

    ensure_model_config(root, args.model_provider if args.model_provider != "current" else None, args.model or None)
    create_project_dirs(root)
    manifest_path = root / "manifest.json"
    if manifest_path.exists() and not args.force:
        print(f"exists: {manifest_path}")
        print("use --force to overwrite manifest.json")
        return 0

    manifest = {
        "project_slug": slug,
        "series_slug": None,
        "episode_number": None,
        "continuity_version": 1,
        "flow_mode": flow_mode,
        "model_config_file": "model_config.json",
        "output_root": str(root),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "aspect_ratio": args.aspect,
        "character_style": args.style,
        "target_length_sec": args.target_length,
        "phases": {
            "phase_1_script": "pending",
            "phase_2_assets": "pending",
            "phase_3_video": "pending"
        },
        "engines": {}
    }
    write_json(manifest_path, manifest)
    print(f"wrote: {manifest_path}")
    print(f"project root: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
