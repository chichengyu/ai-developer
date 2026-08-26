#!/usr/bin/env python3
"""Compose a final manga-drama video from images and audio using ffmpeg."""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ASPECT_RESOLUTIONS = {
    "9:16": "1080x1920",
    "16:9": "1920x1080",
    "1:1": "1080x1080",
}


def load_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_ffmpeg(args):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("error: ffmpeg not found on PATH", file=sys.stderr)
        return False
    cmd = [ffmpeg, "-hide_banner", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-4000:], file=sys.stderr)
        return False
    return True


def parse_resolution(value):
    value = (value or "").lower()
    if "x" in value:
        width, height = value.split("x", 1)
        return int(width), int(height)
    if value in ASPECT_RESOLUTIONS:
        return parse_resolution(ASPECT_RESOLUTIONS[value])
    return 1080, 1920


def make_clip(image_path, duration, output_path, width, height, fps, ken_burns, cinematic):
    frames = max(int(round(duration * fps)), 2)
    base_scale = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    )
    if ken_burns or cinematic:
        if cinematic:
            zoom_expr = f"min(1.0+0.12*pow(on/{frames},1.8),1.12)"
        else:
            zoom_expr = f"min(1.0+0.12*on/{frames},1.12)"
        zoom = (
            f"zoompan=z='{zoom_expr}'"
            f":d=1:x='iw/2-(iw/zoom/2)'"
            f":y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
        )
        vf = f"{base_scale},{zoom}"
    else:
        vf = base_scale
    return run_ffmpeg([
        "-loop", "1",
        "-t", str(duration),
        "-i", str(image_path),
        "-vf", vf,
        "-r", str(fps),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ])


def concat_clips(clips, output_path):
    list_path = output_path.parent / "concat_list.txt"
    with list_path.open("w", encoding="utf-8") as handle:
        for clip in clips:
            handle.write(f"file '{clip.as_posix()}'\n")
    return run_ffmpeg([
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ])


def collect_audio(project_root, audio_manifest, no_audio):
    if no_audio or not audio_manifest:
        return []
    items = []
    for kind, default_volume in (("voice", 1.0), ("bgm", 0.35), ("sfx", 0.8)):
        for entry in audio_manifest.get(kind, []):
            path = project_root / entry["file"]
            if not path.exists():
                print(f"missing audio: {path}", file=sys.stderr)
                return None
            items.append({
                "file": str(path.resolve()),
                "start_at_s": float(entry.get("start_at_s", entry.get("enter_at_s", 0.0))),
                "volume": float(entry.get("volume", default_volume)),
            })
    return items


def main(argv):
    parser = argparse.ArgumentParser(
        description="Compose final video from project assets. Reads assets/manifest.json and audio/manifest.json."
    )
    parser.add_argument("project_dir", help="Project root created by init_project.py.")
    parser.add_argument("--output", help="Final video output path.")
    parser.add_argument("--no-audio", action="store_true", help="Skip voice/BGM/SFX mixing.")
    parser.add_argument("--ken-burns", action="store_true", help="Apply slow zoom to static images.")
    parser.add_argument("--cinematic", action="store_true", help="Apply smoother cinematic ease to static camera moves.")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--resolution", help="WxH override.")
    parser.add_argument("--subs", help="Optional UTF-8 .srt file to burn into the video.")
    args = parser.parse_args(argv)

    root = Path(args.project_dir).resolve()
    manifest = load_json(root / "assets" / "manifest.json")
    audio_manifest = load_json(root / "audio" / "manifest.json")
    if not manifest:
        print(f"missing manifest: {root / 'assets' / 'manifest.json'}", file=sys.stderr)
        return 1

    shots = manifest.get("shots") or []
    if not shots:
        print("assets/manifest.json has no shots", file=sys.stderr)
        return 1

    width, height = parse_resolution(args.resolution or manifest.get("resolution"))
    fps = args.fps
    output = Path(args.output) if args.output else root / "video" / "final" / f"{manifest.get('project_slug') or root.name}_final.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mdvh-") as temp_dir:
        temp = Path(temp_dir)
        clips = []
        for index, shot in enumerate(shots):
            image = root / shot["image"]
            if not image.exists():
                print(f"missing image: {image}", file=sys.stderr)
                return 1
            duration = float(shot.get("duration_sec") or 4.0)
            clip_path = temp / f"clip_{index:03d}.mp4"
            if not make_clip(image, duration, clip_path, width, height, fps, args.ken_burns, args.cinematic):
                return 1
            clips.append(clip_path)

        total_duration = sum(float(shot.get("duration_sec") or 4.0) for shot in shots)
        combined = temp / "combined.mp4"
        if not concat_clips(clips, combined):
            return 1

        audio_items = collect_audio(root, audio_manifest, args.no_audio)
        if audio_items is None:
            return 1
        cmd = []
        if audio_items:
            inputs = ["-i", str(combined)]
            filters = []
            for index, item in enumerate(audio_items):
                inputs += ["-i", item["file"]]
                start_ms = int(round(item["start_at_s"] * 1000))
                filters.append(
                    f"[{index + 1}:a]aresample=44100,"
                    f"adelay={start_ms}|{start_ms},volume={item['volume']}[a{index}]"
                )
            mix_labels = "".join(f"[a{index}]" for index in range(len(audio_items)))
            filters.append(f"{mix_labels}amix=inputs={len(audio_items)}:duration=longest:dropout_transition=2[aout]")
            cmd = [
                *inputs,
                "-filter_complex", ";".join(filters),
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-t", str(total_duration),
            ]
        else:
            cmd = ["-i", str(combined), "-c", "copy"]

        if args.subs:
            subs = Path(args.subs).resolve()
            if not subs.exists():
                print(f"missing subtitles: {subs}", file=sys.stderr)
                return 1
            cmd += ["-vf", f"subtitles='{subs.as_posix()}'"]
            if not audio_items:
                cmd += ["-c:v", "libx264"]

        cmd += [str(output)]
        if not run_ffmpeg(cmd):
            return 1

    print(f"wrote: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
