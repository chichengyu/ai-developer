#!/usr/bin/env python3
"""Detect or install local video-diffusion and talking-head engines.

Usage:
    python install_video_engine.py <project_dir> --check
    python install_video_engine.py <project_dir> --install [--models wan]
    python install_video_engine.py <project_dir> --auto
    python install_video_engine.py <project_dir> --dry-run
    python install_video_engine.py <project_dir> --start

Writes:
    <project_dir>/video_engine_report.json
    <project_dir>/video_engine_report.md

--auto detects the current hardware, installs ComfyUI when missing, installs
the matching video models and talking-head models, then starts the engine.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path
from install_image_engine import probe_comfyui, probe_size
from hardware_profile import detect_hardware_profile


COMFYUI_URL = "https://github.com/comfyanonymous/ComfyUI.git"
WAV2LIP_URL = "https://github.com/Rudrabha/Wav2Lip.git"
CUSTOM_NODES = {
    "wan": "https://github.com/kijai/ComfyUI-WanVideoWrapper",
    "hunyuan": "https://github.com/kijai/ComfyUI-HunyuanVideoWrapper",
    "video_helper": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite",
    "liveportrait": "https://github.com/kijai/ComfyUI-LivePortraitKJ",
}

MODEL_URLS: Dict[str, List[str]] = {
    "wan": [
        "https://hf-mirror.com/Kijai/WanVideo_comfy/resolve/main/Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors",
        "https://www.modelscope.cn/models/Kijai/WanVideo_comfy/resolve/master/Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors",
        "https://hf-mirror.com/Kijai/WanVideo_comfy/resolve/main/Wan2_1-Anisora-I2V-480P-14B_fp8_e4m3fn.safetensors",
    ],
    "wan_clip": [
        "https://hf-mirror.com/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-fp8_e4m3fn.safetensors",
        "https://www.modelscope.cn/models/Kijai/WanVideo_comfy/resolve/master/umt5-xxl-enc-fp8_e4m3fn.safetensors",
    ],
    "wan_vae": [
        "https://hf-mirror.com/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors",
        "https://www.modelscope.cn/models/Kijai/WanVideo_comfy/resolve/master/Wan2_1_VAE_bf16.safetensors",
    ],
    "wan_clip_vision": [
        "https://hf-mirror.com/Kijai/WanVideo_comfy/resolve/main/open-clip-xlm-roberta-large-vit-huge-14_visual_fp16.safetensors",
        "https://www.modelscope.cn/models/Kijai/WanVideo_comfy/resolve/master/open-clip-xlm-roberta-large-vit-huge-14_visual_fp16.safetensors",
    ],
    "liveportrait_models": [
        "https://hf-mirror.com/Kijai/LivePortrait_safetensors/resolve/main/appearance_feature_extractor.safetensors",
        "https://hf-mirror.com/Kijai/LivePortrait_safetensors/resolve/main/motion_extractor.safetensors",
        "https://hf-mirror.com/Kijai/LivePortrait_safetensors/resolve/main/spade_generator.safetensors",
        "https://hf-mirror.com/Kijai/LivePortrait_safetensors/resolve/main/stitching_retargeting_module.safetensors",
        "https://hf-mirror.com/Kijai/LivePortrait_safetensors/resolve/main/warping_module.safetensors",
    ],
    "hunyuan": [
        "https://hf-mirror.com/tencent/HunyuanVideo/resolve/main/hunyuan_video_t2v_720p_bf16.safetensors",
        "https://huggingface.co/tencent/HunyuanVideo/resolve/main/hunyuan_video_t2v_720p_bf16.safetensors",
    ],
    "ltx": [
        "https://hf-mirror.com/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors",
        "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors",
    ],
    "ltx_text_encoder": [
        "https://hf-mirror.com/Comfy-Org/mochi_preview_repackaged/resolve/main/split_files/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors",
        "https://hf-mirror.com/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors",
        "https://hf-mirror.com/Comfy-Org/mochi_preview_repackaged/resolve/main/split_files/text_encoders/t5xxl_fp16.safetensors",
        "https://huggingface.co/Comfy-Org/mochi_preview_repackaged/resolve/main/split_files/text_encoders/t5xxl_fp16.safetensors",
    ],
    "wav2lip": [
        "https://hf-mirror.com/ruslanmv/avatar-renderer/resolve/main/wav2lip/wav2lip_gan.pth",
        "https://huggingface.co/ruslanmv/avatar-renderer/resolve/main/wav2lip/wav2lip_gan.pth",
    ],
    "wav2lip_s3fd": [
        "https://hf-mirror.com/TonyD2046/sadtalker-01/resolve/main/wav2lip/s3fd.pth",
        "https://huggingface.co/TonyD2046/sadtalker-01/resolve/main/wav2lip/s3fd.pth",
    ],
}


def default_video_runtime_dir() -> Path:
    override = os.environ.get("MANGA_VIDEO_RUNTIME_DIR")
    if override:
        return Path(override)
    if Path("E:/soft").is_dir():
        return Path("E:/soft/manga-drama-video")
    local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    return Path(local) / "manga-drama-video"


def find_comfyui_dir() -> Optional[Path]:
    candidates = []
    comfy_override = os.environ.get("MANGA_COMFYUI_DIR")
    if comfy_override:
        candidates.append(Path(comfy_override))
    candidates += [
        default_video_runtime_dir() / "ComfyUI",
        Path("E:/soft/manga-drama-image"),
        Path("E:/soft/manga-drama-image/ComfyUI"),
        Path("E:/soft/ComfyUI"),
        Path.cwd() / "ComfyUI",
    ]
    for candidate in candidates:
        if (candidate / "main.py").is_file():
            return candidate
    return None


def comfy_python(comfy_dir: Path) -> str:
    """Return the Python interpreter that owns the ComfyUI runtime."""
    candidates = []
    venv_override = os.environ.get("MANGA_VENV_DIR")
    if venv_override:
        candidates.append(Path(venv_override) / "Scripts" / "python.exe")
    candidates += [
        comfy_dir / "venv" / "Scripts" / "python.exe",
        comfy_dir.parent / "venv" / "Scripts" / "python.exe",
        Path("E:/soft/manga-drama-image/venv-comfyui/Scripts/python.exe"),
        Path("E:/soft/manga-drama-image/venv/Scripts/python.exe"),
        Path("E:/soft/manga-drama-video/venv/Scripts/python.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return tool_path("python") or sys.executable


def detect_custom_nodes(comfy_dir: Optional[Path]) -> List[str]:
    if comfy_dir is None:
        return []
    node_dir = comfy_dir / "custom_nodes"
    if not node_dir.is_dir():
        return []
    return sorted(
        p.name
        for p in node_dir.iterdir()
        if p.is_dir() and not p.name.startswith("__") and (p / "__init__.py").exists()
    )


def scan_model_files(comfy_dir: Optional[Path], runtime_dir: Path) -> Dict[str, List[str]]:
    roots: List[Tuple[Path, str]] = [
        (runtime_dir / "video-models" / "wan", "wan"),
        (runtime_dir / "video-models" / "hunyuan", "hunyuan"),
        (runtime_dir / "video-models" / "ltx", "ltx"),
    ]
    if comfy_dir is not None:
        roots.extend([
            (comfy_dir / "models" / "diffusion_models", "diffusion"),
            (comfy_dir / "models" / "checkpoints", "checkpoints"),
            (comfy_dir / "models" / "unet", "unet"),
            (comfy_dir / "models" / "vae", "vae"),
            (comfy_dir / "models" / "text_encoders", "text_encoder"),
            (comfy_dir / "models" / "liveportrait", "liveportrait"),
            (comfy_dir / "models" / "clip_vision", "clip_vision"),
        ])
    found: Dict[str, List[str]] = {
        "wan": [], "hunyuan": [], "ltx": [],
        "vae": [], "text_encoder": [], "liveportrait": [], "other": [],
        "clip_vision": [],
    }
    for root, role in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.safetensors"):
            if list(root.glob(path.name + ".part*")):
                continue
            if path.stat().st_size < 1024 * 1024 and role != "liveportrait":
                continue
            name = path.name.lower()
            if role == "vae":
                found["vae"].append(str(path))
            elif role == "text_encoder":
                found["text_encoder"].append(str(path))
            elif role == "liveportrait":
                found["liveportrait"].append(str(path))
            elif role == "clip_vision":
                found["clip_vision"].append(str(path))
            elif role == "wan":
                found["wan"].append(str(path))
            elif role == "hunyuan":
                found["hunyuan"].append(str(path))
            elif role == "ltx":
                found["ltx"].append(str(path))
            elif role == "checkpoints":
                if "ltx" in name:
                    found["ltx"].append(str(path))
                elif "wan" in name:
                    found["wan"].append(str(path))
                elif "hunyuan" in name or "hyvideo" in name:
                    found["hunyuan"].append(str(path))
                else:
                    found["other"].append(str(path))
            elif "wan" in name or "hyvideo" in name or "hunyuan" in name or "ltx" in name:
                if "vae" in name or "umt5" in name or "t5" in name or "clip" in name:
                    found["other"].append(str(path))
                elif "wan" in name:
                    found["wan"].append(str(path))
                elif "hunyuan" in name or "hyvideo" in name:
                    found["hunyuan"].append(str(path))
                else:
                    found["ltx"].append(str(path))
            else:
                found["other"].append(str(path))
    return found


def detect_talking_head(comfy_dir: Optional[Path]) -> Dict[str, Any]:
    cli_tools = [name for name in ("liveportrait", "sadtalker", "musetalk", "hallo") if shutil.which(name)]
    nodes = detect_custom_nodes(comfy_dir)
    node_hits = [
        name for name in nodes
        if any(key in name.lower() for key in ("liveportrait", "sadtalker", "musetalk", "hallo", "talkinghead"))
    ]
    return {
        "cli": cli_tools,
        "comfyui_nodes": node_hits,
        "available": bool(cli_tools or node_hits),
    }


def detect_audio_lip_sync(comfy_dir: Optional[Path], runtime_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Detect engines that can drive mouth shapes from an audio file."""
    cli_tools = [
        name for name in ("wav2lip", "sadtalker", "musetalk", "muse-talk", "hallo")
        if shutil.which(name)
    ]
    wav2lip_dir = runtime_dir / "wav2lip" if runtime_dir else None
    if (
        wav2lip_dir is not None
        and (wav2lip_dir / "inference.py").exists()
        and (wav2lip_dir / "checkpoints" / "wav2lip.pth").exists()
    ):
        if "wav2lip" not in cli_tools:
            cli_tools.append("wav2lip")
    nodes = detect_custom_nodes(comfy_dir)
    node_hits = [
        name for name in nodes
        if any(key in name.lower() for key in ("sadtalker", "musetalk", "wav2lip", "hallo", "talkinghead"))
        and "liveportrait" not in name.lower()
    ]
    return {
        "cli": cli_tools,
        "comfyui_nodes": node_hits,
        "available": bool(cli_tools or node_hits),
        "message": "LivePortrait is motion transfer only; audio-driven lip sync requires SadTalker/MuseTalk/Wav2Lip/Hallo or Wan 2.2 audio-to-video",
    }


