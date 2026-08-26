#!/usr/bin/env python3
"""Run Step 9 post-processing (FFmpeg / VapourSynth).

Usage:
    python postprocess.py <project_dir> [--profile <light|balanced|extreme>] [--force]

Reads:
  <project_dir>/08_final.mp4
  <project_dir>/postprocess_plan.json

Writes:
  <project_dir>/09_final_enhanced.mp4
  <project_dir>/09_final_enhanced_with_subs.mp4
  <project_dir>/09_postprocess_report.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path


DEFAULT_PLAN: Dict[str, Any] = {
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

DEFAULT_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "PingFang SC",
    "Arial Unicode MS",
]


def require_tool(name: str) -> str:
    path = tool_path(name)
    if not path:
        raise SystemExit(f"missing required tool: {name}")
    return path


def load_plan(project: Path) -> Dict[str, Any]:
    plan_path = project / "postprocess_plan.json"
    if plan_path.exists():
        return json.loads(plan_path.read_text(encoding="utf-8"))
    plan = json.loads(json.dumps(DEFAULT_PLAN))
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan


def build_ffmpeg_filters(plan: Dict[str, Any], include_stabilize: bool = False) -> List[str]:
    filters = plan.get("filters", {})
    order = plan.get("order", list(filters.keys()))
    parts: List[str] = []
    for key in order:
        item = filters.get(key, {})
        if not item.get("enabled", False):
            continue
        if key == "stabilize":
            if include_stabilize:
                shakiness = item.get("shakiness", 5)
                parts.append(f"vidstabtransform=input=transforms.trf:zoom=1")
            continue
        if key == "deinterlace":
            parts.append("yadif=1")
        elif key == "denoise":
            strength = int(item.get("strength", 3))
            parts.append(f"hqdn3d=1.5:1.5:{strength * 2}:{strength * 2}")
        elif key == "sharpen":
            amount = float(item.get("amount", 0.5))
            parts.append(f"unsharp=5:5:{amount}:5:5:0")
        elif key == "color":
            params = item.get("params", {})
            saturation = params.get("saturation", 1.05)
            contrast = params.get("contrast", 1.03)
            parts.append(f"eq=saturation={saturation}:contrast={contrast}")
        elif key == "upscale":
            scale = int(item.get("scale", 2))
            parts.append(f"scale=iw*{scale}:ih*{scale}:flags=lanczos")
        elif key == "grain":
            amount = int(item.get("amount", 3))
            parts.append(f"noise=alls={amount}:allf=t+u")
    return parts


def subtitle_filter_path(srt_path: Path) -> str:
    return srt_path.name


def burn_subtitles(ffmpeg: str, project: Path, source: Path, output: Path, font: str) -> None:
    srt_path = project / "07_subtitles.srt"
    if not srt_path.exists():
        return
    cmd = [
        ffmpeg, "-y", "-i", str(source),
        "-vf", f"subtitles={subtitle_filter_path(srt_path)}:force_style='FontName={font},FontSize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=24'",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-c:a", "copy",
        str(output),
    ]
    print("subtitle burn cmd:")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=project)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run Step 9 post-processing.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--profile", choices=["light", "balanced", "extreme"], default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    project = args.project_dir
    plan = load_plan(project)
    if args.profile:
        plan["profile"] = args.profile

    source = project / "08_final.mp4"
    if not source.exists():
        print(f"missing input: {source}")
        return 1

    ffmpeg = require_tool("ffmpeg")
    require_tool("ffprobe")
    output = project / plan.get("outputs", {}).get("video", "09_final_enhanced.mp4")
    output_with_subs = project / plan.get("outputs", {}).get("video_with_subs", "09_final_enhanced_with_subs.mp4")
    commands: List[str] = []

    vs_enabled = plan.get("vapoursynth", {}).get("enabled", False)
    vs_script = plan.get("vapoursynth", {}).get("script")
    vspipe = tool_path("vspipe")
    vs_script_path = None
    if vs_script:
        vs_script_path = Path(vs_script)
        if not vs_script_path.is_absolute():
            vs_script_path = project / vs_script_path

    if vs_enabled and vspipe and vs_script_path and vs_script_path.exists():
        y4m = project / "09_pre_y4m.y4m"
        vs_cmd = [vspipe, str(vs_script_path), str(y4m), "-c", "y4m"]
        commands.append(" ".join(vs_cmd))
        print("vapoursynth cmd:")
        print(" ".join(vs_cmd))
        subprocess.run(vs_cmd, check=True)
        cmd = [
            ffmpeg, "-y", "-i", str(y4m), "-i", str(source),
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "libx264", "-preset", "slow", "-crf", "16",
            "-c:a", "copy", str(output),
        ]
        commands.append(" ".join(cmd))
        subprocess.run(cmd, check=True)
        y4m.unlink(missing_ok=True)
    else:
        filters = plan.get("filters", {})
        stabilize_enabled = filters.get("stabilize", {}).get("enabled", False)
        filter_parts: List[str] = []
        if stabilize_enabled:
            shakiness = filters["stabilize"].get("shakiness", 5)
            detect_cmd = [
                ffmpeg, "-y", "-i", str(source),
                "-vf", f"vidstabdetect=shakiness={shakiness}:result=transforms.trf",
                "-f", "null", "-",
            ]
            commands.append(" ".join(detect_cmd))
            print("stabilize detect cmd:")
            print(" ".join(detect_cmd))
            subprocess.run(detect_cmd, check=True, cwd=project)
        filter_parts.extend(build_ffmpeg_filters(plan, include_stabilize=stabilize_enabled))
        crf = 16 if plan.get("profile") == "extreme" else 18
        cmd = [
            ffmpeg, "-y", "-i", str(source),
        ]
        if filter_parts:
            cmd += ["-vf", ",".join(filter_parts)]
        cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-c:a", "copy", str(output)]
        commands.append(" ".join(cmd))
        print("ffmpeg enhance cmd:")
        print(" ".join(cmd))
        subprocess.run(cmd, check=True, cwd=project)

    font = DEFAULT_FONT_CANDIDATES[0]
    if (project / "07_subtitles.srt").exists():
        burn_subtitles(ffmpeg, project, output, output_with_subs, font)
        commands.append(f"burn subtitles -> {output_with_subs.name}")

    report = project / "09_postprocess_report.md"
    report.write_text(
        "\n".join([
            "# Postprocess Report",
            "",
            f"- profile: {plan.get('profile')}",
            f"- input: {source.name}",
            f"- enhanced: {output.name}",
            f"- enhanced_with_subs: {output_with_subs.name if output_with_subs.exists() else 'skipped'}",
            f"- vapoursynth: {'enabled' if vs_enabled else 'disabled'}",
            "",
            "## Commands",
            "```",
            *commands,
            "```",
            "",
            "## De-AI check",
            "Run the final De-AI audit before approving Step 9.",
            "",
        ]),
        encoding="utf-8",
    )
    print(f"wrote: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
