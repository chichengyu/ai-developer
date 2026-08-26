#!/usr/bin/env python3
"""Validate the outputs/<project-slug>/ directory structure.

Usage:
    python validate_outputs.py <path/to/outputs/<slug>>

Checks for the expected files and report missing ones. Exit code 0 if all
required artifacts exist; exit 1 if any required file is missing. Step 0
bibles, series canonical refs, and De-AI audits are mandatory.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

REQUIRED_STEPS = {
    1: ["01_brief.md", "00_meta.json"],
    2: ["02_script.md", "02_character_analysis.md", "02_script_analysis.md", "02_script_analysis.json"],
    3: ["03_storyboard.md"],
    4: ["04_art_direction.md"],
    5: ["05_images/manifest.json", "05_images/continuity_audit.md", "05_images/deai_audit.md"],
    6: ["06_voice/index.json"],
    7: ["07_subtitles.srt", "07_timeline.json"],
    8: ["08_final.mp4", "08_final_with_subs.mp4", "08_deai_check.md"],
    9: ["postprocess_plan.json", "09_final_enhanced.mp4", "09_postprocess_report.md", "09_deai_check.md"],
}

REQUIRED_STEP0 = [
    "character-bible.md",
    "scene-bible.md",
    "style-lock.json",
    "00_resources.md",
    "resource_manifest.json",
    "engine_plan.json",
]

OPTIONAL_ALWAYS = [
    "STATE.md",
    "README.md",
]


def find_series_root(root: Path) -> Optional[Path]:
    current = root
    while current != current.parent:
        if (current / "00_series.json").exists():
            return current
        current = current.parent
    return None


def check(root: Path) -> tuple[int, list[str], list[str]]:
    missing: list[str] = []
    weak: list[str] = []

    if not root.is_dir():
        return 1, [f"project directory not found: {root}"], []

    for step, files in REQUIRED_STEPS.items():
        for f in files:
            if not (root / f).exists():
                missing.append(f"[step {step}] missing: {f}")

    for f in OPTIONAL_ALWAYS:
        if not (root / f).exists():
            weak.append(f"optional missing: {f}")

    if (root / "07_subtitles.srt").exists() and not (root / "09_final_enhanced_with_subs.mp4").exists():
        weak.append("07_subtitles.srt exists but 09_final_enhanced_with_subs.mp4 is missing")

    if (root / "02_script_analysis.md").exists() and not (root / "02_script_analysis.json").exists():
        weak.append("02_script_analysis.md exists but 02_script_analysis.json is missing")

    meta = None
    meta_path = root / "00_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            weak.append(f"00_meta.json is not valid JSON: {exc}")
        else:
            for key in ("aspect_ratio", "resolution", "framerate", "target_length_sec",
                        "shots_total", "character_style", "is_series", "continuity_version",
                        "motion_mode"):
                if key not in meta:
                    weak.append(f"00_meta.json missing key: {key}")
            if "output_root" in meta and not isinstance(meta["output_root"], str):
                weak.append("00_meta.json output_root must be a string when present")
            if isinstance(meta.get("output_dirs"), dict):
                for kind in ("scripts", "images", "videos", "audio"):
                    if kind not in meta["output_dirs"]:
                        weak.append(f"00_meta.json output_dirs missing key: {kind}")
            if meta.get("is_series") is True:
                for key in ("series_slug", "episode_number"):
                    if key not in meta:
                        weak.append(f"00_meta.json missing key: {key}")

    series_root = find_series_root(root)
    if meta is not None and meta.get("is_series") is True:
        if series_root is None:
            missing.append("[step 0] series root 00_series.json not found")
        else:
            for f in ["00_series.json"] + REQUIRED_STEP0:
                if not (series_root / f).exists():
                    missing.append(f"[step 0] missing in series root: {f}")
            manifest_path = series_root / "00_series.json"
            if manifest_path.exists():
                try:
                    series = json.loads(manifest_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    weak.append(f"00_series.json is not valid JSON: {exc}")
                else:
                    if isinstance(series, dict):
                        for group in ("characters", "locations"):
                            for item in series.get(group, []):
                                for ref in item.get("canonical_refs", []):
                                    if not (series_root / ref).exists():
                                        if (root / "05_images" / "manifest.json").exists():
                                            missing.append(f"[step 5] series ref missing: {ref}")
                                        else:
                                            weak.append(f"[pending step 5] series ref missing: {ref}")
                                if "seed" not in item:
                                    weak.append(f"00_series.json {group} item missing seed: {item.get('character_id') or item.get('scene_id')}")
                                if item.get("locked") is not True:
                                    weak.append(f"00_series.json {group} item not locked: {item.get('character_id') or item.get('scene_id')}")
    else:
        step0_root = series_root if series_root is not None else root
        for f in REQUIRED_STEP0:
            if not (step0_root / f).exists():
                location = "in series root" if series_root is not None else ""
                missing.append(f"[step 0] missing {location}: {f}")

    step0_dir = series_root if meta is not None and meta.get("is_series") is True else root
    if step0_dir is not None:
        for f in ("resource_manifest.json", "engine_plan.json"):
            p = step0_dir / f
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    weak.append(f"{f} is not valid JSON: {exc}")
                else:
                    if f == "engine_plan.json":
                        if not isinstance(data, dict):
                            weak.append("engine_plan.json must be a JSON object")
                    elif f == "resource_manifest.json":
                        if not isinstance(data, dict):
                            weak.append("resource_manifest.json must be a JSON object")
                        elif data.get("blocked"):
                            weak.append(f"resource_manifest.json has {len(data['blocked'])} unresolved blocked resource(s)")

    manifest_path = root / "05_images" / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            weak.append(f"05_images/manifest.json is not valid JSON: {exc}")
        else:
            unapproved = [m for m in manifest if m.get("status") != "approved"]
            if unapproved:
                weak.append(
                    f"{len(unapproved)} shot(s) in 05_images/manifest.json are not approved"
                )
            for shot in manifest:
                for key in ("character_ids", "scene_id", "seed"):
                    if key not in shot:
                        weak.append(f"05_images/manifest.json shot missing {key}: {shot.get('shot_id')}")

    video_manifest_path = root / "05_video" / "manifest.json"
    if meta is not None and meta.get("motion_mode") != "still-kenburns":
        if not video_manifest_path.exists():
            weak.append("05_video/manifest.json missing in real-motion mode")
    if video_manifest_path.exists():
        try:
            video_manifest = json.loads(video_manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            weak.append(f"05_video/manifest.json is not valid JSON: {exc}")
        else:
            if isinstance(video_manifest, list):
                for shot in video_manifest:
                    for key in ("shot_id", "keyframe", "clip", "seed", "model", "status"):
                        if key not in shot:
                            weak.append(f"05_video/manifest.json shot missing {key}: {shot.get('shot_id')}")
                    if shot.get("clip") and not (root / shot["clip"]).exists():
                        weak.append(f"05_video clip missing: {shot.get('clip')}")
                    for key in ("start_image", "end_image"):
                        value = shot.get(key)
                        if value and not (root / value).exists():
                            weak.append(f"05_video frame chain file missing: {value}")

    bundle_path = root / "reference_bundle.json"
    if bundle_path.exists():
        try:
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            weak.append(f"reference_bundle.json is not valid JSON: {exc}")
        else:
            for group in ("images", "videos", "audio"):
                for slot, value in bundle.get(group, {}).items():
                    if value and not (root / value).exists():
                        weak.append(f"reference_bundle {group}.{slot} missing: {value}")
    else:
        weak.append("reference_bundle.json missing (expected after Step 0)")

    voice_index = root / "06_voice" / "index.json"
    if voice_index.exists():
        try:
            entries = json.loads(voice_index.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            weak.append(f"06_voice/index.json is not valid JSON: {exc}")
        else:
            for entry in entries:
                if not (root / entry.get("file", "")).exists():
                    weak.append(f"voice file missing: {entry.get('file')}")

    face_index = root / "06_face" / "index.json"
    if face_index.exists():
        try:
            face_entries = json.loads(face_index.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            weak.append(f"06_face/index.json is not valid JSON: {exc}")
        else:
            for entry in face_entries:
                if entry.get("output") and not (root / entry["output"]).exists():
                    weak.append(f"lip-sync output missing: {entry.get('output')}")

    audit_path = root / "05_images" / "continuity_audit.md"
    if audit_path.exists():
        audit_text = audit_path.read_text(encoding="utf-8")
        mismatch_rows = [
            line for line in audit_text.splitlines()
            if line.startswith("|") and re.search(r"\|\s*mismatch\s*\|", line, re.I)
        ]
        if mismatch_rows:
            weak.append("05_images/continuity_audit.md contains mismatch entries")

    for audit_rel in ("05_images/deai_audit.md", "08_deai_check.md", "09_deai_check.md"):
        audit_path = root / audit_rel
        if audit_path.exists():
            audit_text = audit_path.read_text(encoding="utf-8")
            if re.search(r"是否允许进入下一步:\s*no", audit_text, re.I) or re.search(r"\|\s*fail\s*\|", audit_text, re.I):
                weak.append(f"{audit_rel} blocks next step")

    post_plan_path = root / "postprocess_plan.json"
    if post_plan_path.exists():
        try:
            post_plan = json.loads(post_plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            weak.append(f"postprocess_plan.json is not valid JSON: {exc}")
        else:
            if not isinstance(post_plan, dict):
                weak.append("postprocess_plan.json must be a JSON object")

    return (1 if missing else 0), missing, weak


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: python validate_outputs.py <project_dir>", file=sys.stderr)
        return 2
    code, missing, weak = check(Path(argv[0]))
    if missing:
        print("FAIL")
        for m in missing:
            print(f"  {m}")
    else:
        print("OK: required files present")
    if weak:
        print("WARN")
        for w in weak:
            print(f"  {w}")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
