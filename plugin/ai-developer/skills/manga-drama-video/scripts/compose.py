#!/usr/bin/env python3
"""Compose the final manga-drama video.

Usage:
    python compose.py <project_dir> [--bgm <path>] [--font <fontname>]

Reads:
  <project_dir>/00_meta.json
  <project_dir>/07_timeline.json

Writes:
  <project_dir>/08_final.mp4           # soft-sub / no-sub master
  <project_dir>/08_final_with_subs.mp4  # hard-burned subtitles

Run after Step 7 has been approved.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path

DEFAULT_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "PingFang SC",
    "Arial Unicode MS",
]

CAMERA_MOVE_FILTER = {
    "static": "scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
    "pan-L": "scale={w}*1.5:{h}:force_original_aspect_ratio=increase,crop={w}:{h}:x='(in_w-out_w)*t/{dur}':y='(in_h-out_h)/2'",
    "pan-R": "scale={w}*1.5:{h}:force_original_aspect_ratio=increase,crop={w}:{h}:x='(in_w-out_w)*(1-t/{dur})':y='(in_h-out_h)/2'",
    "tilt-up": "scale={w}:{h}*1.5:force_original_aspect_ratio=increase,crop={w}:{h}:x='(in_w-out_w)/2':y='(in_h-out_h)*(1-t/{dur})'",
    "tilt-down": "scale={w}:{h}*1.5:force_original_aspect_ratio=increase,crop={w}:{h}:x='(in_w-out_w)/2':y='(in_h-out_h)*t/{dur}'",
    "push-in": "scale={w}*1.15:{h}*1.15:force_original_aspect_ratio=increase,zoompan=z='1+0.08*on/{frames}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}",
    "pull-back": "scale={w}*1.15:{h}*1.15:force_original_aspect_ratio=increase,zoompan=z='1.08-0.08*on/{frames}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}",
    "handheld": "scale={w}*1.08:{h}*1.08:force_original_aspect_ratio=increase,eq=brightness=0.02:contrast=1.02,zoompan=z='1+0.005*sin(2*PI*on/12)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}",
    "dolly-in": "scale={w}*1.2:{h}*1.2:force_original_aspect_ratio=increase,zoompan=z='1+0.12*on/{frames}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}",
    "crash-zoom": "scale={w}*1.6:{h}*1.6:force_original_aspect_ratio=increase,zoompan=z='1+0.45*on/{frames}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}",
    "whip-pan": "scale={w}*2:{h}:force_original_aspect_ratio=increase,crop={w}:{h}:x='(in_w-out_w)*min(1,1.8*t/{dur})':y='(in_h-out_h)/2'",
    "orbit": "scale=1.4*{w}:1.4*{h}:force_original_aspect_ratio=increase,crop={w}:{h}:x='(in_w-out_w)*(0.5+0.45*sin(2*PI*t/{dur}))':y='(in_h-out_h)*(0.5+0.45*cos(2*PI*t/{dur}))'",
    "dutch-angle": "scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},rotate=0.06*PI:c=black@0,scale={w}:{h}",
}


def require_tool(name: str) -> str:
    path = tool_path(name)
    if not path:
        raise SystemExit(f"missing required tool: {name}")
    return path


def aspect_to_size(aspect: str, resolution: str) -> tuple[int, int]:
    sizes = {
        "9:16": {"720p": (720, 1280), "1080p": (1080, 1920), "4K": (2160, 3840)},
        "16:9": {"720p": (1280, 720), "1080p": (1920, 1080), "4K": (3840, 2160)},
        "1:1": {"720p": (720, 720), "1080p": (1080, 1080), "4K": (2160, 2160)},
    }
    size = sizes.get(aspect, {}).get(resolution)
    if size is None:
        raise SystemExit(f"unsupported aspect ratio: {aspect} / resolution: {resolution}")
    return size


def subtitle_filter_path(srt_path: Path) -> str:
    return srt_path.name


def probe_duration(path: Path) -> float | None:
    ffprobe = tool_path("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return float(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else None
    except Exception:
        return None


def video_filter(clip_index: int, duration_ms: int, camera_move: str,
                 width: int, height: int, fps: int, source_type: str = "image",
                 pad_stop: float | None = None) -> str:
    duration_s = duration_ms / 1000
    frames = max(1, round(duration_s * fps))
    if source_type == "video":
        base = (
            f"[{clip_index}:v]trim=0:{duration_s},setpts=PTS-STARTPTS"
        )
        if pad_stop is not None and pad_stop > 0:
            base += f",tpad=stop_mode=clone:stop_duration={pad_stop:.3f}"
        return (
            f"{base},"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps}[v{clip_index}]"
        )
    template = CAMERA_MOVE_FILTER.get(camera_move, CAMERA_MOVE_FILTER["static"])
    return (
        f"[{clip_index}:v]trim=0:{duration_s},setpts=PTS-STARTPTS,"
        f"{template.format(w=width, h=height, dur=duration_s, frames=frames, fps=fps)},"
        f"setpts=PTS-STARTPTS,fps={fps}[v{clip_index}]"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Compose final manga drama video.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--bgm", type=Path, default=None, help="optional background music file")
    parser.add_argument("--font", default=None, help="CJK-capable font name for burned subs")
    args = parser.parse_args(argv)

    project = args.project_dir
    meta = json.loads((project / "00_meta.json").read_text(encoding="utf-8-sig"))
    timeline = json.loads((project / "07_timeline.json").read_text(encoding="utf-8-sig"))

    reference_bundle: dict = {}
    bundle_path = project / "reference_bundle.json"
    if bundle_path.exists():
        try:
            reference_bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            reference_bundle = {}

    bgm_path = args.bgm
    if bgm_path is None:
        ambience = reference_bundle.get("audio", {}).get("ambience_sfx")
        if ambience:
            candidate = project / ambience
            if candidate.exists():
                bgm_path = candidate
                print(f"auto BGM from reference_bundle.audio.ambience_sfx: {bgm_path}")

    width, height = aspect_to_size(meta["aspect_ratio"], meta["resolution"])
    fps = int(meta.get("framerate", 30))

    ffmpeg = require_tool("ffmpeg")
    ffprobe = require_tool("ffprobe")

    inputs: list[str] = ["-y"]
    filter_parts: list[str] = []

    for idx, shot in enumerate(timeline["shots"]):
        clip_path = None
        for key in ("lip_clip", "clip"):
            candidate = shot.get(key)
            if candidate and (project / candidate).exists():
                clip_path = project / candidate
                break
        source_type = "image"
        actual_duration = None
        if clip_path is not None:
            inputs += ["-i", str(clip_path)]
            source_type = "video"
            actual_duration = probe_duration(clip_path)
        else:
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", str(shot["duration_ms"] / 1000),
                       "-i", str(project / shot["image"])]
        shot_duration_s = shot["duration_ms"] / 1000
        pad_stop = None
        if actual_duration is not None and actual_duration + 0.05 < shot_duration_s:
            pad_stop = shot_duration_s - actual_duration
            print(
                f"warning: {clip_path.name} is {actual_duration:.2f}s, "
                f"shorter than planned {shot_duration_s:.2f}s; padding to shot length"
            )
        filter_parts.append(video_filter(idx, shot["duration_ms"], shot.get("camera_move", "static"),
                                          width, height, fps, source_type, pad_stop))

    audio_index = len(timeline["shots"])
    voice_inputs: list[tuple[str, float, float]] = []  # (file, start_in_shot_ms, end_in_shot_ms)
    for shot in timeline["shots"]:
        for vl in shot.get("voice_lines", []):
            voice_inputs.append((vl["file"], vl["start_in_shot_ms"], vl["end_in_shot_ms"]))

    voice_input_index = audio_index
    for vidx, (vfile, _, _) in enumerate(voice_inputs):
        inputs += ["-i", str(project / vfile)]
    voice_input_index = audio_index + len(voice_inputs)

    concat_inputs = "".join(f"[v{i}]" for i in range(len(timeline["shots"])))
    filter_parts.append(f"{concat_inputs}concat=n={len(timeline['shots'])}:v=1:a=0[outv]")

    if voice_inputs:
        adelay_parts = []
        amix_inputs = []
        cursor_ms = 0
        voice_index = 0
        for shot in timeline["shots"]:
            for vl in shot.get("voice_lines", []):
                adelay_parts.append(f"[{audio_index + voice_index}:a]"
                                    f"adelay={cursor_ms + vl['start_in_shot_ms']}|{cursor_ms + vl['start_in_shot_ms']}[a{len(amix_inputs)}]")
                amix_inputs.append(f"[a{len(amix_inputs)}]")
                voice_index += 1
            cursor_ms += shot.get("duration_ms", 0)
        filter_parts.extend(adelay_parts)
        filter_parts.append(
            f"{''.join(amix_inputs)}amix=inputs={len(amix_inputs)}:duration=longest:dropout_transition=0[outa]"
        )

    if bgm_path:
        bgm_index = voice_input_index
        inputs += ["-stream_loop", "-1", "-i", str(bgm_path)]
        filter_parts.append(f"[{bgm_index}:a]volume=0.35[bgma]")
        if voice_inputs:
            filter_parts.append("[outa][bgma]amix=inputs=2:duration=longest[outa]")
        else:
            filter_parts.append("[bgma]anull[outa]")

    filter_complex = ";\n".join(filter_parts)
    total_ms = sum(int(shot.get("duration_ms", 0)) for shot in timeline["shots"])

    cmd = [ffmpeg, *inputs, "-filter_complex", filter_complex, "-map", "[outv]"]
    if voice_inputs or bgm_path:
        cmd += ["-map", "[outa]"]
    if bgm_path:
        cmd += ["-t", f"{total_ms / 1000:.3f}"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-r", str(fps), "-pix_fmt", "yuv420p",
            str(project / "08_final.mp4")]
    print("ffmpeg cmd:")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)

    srt_path = project / "07_subtitles.srt"
    if srt_path.exists():
        font = args.font or DEFAULT_FONT_CANDIDATES[0]
        burned = [ffmpeg, "-y", "-i", str(project / "08_final.mp4"),
                  "-vf", f"subtitles={subtitle_filter_path(srt_path)}:force_style='FontName={font},FontSize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=24'",
                  "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                  "-c:a", "copy", str(project / "08_final_with_subs.mp4")]
        print("burned subs cmd:")
        print(" ".join(burned))
        subprocess.run(burned, check=True, cwd=project)

    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(project / "08_final.mp4")],
        capture_output=True, text=True, check=True,
    )
    print(f"final duration: {probe.stdout.strip()}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
