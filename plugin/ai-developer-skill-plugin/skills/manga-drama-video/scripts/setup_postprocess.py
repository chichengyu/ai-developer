#!/usr/bin/env python3
"""Detect and configure FFmpeg / VapourSynth post-processing engines.

Usage:
    python setup_postprocess.py <project_dir> [--install-models] [--model-dir <dir>] [--write-plan]

Exit code 0 if at least one usable video engine is available.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path


MODEL_REGISTRY = {
    "realesrgan_x4plus": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
    "realesrgan_x4plus_anime_6b": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
}

DEFAULT_PLAN = {
    "postprocess_plan_version": 1,
    "profile": "balanced",
    "enabled": True,
    "order": ["stabilize", "deinterlace", "denoise", "sharpen", "color", "upscale", "grain"],
    "filters": {
        "stabilize": {"enabled": True, "method": "vidstab", "shakiness": 5},
        "deinterlace": {"enabled": False, "method": "yadif"},
        "denoise": {"enabled": True, "method": "hqdn3d", "strength": 3},
        "sharpen": {"enabled": True, "method": "unsharp", "amount": 0.5},
        "color": {"enabled": True, "method": "eq", "params": {"saturation": 1.05, "contrast": 1.03}},
        "upscale": {"enabled": False, "method": "real-esrgan", "scale": 2, "model": "realesrgan_x4plus"},
        "grain": {"enabled": True, "method": "noise", "amount": 3},
    },
    "vapoursynth": {"enabled": False, "script": None, "plugins": [], "models": {}},
    "outputs": {
        "video": "09_final_enhanced.mp4",
        "video_with_subs": "09_final_enhanced_with_subs.mp4",
    },
}


def download_file(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "codex-manga-drama-video/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as fh:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    fh.write(chunk)
        return True
    except Exception as exc:
        print(f"  FAIL  download {dest.name}: {exc}")
        return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Configure post-processing engines.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--install-models", action="store_true", help="download missing models")
    parser.add_argument("--write-plan", action="store_true", help="write postprocess_plan.json if missing")
    parser.add_argument("--auto-install", action="store_true", help="auto-install FFmpeg/VapourSynth before setup")
    args = parser.parse_args(argv)

    project = args.project_dir
    project.mkdir(parents=True, exist_ok=True)
    model_dir = args.model_dir or (project / "models")

    if args.auto_install:
        installer = Path(__file__).with_name("install_ffmpeg_vapoursynth.py")
        print("auto-installing FFmpeg / VapourSynth ...")
        code = subprocess.run([sys.executable, str(installer), str(project), "--auto-install"]).returncode
        if code != 0:
            print("auto-install failed; stopping setup")
            return code

    print("Post-processing engines")
    ffmpeg_path = tool_path("ffmpeg")
    ffprobe_path = tool_path("ffprobe")
    vspipe_path = tool_path("vspipe")
    ffmpeg_ok = bool(ffmpeg_path and ffprobe_path)
    vspipe_ok = bool(vspipe_path)
    print(f"  ffmpeg:  {'OK' if ffmpeg_ok else 'MISS'} {ffmpeg_path or ''}")
    print(f"  ffprobe: {'OK' if ffprobe_path else 'MISS'} {ffprobe_path or ''}")
    print(f"  vspipe:  {'OK' if vspipe_ok else 'MISS'} {vspipe_path or ''}")

    try:
        import vapoursynth  # type: ignore
        print("  vapoursynth python: OK")
        vs_py_ok = True
    except Exception:
        print("  vapoursynth python: MISS")
        vs_py_ok = False

    if not vspipe_ok or not vs_py_ok:
        print("  Note: VapourSynth is optional. Install it manually when extreme frame-level processing is needed.")

    if args.install_models:
        model_dir.mkdir(parents=True, exist_ok=True)
        for name, url in MODEL_REGISTRY.items():
            dest = model_dir / f"{name}.pth"
            if dest.exists():
                print(f"  model {name}: OK")
                continue
            print(f"  model {name}: downloading")
            if download_file(url, dest):
                print(f"  model {name}: OK")
            else:
                print(f"  model {name}: blocked")

    if args.write_plan:
        plan_path = project / "postprocess_plan.json"
        if not plan_path.exists():
            plan = json.loads(json.dumps(DEFAULT_PLAN))
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"wrote: {plan_path}")

    usable = (ffmpeg_ok and bool(ffprobe_path)) or vspipe_ok
    if not usable:
        print("No usable video engine found. Install ffmpeg (winget install Gyan.FFmpeg) or VapourSynth first.")
        return 1
    print("Post-processing setup ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