def write_report(project: Path, status: Dict[str, Any]) -> None:
    project.mkdir(parents=True, exist_ok=True)
    path = project / "video_engine_report.json"
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = project / "video_engine_report.md"
    md.write_text(
        "\n".join([
            "# Video Engine Report",
            "",
            f"- comfyui_api: {status.get('comfyui_api')}",
            f"- comfyui_dir: {status.get('comfyui_dir') or 'not found'}",
            f"- custom_nodes: {', '.join(status.get('custom_nodes', [])) or 'none'}",
            f"- wan_models: {', '.join(status.get('models', {}).get('wan', [])) or 'none'}",
            f"- hunyuan_models: {', '.join(status.get('models', {}).get('hunyuan', [])) or 'none'}",
            f"- ltx_models: {', '.join(status.get('models', {}).get('ltx', [])) or 'none'}",
            f"- wan_clip_vision: {', '.join(status.get('models', {}).get('clip_vision', [])) or 'none'}",
            f"- ltx_text_encoder: {', '.join(status.get('models', {}).get('text_encoder', [])) or 'none'}",
            f"- talking_head: {json.dumps(status.get('talking_head', {}), ensure_ascii=False)}",
            f"- audio_lip_sync: {json.dumps(status.get('audio_lip_sync', {}), ensure_ascii=False)}",
        ]) + "\n",
        encoding="utf-8",
    )
    print(f"wrote: {path}")
    print(f"wrote: {md}")


