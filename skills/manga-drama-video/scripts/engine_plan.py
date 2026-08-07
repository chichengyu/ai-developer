#!/usr/bin/env python3
"""Generate or refresh engine_plan.json for a manga-drama project.

Usage:
    python engine_plan.py <project_or_series_dir> [--check] [--require-motion]

Writes:
    <project_dir>/engine_plan.json  (or the detected series root)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path
from install_image_engine import probe_local_image_engines
from install_video_engine import (
    default_video_runtime_dir,
    detect_audio_lip_sync,
    detect_custom_nodes,
    detect_talking_head,
    find_comfyui_dir,
    scan_model_files,
)
from hardware_profile import detect_hardware_profile


def have_tool(name: str) -> bool:
    return tool_path(name) is not None


def find_series_root(candidate: Path) -> Optional[Path]:
    current = candidate
    while current != current.parent:
        if (current / "00_series.json").exists():
            return current
        current = current.parent
    return None


def detect_target(candidate: Path) -> Path:
    meta_path = candidate / "00_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
            if meta.get("is_series") is True:
                series = find_series_root(candidate)
                if series is not None:
                    return series
        except (json.JSONDecodeError, OSError):
            pass
    return candidate


def load_model_config(target: Path) -> Dict[str, Any]:
    path = target / "model_config.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        current = data.get("current", {}) if isinstance(data, dict) else {}
        provider = current.get("provider")
        model = current.get("model")
        if provider and model:
            return {
                "provider": str(provider),
                "model": str(model),
                "roles": [str(role) for role in current.get("roles", []) if isinstance(role, str)],
            }
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def build_engines(target: Path) -> Dict[str, Dict[str, Any]]:
    ffmpeg_ok = have_tool("ffmpeg") and have_tool("ffprobe")
    openai_ok = bool(os.environ.get("OPENAI_API_KEY"))
    local_image = probe_local_image_engines()
    comfy_dir = find_comfyui_dir()
    video_models = scan_model_files(comfy_dir, default_video_runtime_dir())
    video_family = next((key for key in ("wan", "hunyuan", "ltx") if video_models.get(key)), None)
    video_ready = bool(video_family)
    if video_family == "wan":
        video_ready = bool(
            video_models.get("vae")
            and video_models.get("text_encoder")
            and video_models.get("clip_vision")
        )
    elif video_family == "ltx":
        video_ready = bool(
            any("t5xxl" in Path(p).name.lower() for p in video_models.get("text_encoder", []))
        )
    hardware = detect_hardware_profile(
        wan_available=bool(video_models.get("wan")),
        ltx_available=bool(video_models.get("ltx")),
    )
    talking = detect_talking_head(comfy_dir)
    audio_sync = detect_audio_lip_sync(comfy_dir, default_video_runtime_dir())
    comfy_api_ok = "comfyui" in local_image
    model_cfg = load_model_config(target)
    provider = str(model_cfg.get("provider") or "").strip()
    model_name = str(model_cfg.get("model") or "").strip()
    provider_lc = provider.lower()
    model_lc = model_name.lower()
    roles = {str(role).strip().lower() for role in model_cfg.get("roles", []) if isinstance(role, str)}
    is_cloud_video = bool(
        provider_lc
        and (
            "video" in roles
            or "video_gen" in roles
            or "minimax" in provider_lc
            or "hailuo" in provider_lc
            or "seedance" in provider_lc
            or "seedance" in model_lc
            or "jimeng" in provider_lc
            or ("doubao" in provider_lc and ("seedance" in model_lc or "video" in model_lc))
        )
    )
    is_audio_driven_lip = bool(
        provider_lc
        and (
            "lip_sync" in roles
            or "minimax" in provider_lc
            or "seedance" in provider_lc
            or "seedance" in model_lc
        )
    )

    if openai_ok:
        image = {"name": "imagegen", "status": "available", "params": {"provider": "openai"}}
        tts = {"name": "openai-tts", "status": "available", "params": {"provider": "openai"}}
    elif "comfyui" in local_image:
        image = {
            "name": "comfyui",
            "status": "available",
            "params": {
                "endpoint": local_image["comfyui"]["endpoint"],
                "model": "RealVisXL_V4.0",
                "installer": "install_image_engine.py --auto-install",
                "generate": "generate_images.py",
            },
        }
        tts = {"name": "edge-tts", "status": "available", "params": {"provider": "edge"}}
    elif "sd-webui" in local_image:
        image = {
            "name": "sd-webui",
            "status": "available",
            "params": {
                "endpoint": local_image["sd-webui"]["endpoint"],
                "installer": "install_image_engine.py --auto-install",
            },
        }
        tts = {"name": "edge-tts", "status": "available", "params": {"provider": "edge"}}
    elif "diffusers" in local_image:
        image = {
            "name": "diffusers",
            "status": "available",
            "params": {
                **local_image["diffusers"],
                "installer": "install_image_engine.py --auto-install",
                "generate": "generate_images.py",
            },
        }
        tts = {"name": "edge-tts", "status": "available", "params": {"provider": "edge"}}
    else:
        image = {
            "name": "imagegen",
            "status": "assumed_mcp",
            "params": {
                "provider": "codex_mcp",
                "installer": "install_image_engine.py --auto-install",
                "generate": "generate_images.py",
                "manual_external_tools": "forbidden",
            },
        }
        if have_tool("edge-tts"):
            tts = {"name": "edge-tts", "status": "available", "params": {"provider": "edge"}}
        elif have_tool("espeak-ng") or have_tool("espeak"):
            tts = {"name": "espeak", "status": "available", "params": {"provider": "local"}}
        else:
            tts = {"name": "speech", "status": "assumed_mcp", "params": {"provider": "codex_mcp"}}

    if provider_lc and (
        "image" in roles
        or "imagegen" in roles
        or "seedream" in provider_lc
        or "seedream" in model_lc
    ):
        image = {
            "name": "current-model-image",
            "status": "configured",
            "params": {
                "provider": provider,
                "model": model_name,
                "generate": "current model/API image generation or editing",
                "verify": "confirm API key and endpoint before Step 1",
            },
        }

    digital_human = {"name": "still-portrait", "status": "available", "params": {"mode": "ken-burns"}}
    if any(have_tool(name) for name in ("sadtalker", "liveportrait", "hallo", "muse-talk")):
        digital_human = {"name": "local-face-animation", "status": "available", "params": {"mode": "auto"}}
    elif os.environ.get("HEYGEN_API_KEY") or os.environ.get("D_ID_API_KEY"):
        digital_human = {"name": "api-talking-head", "status": "available", "params": {"mode": "auto"}}

    if video_family and video_ready and comfy_api_ok:
        video_gen = {
            "name": f"comfyui-{video_family}",
            "status": "available",
            "params": {
                "model": video_family,
                "model_file": video_models[video_family][0],
                "model_dir": str(default_video_runtime_dir() / "video-models" / video_family),
                "custom_nodes": detect_custom_nodes(comfy_dir),
                "hardware_profile": hardware.get("profile"),
                "recommended": hardware.get("recommended"),
                "installer": "install_video_engine.py --auto",
                "generate": "generate_video.py",
            },
        }
    elif video_family or comfy_dir is not None:
        video_gen = {
            "name": "none",
            "status": "installed-not-running",
            "params": {
                "model_dir": str(default_video_runtime_dir() / "video-models"),
                "installer": "install_video_engine.py --auto",
            },
        }
    else:
        video_gen = {
            "name": "none",
            "status": "unavailable",
            "params": {"installer": "install_video_engine.py --auto"},
        }

    if is_cloud_video:
        video_gen = {
            "name": "current-model-api",
            "status": "configured",
            "params": {
                "provider": provider,
                "model": model_name,
                "endpoint": "verify from provider docs",
                "generate": "current model/API image-to-video",
                "verify": "confirm API key and endpoint before Step 1",
            },
        }

    if talking.get("available"):
        talking_head = {
            "name": talking["cli"][0] if talking["cli"] else "comfyui",
            "status": "available",
            "params": {
                "cli": talking["cli"],
                "comfyui_nodes": talking["comfyui_nodes"],
                "installer": "install_video_engine.py --install --models liveportrait",
            },
        }
    else:
        talking_head = {
            "name": "none",
            "status": "unavailable",
            "params": {
                "fallback": "voice-only",
                "installer": "install_video_engine.py --install --models liveportrait",
            },
        }

    if audio_sync.get("available"):
        audio_lip_sync = {
            "name": audio_sync["cli"][0] if audio_sync["cli"] else audio_sync["comfyui_nodes"][0],
            "status": "available",
            "params": {
                "cli": audio_sync["cli"],
                "comfyui_nodes": audio_sync["comfyui_nodes"],
                "mode": "audio-driven",
            },
        }
    else:
        audio_lip_sync = {
            "name": "none",
            "status": "unavailable",
            "params": {
                "mode": "voice-only",
                "message": audio_sync.get("message", "no audio-driven lip-sync engine found"),
                "installer": "install SadTalker/MuseTalk/Wav2Lip/Hallo or export a Wan 2.2 audio-to-video workflow",
            },
        }

    if is_audio_driven_lip:
        digital_human = {
            "name": "current-model-audio-to-video",
            "status": "configured",
            "params": {
                "provider": provider,
                "model": model_name,
                "mode": "audio-driven lip sync",
                "verify": "confirm API key and endpoint before Step 1",
            },
        }
        audio_lip_sync = {
            "name": "current-model-audio-to-video",
            "status": "configured",
            "params": {
                "provider": provider,
                "model": model_name,
                "mode": "audio-driven",
                "input": "audio_url + image_url/video_url",
                "note": "MiniMax-H3 supports WAV/MP3 2-15s paired with image/video; verify other providers separately",
            },
        }

    video_native = video_gen.get("status") in ("available", "configured", "user_specified")

    return {
        "hardware": {
            "name": hardware.get("profile", "unknown"),
            "status": "available",
            "params": {
                "gpu": hardware.get("gpu_name"),
                "vram_gb": hardware.get("vram_gb"),
                "ram_gb": hardware.get("ram_gb"),
                "recommended": hardware.get("recommended"),
            },
        },
        "image": image,
        "video_gen": video_gen,
        "talking_head": talking_head,
        "audio_lip_sync": audio_lip_sync,
        "video": {
            "name": "ffmpeg",
            "status": "available" if ffmpeg_ok else "unavailable",
            "params": {"encoder": "libx264", "audio": "aac"},
        },
        "audio_tts": tts,
        "digital_human": digital_human,
        "camera_motion": {
            "name": "video-native" if video_native else "ffmpeg-ken-burns",
            "status": "available" if ffmpeg_ok else "unavailable",
            "params": {
                "mode": "video-native" if video_native else "ffmpeg-ken-burns",
                "fallback": "static",
            },
        },
        "subtitles": {
            "name": "ffmpeg-subtitles",
            "status": "available" if ffmpeg_ok else "unavailable",
            "params": {"encoding": "utf-8-no-bom"},
        },
        "resource_reader": {
            "name": "codex-tools",
            "status": "available",
            "params": {"tools": ["browser", "open_page", "curl", "ffmpeg", "asr", "ocr"]},
        },
        "postprocess": {
            "name": "ffmpeg-vapoursynth",
            "status": "available" if (ffmpeg_ok or have_tool("vspipe")) else "unavailable",
            "params": {"profile": "balanced", "installer": "install_ffmpeg_vapoursynth.py --auto-install", "models": "setup_postprocess.py --install-models"},
        },
    }


def _detect_reference_bundle(target: Path) -> Dict[str, Any]:
    bundle_path = target / "reference_bundle.json"
    if not bundle_path.exists():
        return {"status": "pending", "images": 0, "videos": 0, "audio": 0}
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
        images = sum(1 for v in bundle.get("images", {}).values() if v)
        videos = sum(1 for v in bundle.get("videos", {}).values() if v)
        audio = sum(1 for v in bundle.get("audio", {}).values() if v)
        return {"status": "ok", "images": images, "videos": videos, "audio": audio}
    except (json.JSONDecodeError, OSError):
        return {"status": "blocked", "images": 0, "videos": 0, "audio": 0}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate engine_plan.json.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--check", action="store_true", help="exit non-zero if core engines are missing")
    parser.add_argument("--require-motion", action="store_true", help="also require a real-motion video engine")
    args = parser.parse_args(argv)

    target = detect_target(args.project_dir)
    target.mkdir(parents=True, exist_ok=True)
    plan_path = target / "engine_plan.json"

    existing: Dict[str, Any] = {}
    if plan_path.exists():
        try:
            existing = json.loads(plan_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    engines = build_engines(target)
    overrides = existing.get("user_overrides", {}) if isinstance(existing, dict) else {}
    if isinstance(overrides, dict):
        for engine_key, override in overrides.items():
            if engine_key in engines and isinstance(override, dict):
                name = override.get("name")
                if name:
                    engines[engine_key]["name"] = name
                    engines[engine_key]["status"] = "user_specified"

    plan = {
        "engine_plan_version": 1,
        "auto": not bool(overrides),
        "engines": engines,
        "cloud_model": load_model_config(target) or None,
        "reference_bundle": _detect_reference_bundle(target),
        "fallbacks": {
            "image": ["comfyui", "sd-webui", "imagegen", "install-local"],
            "video_gen": ["still-kenburns", "ffmpeg-ken-burns", "install-local"],
            "talking_head": ["voice-only", "install-local"],
            "audio_lip_sync": ["voice-only", "install-local"],
            "video": [],
            "audio_tts": ["speech", "openai-tts", "edge-tts"],
            "digital_human": ["liveportrait", "still-portrait"],
            "camera_motion": ["ffmpeg-ken-burns", "static"],
            "subtitles": [],
            "resource_reader": ["manual-user-input"],
            "postprocess": ["ffmpeg-only", "manual-user-input"],
        },
        "user_overrides": overrides,
        "notes": existing.get("notes", []) if isinstance(existing, dict) else [],
    }

    plan_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for key, engine in engines.items():
        print(f"{key}: {engine['name']} [{engine['status']}]")
    print(f"wrote: {plan_path}")

    if args.check:
        core = ["image", "video", "camera_motion", "subtitles"]
        if args.require_motion:
            core += ["video_gen"]
        allowed = {
            "image": ("available", "user_specified", "assumed_mcp", "configured"),
            "video_gen": ("available", "user_specified", "configured"),
        }
        missing = [
            key for key in core
            if engines.get(key, {}).get("status") not in allowed.get(key, ("available", "user_specified"))
        ]
        if missing:
            print(f"missing core engines: {', '.join(missing)}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
