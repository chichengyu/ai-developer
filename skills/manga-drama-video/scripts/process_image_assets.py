#!/usr/bin/env python3
"""Normalize and enhance generated image assets with local tools only.

Uses Pillow for format/size normalization, FFmpeg for light denoise/sharpen,
and Real-ESRGAN when available. Never asks the user to process images in an
external web tool.

Usage:
    python process_image_assets.py <image_dir> --target 1080x1920 [--denoise] [--sharpen] [--out <dir>]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path


def process_one(
    src: Path,
    out: Path,
    target_w: int,
    target_h: int,
    denoise: bool,
    sharpen: bool,
) -> Dict[str, str]:
    ffmpeg = tool_path("ffmpeg")
    filters: List[str] = []
    if target_w and target_h:
        filters.append(f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}")
    if denoise:
        filters.append("hqdn3d=2:1.5:3:2.5")
    if sharpen:
        filters.append("unsharp=5:5:0.35:5:5:0.0")
    if ffmpeg and filters:
        tmp = out.with_suffix(".tmp.png")
        cmd = [
            ffmpeg, "-y", "-loglevel", "error", "-i", str(src),
            "-vf", ",".join(filters), "-frames:v", "1", str(tmp),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and tmp.exists():
            tmp.replace(out)
            return {"engine": "ffmpeg", "filters": ",".join(filters)}

    try:
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError:
        shutil.copy2(src, out)
        return {"engine": "copy", "note": "Pillow not installed"}

    img = Image.open(src).convert("RGB")
    if target_w and target_h:
        ratio = max(target_w / img.width, target_h / img.height)
        img = img.resize((round(img.width * ratio), round(img.height * ratio)), Image.LANCZOS)
        left = (img.width - target_w) // 2
        top = (img.height - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))
    if denoise:
        img = img.filter(ImageFilter.MedianFilter(3))
    if sharpen:
        img = ImageEnhance.Sharpness(img).enhance(1.2)
    img.save(out, "PNG")
    return {"engine": "pillow", "filters": "scale" + ("+median" if denoise else "") + ("+sharpen" if sharpen else "")}


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Normalize image assets locally.")
    parser.add_argument("image_dir", type=Path)
    parser.add_argument("--target", default="1080x1920", help="WxH target, or 0x0 to skip resize")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--denoise", action="store_true")
    parser.add_argument("--sharpen", action="store_true")
    args = parser.parse_args(argv)

    target = args.target.lower().split("x")
    target_w = int(target[0]) if len(target) == 2 else 0
    target_h = int(target[1]) if len(target) == 2 else 0
    out_dir = args.out or args.image_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: List[Dict[str, str]] = []
    files = sorted(args.image_dir.glob("*.png")) + sorted(args.image_dir.glob("*.jpg")) + sorted(args.image_dir.glob("*.jpeg"))
    if not files:
        print("no image files found")
        return 1
    for src in files:
        out = out_dir / f"{src.stem}_processed.png"
        info = process_one(src, out, target_w, target_h, args.denoise, args.sharpen)
        info["source"] = str(src)
        info["output"] = str(out)
        manifest.append(info)
        print(f"processed {src.name} -> {out.name} ({info['engine']})")

    manifest_path = out_dir / "image_assets_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