def clone_node(comfy_dir: Path, name: str, url: str) -> bool:
    dest = comfy_dir / "custom_nodes" / name
    if (dest / "__init__.py").exists() or dest.is_dir():
        print(f"node already present: {name}")
        return True
    git = shutil.which("git")
    if not git:
        print("git is required to install custom nodes")
        return False
    print(f"cloning {name} ...")
    result = subprocess.run([git, "clone", "--depth", "1", url, str(dest)], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-1200:])
        return False
    requirements = dest / "requirements.txt"
    if requirements.exists():
        py = os.environ.get("MANGA_PYTHON") or comfy_python(comfy_dir)
        print(f"installing requirements for {name} ...")
        subprocess.run([py, "-m", "pip", "install", "-r", str(requirements)], capture_output=True, text=True)
    return True


def download_model_file(urls: List[str], dest: Path) -> bool:
    size = probe_size(urls[0]) if urls else None
    if size is None:
        print(f"cannot determine size for {urls[0] if urls else 'unknown'}; using streaming download")
        for url in urls:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                req = urllib.request.Request(url, headers={"User-Agent": "manga-drama-video/1.0"})
                with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as fh:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
                if dest.stat().st_size > 1024 * 1024:
                    return True
            except Exception as exc:
                print(f"download failed: {exc}")
            dest.unlink(missing_ok=True)
        return False
    from install_image_engine import resilient_multi_download
    return resilient_multi_download(urls, dest, size)


