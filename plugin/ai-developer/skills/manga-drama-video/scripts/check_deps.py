#!/usr/bin/env python3
"""Cross-platform dependency check for manga-drama-video.

Usage:
    python check_deps.py

Exit code 0 if required tools are present; 1 if ffmpeg/ffprobe are missing.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path
from install_image_engine import probe_local_image_engines
from install_video_engine import (
    default_video_runtime_dir,
    detect_audio_lip_sync,
    detect_talking_head,
    find_comfyui_dir,
    scan_model_files,
)


def have_tool(name: str) -> bool:
    return tool_path(name) is not None


def first_version(name: str) -> str:
    resolved = tool_path(name) or name
    try:
        result = subprocess.run([resolved, "--version"], capture_output=True, text=True, timeout=15)
        return (result.stdout or result.stderr).strip().splitlines()[0][:120]
    except Exception:
        return "unavailable"


def main() -> int:
    fail = False
    video_scan = scan_model_files(find_comfyui_dir(), default_video_runtime_dir())
    video_diffusion = [
        path
        for family in ("wan", "hunyuan", "ltx")
        for path in video_scan.get(family, [])
    ]

    print(f"System: {platform.platform()} / {platform.machine()}")
    print("Policy: latest stable, compatible with current OS/architecture")

    print("Required")
    checks = [
        ("ffmpeg", have_tool("ffmpeg"), "install via winget/choco/apt/brew"),
        ("ffprobe", have_tool("ffprobe"), "ships with ffmpeg"),
        ("python", True, "this script is running under Python"),
    ]
    for name, ok, hint in checks:
        if ok:
            print(f"  OK    {name}")
        else:
            print(f"  MISS  {name} ({hint})")
            fail = True

    print("\nOptional (improves quality)")
    optional = [
        ("edge-tts", have_tool("edge-tts"), "pip install edge-tts"),
        ("espeak/espeak-ng", have_tool("espeak-ng") or have_tool("espeak"), "local TTS fallback"),
        ("curl", have_tool("curl"), "needed for API and resource downloads"),
        ("node", have_tool("node"), "optional for browser/Node-based helpers"),
        ("vspipe", have_tool("vspipe"), "VapourSynth pipe tool for Step 9"),
        ("local image engine", bool(probe_local_image_engines()), "run scripts/install_image_engine.py --auto-install"),
        ("video diffusion models", bool(video_diffusion), "run scripts/install_video_engine.py <project> --auto"),
        ("talking head tool", bool(detect_talking_head(find_comfyui_dir()).get("available")), "run scripts/install_video_engine.py <project> --install --models liveportrait"),
        ("audio-driven lip sync", bool(detect_audio_lip_sync(find_comfyui_dir(), default_video_runtime_dir()).get("available")), "install SadTalker/MuseTalk/Wav2Lip/Hallo or export a Wan 2.2 A2V workflow"),
        ("MANGA_TOOL_DIR", bool(os.environ.get("MANGA_TOOL_DIR")), "optional env override for tool paths"),
    ]
    for name, ok, hint in optional:
        if ok:
            print(f"  OK    {name}")
        else:
            print(f"  MISS  {name} ({hint})")

    print("\nImagegen / talking-head providers")
    if os.environ.get("OPENAI_API_KEY"):
        print("  OK    OPENAI_API_KEY set (OpenAI imagegen/TTS reachable)")
    else:
        print("  MISS  OPENAI_API_KEY (fallback: Codex imagegen MCP / speech MCP)")
    if os.environ.get("HEYGEN_API_KEY") or os.environ.get("D_ID_API_KEY"):
        print("  OK    talking-head API key set")
    else:
        print("  MISS  talking-head API key (still-portrait mode remains available)")

    print("\nVersions")
    for name in ("ffmpeg", "ffprobe", "vspipe", "node"):
        if have_tool(name):
            print(f"  {name}: {first_version(name)}")
        else:
            print(f"  {name}: unavailable")

    print()
    if fail:
        print("Some required tools are missing. Step 8 and parts of Step 6/7 will not work.")
        return 1
    print("All required tools present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
