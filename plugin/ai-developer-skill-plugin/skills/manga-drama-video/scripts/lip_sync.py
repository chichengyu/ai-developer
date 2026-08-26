#!/usr/bin/env python3
"""Drive talking-head lip sync for speaking shots.

Usage:
    python lip_sync.py <project_dir> --shot SH1.1 --engine auto

Reads:
    <project_dir>/05_video/manifest.json (or 05_images/)
    <project_dir>/06_voice/index.json
    <project_dir>/engine_plan.json

Writes:
    <project_dir>/06_face/<shot_id>_lip.mp4
    <project_dir>/06_face/index.json
    <project_dir>/06_face/lip_sync_report.md

ComfyUI engines use <project_dir>/talking_head_workflow.json when present.
CLI engines use engine_plan.json `talking_head.params.command_template` with
{input} {audio} {output} placeholders.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path
from install_image_engine import probe_comfyui
from install_video_engine import (
    comfy_python,
    default_video_runtime_dir,
    detect_audio_lip_sync,
    detect_talking_head,
    find_comfyui_dir,
)
from generate_video import validate_workflow


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def pick_input(project: Path, shot_id: str) -> Optional[Path]:
    video_manifest = load_json(project / "05_video" / "manifest.json")
    if isinstance(video_manifest, list):
        for item in video_manifest:
            if item.get("shot_id") == shot_id and item.get("clip"):
                path = project / item["clip"]
                if path.exists():
                    return path
    image = project / "05_images" / f"{shot_id}.png"
    if image.exists():
        return image
    return None


def pick_audio(project: Path, shot_id: str) -> Optional[Path]:
    index = load_json(project / "06_voice" / "index.json")
    if not isinstance(index, list):
        return None
    scene_prefix = shot_id.split(".")[0] if "." in shot_id else shot_id
    for entry in index:
        if entry.get("shot_id") == shot_id and entry.get("file"):
            path = project / entry["file"]
            if path.exists():
                return path
        file_name = str(entry.get("file", ""))
        if entry.get("line_id", "").startswith(scene_prefix) and file_name:
            path = project / file_name
            if path.exists():
                return path
    return None


def submit_comfyui(workflow: Dict[str, Any], comfy_url: str, output: Path, timeout: int = 1800) -> bool:
    import time

    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    try:
        req = urllib.request.Request(
            comfy_url.rstrip("/") + "/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"talking-head ComfyUI request failed: {exc}")
        return False
    prompt_id = info.get("prompt_id")
    if not prompt_id:
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        try:
            with urllib.request.urlopen(comfy_url.rstrip("/") + "/history/" + prompt_id, timeout=10) as resp:
                history = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        if prompt_id not in history:
            continue
        entry = history[prompt_id]
        if entry.get("status", {}).get("status_str") == "error":
            print(json.dumps(entry.get("status", {}), ensure_ascii=False, indent=2)[:2000])
            return False
        for node in entry.get("outputs", {}).values():
            videos = node.get("gifs") or node.get("videos") or node.get("images")
            if videos:
                item = videos[0]
                url = (
                    comfy_url.rstrip("/") + "/view?filename=" + item.get("filename", "")
                    + "&subfolder=" + item.get("subfolder", "")
                    + "&type=" + item.get("type", "output")
                )
                try:
                    urllib.request.urlretrieve(url, str(output))
                    return output.exists()
                except Exception as exc:
                    print(f"download failed: {exc}")
                    return False
    return False


def run_cli(template: str, input_path: Path, audio_path: Path, output: Path) -> bool:
    command = template.format(input=str(input_path), audio=str(audio_path), output=str(output))
    print(f"$ {command}")
    result = subprocess.run(command, shell=True)
    return result.returncode == 0 and output.exists()


def probe_audio_duration(path: Path) -> float:
    ffprobe = tool_path("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def run_wav2lip(input_path: Path, audio_path: Path, output: Path, timeout: int = 1800) -> bool:
    wdir = default_video_runtime_dir() / "wav2lip"
    py = os.environ.get("MANGA_PYTHON") or comfy_python(find_comfyui_dir())
    ffmpeg = tool_path("ffmpeg")
    if not ffmpeg or not (wdir / "inference.py").exists() or not (wdir / "checkpoints" / "wav2lip.pth").exists():
        print("Wav2Lip not installed; run python scripts/install_video_engine.py <project> --install --models wav2lip")
        return False
    (wdir / "temp").mkdir(parents=True, exist_ok=True)
    inference_py = wdir / "inference.py"
    if inference_py.exists() and "frame_index = 0" not in inference_py.read_text(encoding="utf-8", errors="replace"):
        try:
            from install_video_engine import patch_wav2lip_compat
            patch_wav2lip_compat(wdir)
        except Exception as exc:
            print(f"Wav2Lip compatibility patch skipped: {exc}")
    work_dir = output.parent / ".wav2lip"
    work_dir.mkdir(parents=True, exist_ok=True)
    face_video = input_path
    if input_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        duration = probe_audio_duration(audio_path) or 3.0
        face_video = work_dir / "face_static.mp4"
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-loop", "1", "-i", str(input_path),
             "-t", f"{duration:.3f}", "-r", "25", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(face_video)],
            capture_output=True,
            text=True,
            check=True,
        )
    wav_audio = work_dir / "audio.wav"
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(audio_path), "-ar", "16000", "-ac", "1", str(wav_audio)],
        capture_output=True,
        text=True,
        check=True,
    )
    raw_out = work_dir / "wav2lip_raw.mp4"
    cmd = [
        str(py),
        str(wdir / "inference.py"),
        "--checkpoint_path", str(wdir / "checkpoints" / "wav2lip.pth"),
        "--face", str(face_video),
        "--audio", str(wav_audio),
        "--outfile", str(raw_out),
    ]
    numba_cache = work_dir / "numba_cache"
    numba_cache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["NUMBA_CACHE_DIR"] = str(numba_cache)
    print("wav2lip cmd:")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=str(wdir), env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print(result.stdout[-1500:])
        print(result.stderr[-1500:])
        return False
    if not raw_out.exists():
        return False
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(raw_out), "-i", str(audio_path),
         "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
         "-shortest", str(output)],
        capture_output=True,
        text=True,
        check=True,
    )
    if output.exists():
        for png in work_dir.glob("frame_*.png"):
            try:
                png.unlink()
            except OSError:
                pass
    return output.exists()


def sanitize_input_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return base or "asset"


def upload_image_api(comfy_url: str, path: Path, prefix: str) -> Optional[str]:
    boundary = "----manga" + uuid.uuid4().hex
    filename = f"{prefix}_{sanitize_input_name(path.name)}"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="image"; filename="' + filename + '"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + path.read_bytes() + (
        f"\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
        "true\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="type"\r\n\r\n'
        "input\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    try:
        req = urllib.request.Request(
            comfy_url.rstrip("/") + "/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8", "replace"))
        return result.get("name") or filename
    except Exception as exc:
        print(f"image upload failed: {exc}")
        return None


def builtin_liveportrait_workflow(
    source_path: Path,
    driving_path: Path,
    audio_path: Path,
    comfy_url: str,
    fps: float,
) -> Dict[str, Any]:
    source_name = upload_image_api(comfy_url, source_path, "lp_src")
    if source_name is None:
        raise RuntimeError("source image upload failed")
    return {
        "1": {
            "class_type": "DownloadAndLoadLivePortraitModels",
            "inputs": {"precision": "fp16", "mode": "human"},
        },
        "2": {
            "class_type": "LivePortraitLoadFaceAlignmentCropper",
            "inputs": {
                "face_detector": "blazeface_back_camera",
                "landmarkrunner_device": "torch_gpu",
                "face_detector_device": "cuda",
                "face_detector_dtype": "fp16",
                "keep_model_loaded": True,
            },
        },
        "3": {"class_type": "LoadImage", "inputs": {"image": source_name}},
        "4": {
            "class_type": "LivePortraitCropper",
            "inputs": {
                "pipeline": ["1", 0],
                "cropper": ["2", 0],
                "source_image": ["3", 0],
                "dsize": 512,
                "scale": 2.3,
                "vx_ratio": 0.0,
                "vy_ratio": -0.125,
                "face_index": 0,
                "face_index_order": "large-small",
                "rotate": True,
            },
        },
        "5": {
            "class_type": "VHS_LoadVideoPath",
            "inputs": {
                "video": str(driving_path),
                "force_rate": 0,
                "custom_width": 0,
                "custom_height": 0,
                "frame_load_cap": 0,
                "skip_first_frames": 0,
                "select_every_nth": 1,
                "format": "None",
            },
        },
        "6": {
            "class_type": "LivePortraitProcess",
            "inputs": {
                "pipeline": ["1", 0],
                "crop_info": ["4", 1],
                "source_image": ["3", 0],
                "driving_images": ["5", 0],
                "lip_zero": False,
                "lip_zero_threshold": 0.03,
                "stitching": True,
                "delta_multiplier": 1.0,
                "mismatch_method": "constant",
                "relative_motion_mode": "relative",
                "driving_smooth_observation_variance": 0.000003,
            },
        },
        "7": {
            "class_type": "LivePortraitComposite",
            "inputs": {
                "source_image": ["3", 0],
                "cropped_image": ["4", 0],
                "liveportrait_out": ["6", 1],
            },
        },
        "8": {
            "class_type": "VHS_LoadAudio",
            "inputs": {"audio_file": str(audio_path), "seek_seconds": 0, "duration": 0},
        },
        "9": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["7", 0],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": "manga_lip",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
                "audio": ["8", 0],
            },
        },
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Lip-sync speaking shots.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--shot", required=True)
    parser.add_argument("--engine", choices=("auto", "comfyui", "liveportrait", "sadtalker", "musetalk", "muse-talk", "wav2lip", "hallo"), default="auto")
    parser.add_argument("--require-audio-sync", action="store_true", help="fail unless a true audio-driven lip-sync engine is available")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--audio", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--driving-video", type=Path, default=None)
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument("--timeout", type=int, default=1800, help="seconds to wait for a talking-head engine (default 1800)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project = args.project_dir
    input_path = args.input or pick_input(project, args.shot)
    audio_path = args.audio or pick_audio(project, args.shot)
    if not input_path or not audio_path:
        print(f"missing input or audio for {args.shot}")
        return 1
    face_dir = project / "06_face"
    face_dir.mkdir(parents=True, exist_ok=True)
    output = args.output or face_dir / f"{args.shot}_lip.mp4"

    engine_plan = load_json(project / "engine_plan.json")
    plan_engine = engine_plan.get("engines", {}).get("talking_head", {})
    audio_plan = engine_plan.get("engines", {}).get("audio_lip_sync", {})
    has_audio_workflow = False
    workflow_path = project / "talking_head_workflow.json"
    if workflow_path.exists():
        workflow_text = workflow_path.read_text(encoding="utf-8", errors="replace").lower()
        has_audio_workflow = "audio" in workflow_text and ("video" in workflow_text or "audio_to" in workflow_text)
    chosen = args.engine
    if chosen == "auto":
        chosen = audio_plan.get("name") if audio_plan.get("status") == "available" else plan_engine.get("name", "comfyui")
    if args.require_audio_sync and audio_plan.get("status") != "available" and not has_audio_workflow:
        report = [
            "# Lip Sync Report",
            "",
            f"- shot: {args.shot}",
            f"- engine: {chosen}",
            f"- require_audio_sync: true",
            f"- status: blocked",
            f"- audio_lip_sync: {audio_plan.get('status')}",
            f"- message: {audio_plan.get('params', {}).get('message', 'no audio-driven lip-sync engine found')}",
        ]
        (project / "06_face" / "lip_sync_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        print("\n".join(report))
        return 1
    comfy = probe_comfyui()
    local = detect_talking_head(find_comfyui_dir())
    audio_sync = detect_audio_lip_sync(find_comfyui_dir(), default_video_runtime_dir())
    report: List[str] = [
        f"# Lip Sync Report", "",
        f"- shot: {args.shot}",
        f"- engine: {chosen}",
        f"- audio_driven: {bool(audio_plan.get('status') == 'available' or has_audio_workflow)}",
        f"- local_audio_sync: {bool(audio_sync.get('available'))}",
        "",
    ]
    ok = False

    if chosen == "comfyui":
        if not comfy:
            report.append("ComfyUI API not reachable")
        else:
            workflow_path = project / "talking_head_workflow.json"
            if not workflow_path.exists():
                comfy_dir = find_comfyui_dir()
                nodes = detect_talking_head(comfy_dir).get("comfyui_nodes", [])
                if comfy_dir is not None and any("liveportrait" in name.lower() for name in nodes):
                    driving_path = args.driving_video or input_path
                    if driving_path.suffix.lower() not in (".mp4", ".mov", ".webm", ".mkv"):
                        report.append(f"driving video required for LivePortrait; got {driving_path}")
                    else:
                        workflow = builtin_liveportrait_workflow(input_path, driving_path, audio_path, "http://127.0.0.1:8188", args.fps)
                        if args.dry_run:
                            print(json.dumps(workflow, ensure_ascii=False, indent=2))
                            return 0
                        if not validate_workflow(workflow, "http://127.0.0.1:8188"):
                            report.append("built-in LivePortrait workflow failed validation")
                        else:
                            ok = submit_comfyui(workflow, "http://127.0.0.1:8188", output, args.timeout)
                            report.append("built-in LivePortrait workflow executed" if ok else "built-in LivePortrait workflow failed")
                else:
                    report.append("talking_head_workflow.json not found; export a workflow from ComfyUI and add placeholders {input} {audio} {output}")
            else:
                workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
                workflow_text = json.dumps(workflow).replace("{input}", str(input_path)).replace("{audio}", str(audio_path)).replace("{output}", str(output))
                rendered = json.loads(workflow_text)
                if args.dry_run:
                    print(workflow_text)
                    return 0
                ok = submit_comfyui(rendered, "http://127.0.0.1:8188", output, args.timeout)
                report.append("ComfyUI workflow executed" if ok else "ComfyUI workflow failed")
    elif chosen == "wav2lip":
        if args.dry_run:
            print("Wav2Lip audio-driven lip sync (dry run)")
            return 0
        ok = run_wav2lip(input_path, audio_path, output, args.timeout)
        report.append("Wav2Lip audio-driven lip sync succeeded" if ok else "Wav2Lip audio-driven lip sync failed")
    elif chosen in ("liveportrait", "sadtalker", "musetalk", "muse-talk", "hallo"):
        cli = shutil.which(chosen)
        template = plan_engine.get("params", {}).get("command_template")
        if not cli and not template:
            report.append(f"{chosen} CLI not found and no command_template configured in engine_plan.json")
        elif template:
            if args.dry_run:
                print(template.format(input=str(input_path), audio=str(audio_path), output=str(output)))
                return 0
            ok = run_cli(template, input_path, audio_path, output)
            report.append(f"CLI command {'succeeded' if ok else 'failed'}")
        else:
            report.append(f"{chosen} CLI found; set engine_plan.json talking_head.params.command_template with {{input}} {{audio}} {{output}} to automate")
    else:
        report.append(f"engine not available: {chosen}; install a local talking-head tool or pass --engine comfyui/liveportrait/sadtalker/musetalk/hallo")

    if not ok:
        report.append("status: blocked")
    else:
        report.append(f"status: ok")
        report.append(f"output: {output}")
        index_path = face_dir / "index.json"
        index = []
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
        index.append({
            "shot_id": args.shot,
            "input": str(input_path),
            "audio": str(audio_path),
            "output": str(output),
            "engine": chosen,
        })
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (face_dir / "lip_sync_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