def install_models(runtime_dir: Path, models: List[str], model_url_override: Optional[str], comfy_dir: Optional[Path] = None) -> Dict[str, str]:
    status: Dict[str, str] = {}
    for key in models:
        if key == "wav2lip":
            py = os.environ.get("MANGA_PYTHON") or (comfy_python(comfy_dir) if comfy_dir else None) or tool_path("python") or sys.executable
            status["wav2lip"] = "ok" if install_wav2lip(runtime_dir, Path(py)) else "blocked-install"
            continue
        if key == "liveportrait":
            target_dir = comfy_dir / "models" / "liveportrait" if comfy_dir else runtime_dir / "video-models" / "liveportrait"
            target_dir.mkdir(parents=True, exist_ok=True)
            urls = MODEL_URLS.get("liveportrait_models", [])
            ok_count = 0
            for url in urls:
                dest = target_dir / Path(url).name
                if dest.exists() or download_model_file([url], dest):
                    ok_count += 1
                else:
                    status["liveportrait"] = "blocked-download"
                    break
            if ok_count == len(urls):
                status["liveportrait"] = "ok"
            continue
        if key == "ltx":
            model_dir = comfy_dir / "models" / "checkpoints" if comfy_dir else runtime_dir / "video-models" / "ltx"
            model_dir.mkdir(parents=True, exist_ok=True)
            urls = [model_url_override] if model_url_override else MODEL_URLS.get("ltx", [])
            dest = model_dir / Path(urls[0]).name
            model_needed = not (
                dest.exists()
                and dest.stat().st_size > 1024 * 1024 * 1024
                and not list(model_dir.glob(dest.name + ".part*"))
            )
            te_dir = comfy_dir / "models" / "text_encoders" if comfy_dir else runtime_dir / "video-models" / "text_encoders"
            te_dir.mkdir(parents=True, exist_ok=True)
            existing_te = [
                p for p in te_dir.glob("t5xxl*.safetensors")
                if p.stat().st_size > 1024 * 1024 * 1024 and not list(te_dir.glob(p.name + ".part*"))
            ]
            te_result = [False]
            te_thread = None
            if not existing_te:
                te_urls = MODEL_URLS.get("ltx_text_encoder", [])
                te_urls = order_ltx_text_encoder_urls(te_urls)
                te_dest = te_dir / Path(te_urls[0]).name
                print(f"downloading LTX text encoder: {te_dest.name}")

                def _download_te() -> None:
                    te_result[0] = download_model_file(te_urls, te_dest)

                te_thread = threading.Thread(target=_download_te, daemon=True)
                te_thread.start()
            if model_needed:
                if urls and download_model_file(urls, dest):
                    status["ltx"] = "ok"
                else:
                    status["ltx"] = "blocked-download"
            else:
                status["ltx"] = f"already-{dest.name}"
            if te_thread is not None:
                te_thread.join()
                if te_result[0]:
                    status["ltx_text_encoder"] = "ok"
                else:
                    te_dest.unlink(missing_ok=True)
                    status["ltx_text_encoder"] = "blocked-download"
            else:
                status["ltx_text_encoder"] = f"already-{existing_te[0].name}"
            continue
        model_dir = comfy_dir / "models" / "diffusion_models" if comfy_dir else runtime_dir / "video-models" / key
        model_dir.mkdir(parents=True, exist_ok=True)
        existing = [
            p for p in model_dir.glob("*.safetensors")
            if p.stat().st_size > 1024 * 1024 * 1024 and not list(model_dir.glob(p.name + ".part*"))
        ]
        if existing:
            status[key] = f"already-{existing[0].name}"
            if key != "wan":
                continue
        else:
            urls = [model_url_override] if model_url_override else MODEL_URLS.get(key, [])
            if not urls:
                status[key] = "blocked-no-url"
                continue
            ok = False
            dest = model_dir / Path(urls[0]).name
            print(f"downloading {key} model: {dest.name}")
            if download_model_file(urls, dest):
                status[key] = "ok"
                ok = True
            else:
                dest.unlink(missing_ok=True)
            if not ok:
                status[key] = "blocked-download"
                if key != "wan":
                    continue
        if key == "wan":
            for aux_key, subdir in (("wan_clip", "text_encoders"), ("wan_vae", "vae")):
                aux_dir = comfy_dir / "models" / subdir if comfy_dir else runtime_dir / "video-models" / subdir
                aux_dir.mkdir(parents=True, exist_ok=True)
                aux_urls = MODEL_URLS.get(aux_key, [])
                aux_url = aux_urls[0] if aux_urls else None
                if not aux_url:
                    status[aux_key] = "blocked-no-url"
                    continue
                aux_dest = aux_dir / Path(aux_url).name
                if aux_dest.exists():
                    status[aux_key] = "already"
                elif download_model_file(aux_urls, aux_dest):
                    status[aux_key] = "ok"
                else:
                    status[aux_key] = "blocked-download"
            cv_dir = comfy_dir / "models" / "clip_vision" if comfy_dir else runtime_dir / "video-models" / "clip_vision"
            cv_dir.mkdir(parents=True, exist_ok=True)
            cv_urls = MODEL_URLS.get("wan_clip_vision", [])
            cv_url = cv_urls[0] if cv_urls else None
            if cv_url:
                cv_dest = cv_dir / Path(cv_url).name
                if cv_dest.exists():
                    status["wan_clip_vision"] = "already"
                elif download_model_file(cv_urls, cv_dest):
                    status["wan_clip_vision"] = "ok"
                else:
                    status["wan_clip_vision"] = "blocked-download"
    return status


def install_wav2lip(runtime_dir: Path, py: Path) -> bool:
    dest = runtime_dir / "wav2lip"
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / "inference.py").exists():
        git = shutil.which("git")
        if not git:
            print("git is required to install Wav2Lip")
            return False
        print("cloning Wav2Lip ...")
        result = subprocess.run([git, "clone", "--depth", "1", WAV2LIP_URL, str(dest)], capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print(result.stderr[-1200:])
            return False
    if not patch_wav2lip_compat(dest):
        return False
    print("installing Wav2Lip python dependencies ...")
    deps = ["numpy", "scipy", "librosa", "opencv-python-headless", "tqdm", "numba"]
    result = subprocess.run([str(py), "-m", "pip", "install", *deps], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-1200:])
        return False
    checkpoint_dir = dest / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    wav2lip_path = checkpoint_dir / "wav2lip.pth"
    if not wav2lip_path.exists():
        print("downloading Wav2Lip checkpoint ...")
        if not download_model_file(MODEL_URLS.get("wav2lip", []), wav2lip_path):
            return False
    sfd_dir = dest / "face_detection" / "detection" / "sfd"
    sfd_dir.mkdir(parents=True, exist_ok=True)
    sfd_path = sfd_dir / "s3fd.pth"
    if not sfd_path.exists():
        print("downloading Wav2Lip face-detection model ...")
        if not download_model_file(MODEL_URLS.get("wav2lip_s3fd", []), sfd_path):
            return False
    return True


def patch_wav2lip_compat(dest: Path) -> bool:
    """Patch Wav2Lip for modern librosa/scipy and OpenCV 5 video writing."""
    audio_py = dest / "audio.py"
    if not audio_py.exists():
        return False
    text = audio_py.read_text(encoding="utf-8", errors="replace")
    replacements = [
        ("librosa.core.load", "librosa.load"),
        (
            "return librosa.filters.mel(hp.sample_rate, hp.n_fft, n_mels=hp.num_mels,",
            "return librosa.filters.mel(sr=hp.sample_rate, n_fft=hp.n_fft, n_mels=hp.num_mels,",
        ),
        (
            "def save_wavenet_wav(wav, path, sr):\n    librosa.output.write_wav(path, wav, sr=sr)",
            "def save_wavenet_wav(wav, path, sr):\n    wav *= 32767 / max(0.01, np.max(np.abs(wav)))\n    wavfile.write(path, sr, wav.astype(np.int16))",
        ),
    ]
    changed = False
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new)
            changed = True
    if changed:
        audio_py.write_text(text, encoding="utf-8")

    (dest / "temp").mkdir(parents=True, exist_ok=True)
    inference_py = dest / "inference.py"
    if inference_py.exists():
        itext = inference_py.read_text(encoding="utf-8", errors="replace")
        if "frame_index = 0" not in itext:
            lines = itext.splitlines(keepends=True)
            patched_lines: List[str] = []
            skip_writer_continuation = False
            for line in lines:
                stripped = line.strip()
                indent = line[: len(line) - len(line.lstrip())]
                if stripped.startswith("out = cv2.VideoWriter('temp/result.avi'"):
                    patched_lines.append(f"{indent}frame_index = 0\n")
                    patched_lines.append(f"{indent}frame_dir = os.path.dirname(args.outfile)\n")
                    skip_writer_continuation = True
                elif skip_writer_continuation and "cv2.VideoWriter_fourcc(*'DIVX')" in stripped:
                    skip_writer_continuation = False
                elif stripped == "out.write(f)":
                    patched_lines.append(
                        f"{indent}cv2.imwrite(os.path.join(frame_dir, 'frame_%06d.png' % frame_index), f)\n"
                        f"{indent}frame_index += 1\n"
                    )
                elif stripped == "out.release()":
                    patched_lines.append(f"{indent}pass\n")
                elif stripped.startswith("command = 'ffmpeg -y -i {} -i {}"):
                    patched_lines.append(
                        f"{indent}command = 'ffmpeg -y -framerate {{}} -i {{}} -i {{}} -strict -2 -q:v 1 {{}}'"
                        f".format(fps, os.path.join(frame_dir, 'frame_%06d.png'), args.audio, args.outfile)\n"
                    )
                else:
                    patched_lines.append(line)
            itext = "".join(patched_lines)
            inference_py.write_text(itext, encoding="utf-8")
    return True


def order_ltx_text_encoder_urls(urls: List[str]) -> List[str]:
    """Prefer the fp8-scaled T5 for <=12GB GPUs and fp16 otherwise."""
    hardware = detect_hardware_profile()
    vram = hardware.get("vram_gb")
    ranked = list(urls)
    if vram is not None and vram < 12:
        ranked.sort(key=lambda u: (
            "t5xxl_fp8_e4m3fn_scaled" not in u,
            "t5xxl_fp8" not in u,
            "t5xxl_fp16" not in u,
        ))
    else:
        ranked.sort(key=lambda u: (
            "t5xxl_fp16" not in u,
            "t5xxl_fp8_e4m3fn_scaled" not in u,
            "t5xxl_fp8" not in u,
        ))
    return ranked


def missing_video_components(models: Dict[str, List[str]], hardware: Optional[Dict[str, Any]] = None) -> List[str]:
    """Return the model groups this hardware still needs for the full local pipeline."""
    hardware = hardware or detect_hardware_profile()
    vram = hardware.get("vram_gb")
    missing: List[str] = []
    ltx_ok = bool(
        models.get("ltx")
        and any("t5xxl" in Path(p).name.lower() for p in models.get("text_encoder", []))
    )
    if not ltx_ok:
        missing.append("ltx")
    if vram is None or vram < 7.5:
        if not models.get("liveportrait"):
            missing.append("liveportrait")
        return missing
    wan_ok = bool(
        models.get("wan")
        and models.get("vae")
        and models.get("text_encoder")
        and models.get("clip_vision")
    )
    if not wan_ok:
        missing.append("wan")
    if not models.get("liveportrait"):
        missing.append("liveportrait")
    return missing


def start_comfyui(comfy_dir: Path) -> bool:
    if probe_comfyui():
        print("ComfyUI API already ready")
        return True
    py = comfy_python(comfy_dir)
    log = comfy_dir / "comfyui_video.log"
    kwargs: Dict[str, Any] = {"stdout": log.open("ab"), "stderr": log.open("ab")}
    if platform.system().lower() == "windows":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        [py, str(comfy_dir / "main.py"), "--port", "8188"],
        cwd=str(comfy_dir),
        **kwargs,
    )
    (comfy_dir / "comfyui_video.pid").write_text(str(proc.pid), encoding="utf-8")
    deadline = time.time() + 180
    while time.time() < deadline:
        if probe_comfyui():
            print("ComfyUI API ready")
            return True
        if proc.poll() is not None:
            print(f"ComfyUI exited early with code {proc.returncode}")
            return False
        time.sleep(2)
    print("ComfyUI did not become ready; check comfyui_video.log")
    return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Detect/install local video engines.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--auto", action="store_true", help="install missing software/models for the current hardware")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--nodes-only", action="store_true", help="install custom nodes without downloading models")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--models", nargs="+", action="append", choices=("wan", "hunyuan", "ltx", "liveportrait", "wav2lip"), default=None)
    parser.add_argument("--model-url", default=None)
    parser.add_argument("--runtime-dir", type=Path, default=None)
    parser.add_argument("--comfy-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    runtime_dir = args.runtime_dir or default_video_runtime_dir()
    comfy_dir = args.comfy_dir or find_comfyui_dir()
    api = "available" if probe_comfyui() else "unavailable"
    nodes = detect_custom_nodes(comfy_dir)
    models = scan_model_files(comfy_dir, runtime_dir)
    talking = detect_talking_head(comfy_dir)
    audio_sync = detect_audio_lip_sync(comfy_dir, runtime_dir)
    report: Dict[str, Any] = {
        "os": platform.platform(),
        "arch": platform.machine(),
        "runtime_dir": str(runtime_dir),
        "comfyui_dir": str(comfy_dir) if comfy_dir else None,
        "comfyui_api": api,
        "custom_nodes": nodes,
        "models": models,
        "talking_head": talking,
        "audio_lip_sync": audio_sync,
    }

    if args.check or args.dry_run:
        write_report(args.project_dir, report)
        print("video engine:", json.dumps(report, ensure_ascii=False))
        return 0

    if args.auto:
        if comfy_dir is None:
            print("ComfyUI not found; installing local ComfyUI first ...")
            installer = Path(__file__).resolve().parent / "install_image_engine.py"
            cmd = [sys.executable, str(installer), "--engine", "comfyui", "--auto-install"]
            if args.runtime_dir is not None:
                cmd += ["--runtime-dir", str(args.runtime_dir)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(result.stdout[-2000:])
                print(result.stderr[-2000:])
                report["auto"] = "blocked-comfyui-install"
                write_report(args.project_dir, report)
                return 1
            comfy_dir = find_comfyui_dir()
            if comfy_dir is None:
                report["auto"] = "blocked-comfyui-install"
                write_report(args.project_dir, report)
                return 1

        nodes = detect_custom_nodes(comfy_dir)
        models = scan_model_files(comfy_dir, runtime_dir)
        hardware = detect_hardware_profile()
        if not (tool_path("ffmpeg") and tool_path("ffprobe")):
            ffmpeg_installer = Path(__file__).resolve().parent / "install_ffmpeg_vapoursynth.py"
            result = subprocess.run(
                [sys.executable, str(ffmpeg_installer), str(args.project_dir), "--auto-install"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(result.stdout[-2000:])
                print(result.stderr[-2000:])
                report["auto"] = "blocked-ffmpeg-install"
                write_report(args.project_dir, report)
                return 1
        missing_models = missing_video_components(models, hardware)
        report["hardware"] = hardware
        report["models"] = models
        report["custom_nodes"] = nodes
        if not missing_models and any("videohelper" in name.lower() for name in nodes):
            report["auto"] = "already-ready"
            if args.start or not probe_comfyui():
                ok = start_comfyui(comfy_dir)
                report["started"] = ok
                if not ok:
                    write_report(args.project_dir, report)
                    return 1
            write_report(args.project_dir, report)
            print("video engine already ready for this hardware")
            return 0

        node_keys = ["video_helper"]
        if "wan" in missing_models:
            node_keys.append("wan")
        if "liveportrait" in missing_models:
            node_keys.append("liveportrait")
        for node in node_keys:
            node_name = CUSTOM_NODES[node].rstrip("/").split("/")[-1]
            if not clone_node(comfy_dir, node_name, CUSTOM_NODES[node]):
                report["auto"] = "blocked-node"
                write_report(args.project_dir, report)
                return 1

        if missing_models:
            model_status = install_models(runtime_dir, missing_models, None, comfy_dir)
            report["model_status"] = model_status
            if any(v.startswith("blocked") for v in model_status.values()):
                write_report(args.project_dir, report)
                print("one or more models blocked; see video_engine_report.md")
                return 1
        report["auto"] = "ok"
        if args.start or not probe_comfyui():
            ok = start_comfyui(comfy_dir)
            report["started"] = ok
            if not ok:
                write_report(args.project_dir, report)
                return 1
        write_report(args.project_dir, report)
        print("video engine auto install complete")
        return 0

    if args.start:
        if comfy_dir is None:
            print("ComfyUI directory not found")
            return 1
        ok = start_comfyui(comfy_dir)
        report["started"] = ok
        write_report(args.project_dir, report)
        return 0 if ok else 1

    if not args.install:
        print("use --check to inspect or --install to install missing components")
        return 1

    if comfy_dir is None:
        print("ComfyUI not found; install image engine first or pass --comfy-dir")
        return 1

    model_keys = [key for group in (args.models or []) for key in group] or ["wan"]
    for key in model_keys:
        if key == "wav2lip":
            continue
        node_keys = [key]
        if key in ("wan", "hunyuan"):
            node_keys = ["video_helper", key]
        elif key == "ltx":
            node_keys = ["video_helper"]
        for node in node_keys:
            if not clone_node(comfy_dir, CUSTOM_NODES[node].rstrip("/").split("/")[-1], CUSTOM_NODES[node]):
                report["install_status"] = "failed"
                write_report(args.project_dir, report)
                return 1

    if args.nodes_only:
        report["install_status"] = "nodes-ok"
        write_report(args.project_dir, report)
        print("custom nodes installed; models skipped")
        return 0

    model_status = install_models(runtime_dir, model_keys, args.model_url, comfy_dir)
    report["model_status"] = model_status
    if any(v.startswith("blocked") for v in model_status.values()):
        write_report(args.project_dir, report)
        print("one or more models blocked; see video_engine_report.md")
        return 1
    report["install_status"] = "ok"
    write_report(args.project_dir, report)
    print("video engine install complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
