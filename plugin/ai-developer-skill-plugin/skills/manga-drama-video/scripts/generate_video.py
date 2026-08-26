#!/usr/bin/env python3
"""Generate real-motion shot clips with a local ComfyUI video engine.

Usage:
    python generate_video.py --prompt "<motion_text>" --image keyframe.png \
        --output 05_video/SH1.1.mp4 --seed 101 --model wan \
        --width 480 --height 832 --frames 49 --fps 24

The script prefers a project workflow file exported from ComfyUI:
    outputs/<project>/video_workflow.json
Placeholders inside the workflow JSON are replaced at runtime:
    {prompt} {negative} {seed} {image} {width} {height} {frames} {fps} {steps}
When no workflow file exists, built-in Wan / LTX templates are attempted and
the exact API failure is reported so the user can export a compatible workflow.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
import uuid
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path
from install_image_engine import probe_comfyui
from install_video_engine import find_comfyui_dir
from hardware_profile import detect_hardware_profile, recommend


COMFY_URL = "http://127.0.0.1:8188"
DEFAULT_NEGATIVE = "lowres, bad anatomy, bad hands, extra fingers, blurry, plastic skin, text, watermark, jitter, flicker, morphing, foot sliding, floating"


def http_json(url: str, payload: Optional[bytes] = None, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"} if payload else {"User-Agent": "manga-drama-video/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:
        print(f"ComfyUI request failed: {exc}")
        return None


def available_node_classes(comfy_url: str) -> Dict[str, Any]:
    info = http_json(comfy_url.rstrip("/") + "/object_info")
    return info if isinstance(info, dict) else {}


def find_model_file(comfy_url: str, family: str) -> Optional[str]:
    comfy_dir = find_comfyui_dir()
    bases = [comfy_dir] if comfy_dir else []
    bases.append(Path("E:/soft/manga-drama-image"))
    roots: list[Path] = []
    for base in bases:
        if base is not None:
            roots.extend([
                base / "models" / "diffusion_models",
                base / "models" / "checkpoints",
                base / "models" / "unet",
            ])
    for root in roots:
        if root.is_dir():
            for path in sorted(root.glob("*.safetensors")):
                if list(root.glob(path.name + ".part*")):
                    continue
                if path.stat().st_size < 1024 * 1024 * 1024:
                    continue
                name = path.name.lower()
                if family == "wan" and "wan" in name:
                    return path.name
                if family == "ltx" and "ltx" in name:
                    return path.name
                if family == "hunyuan" and ("hunyuan" in name or "hyvideo" in name):
                    return path.name
    return None


def find_text_encoder_file(prefix: str = "t5xxl") -> Optional[str]:
    comfy_dir = find_comfyui_dir()
    bases = [comfy_dir] if comfy_dir else []
    bases.append(Path("E:/soft/manga-drama-image"))
    for base in bases:
        if base is None:
            continue
        folder = base / "models" / "text_encoders"
        if folder.is_dir():
            files = sorted(folder.glob("*.safetensors"))
            for path in files:
                if list(folder.glob(path.name + ".part*")):
                    continue
                if path.stat().st_size > 1024 * 1024 * 1024 and path.name.lower().startswith(prefix.lower()):
                    return path.name
    return None


def load_workflow_template(project_dir: Optional[Path], comfy_url: str, family: str, model_file: Optional[str]) -> Dict[str, Any]:
    if project_dir is not None:
        custom = project_dir / "video_workflow.json"
        if custom.exists():
            return json.loads(custom.read_text(encoding="utf-8"))
    if family == "wan":
        return {
            "1": {
                "class_type": "WanVideoModelLoader",
                "inputs": {
                    "model": model_file or "Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors",
                    "base_precision": "fp16",
                    "quantization": "fp8_e4m3fn",
                    "load_device": "offload_device",
                    "attention_mode": "sdpa",
                },
            },
            "2": {
                "class_type": "WanVideoVAELoader",
                "inputs": {
                    "model_name": "Wan2_1_VAE_bf16.safetensors",
                    "precision": "fp16",
                },
            },
            "3": {
                "class_type": "WanVideoTextEncodeCached",
                "inputs": {
                    "model_name": "umt5-xxl-enc-fp8_e4m3fn.safetensors",
                    "precision": "bf16",
                    "positive_prompt": "{prompt}",
                    "negative_prompt": "{negative}",
                    "quantization": "fp8_e4m3fn",
                    "use_disk_cache": True,
                    "device": "cpu",
                },
            },
            "4": {"class_type": "LoadImage", "inputs": {"image": "keyframe.png"}},
            "5": {
                "class_type": "WanVideoImageToVideoEncode",
                "inputs": {
                    "width": "{width}",
                    "height": "{height}",
                    "num_frames": "{frames}",
                    "noise_aug_strength": 0.0,
                    "start_latent_strength": 1.0,
                    "end_latent_strength": 1.0,
                    "force_offload": True,
                    "vae": ["2", 0],
                    "start_image": ["4", 0],
                    "end_image": None,
                    "fun_or_fl2v_model": False,
                    "tiled_vae": True,
                },
            },
            "6": {
                "class_type": "WanVideoSampler",
                "inputs": {
                    "model": ["10", 0],
                    "image_embeds": ["5", 0],
                    "text_embeds": ["3", 0],
                    "steps": "{steps}",
                    "cfg": 5.0,
                    "shift": 5.0,
                    "seed": "{seed}",
                    "force_offload": True,
                    "scheduler": "unipc",
                    "riflex_freq_index": 0,
                },
            },
            "7": {
                "class_type": "WanVideoDecode",
                "inputs": {
                    "vae": ["2", 0],
                    "samples": ["6", 0],
                    "enable_vae_tiling": True,
                    "tile_x": 272,
                    "tile_y": 272,
                    "tile_stride_x": 144,
                    "tile_stride_y": 128,
                    "normalization": "default",
                },
            },
            "8": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["7", 0],
                    "frame_rate": "{fps}",
                    "loop_count": 0,
                    "filename_prefix": "manga_video",
                    "format": "video/h264-mp4",
                    "pingpong": False,
                    "save_output": True,
                },
            },
            "9": {
                "class_type": "WanVideoBlockSwap",
                "inputs": {
                    "blocks_to_swap": "{block_swap}",
                    "offload_img_emb": True,
                    "offload_txt_emb": True,
                    "use_non_blocking": False,
                    "vace_blocks_to_swap": 0,
                    "prefetch_blocks": 0,
                    "block_swap_debug": False,
                },
            },
            "10": {
                "class_type": "WanVideoSetBlockSwap",
                "inputs": {
                    "model": ["1", 0],
                    "block_swap_args": ["9", 0],
                },
            },
        }
    if family == "ltx":
        text_encoder = find_text_encoder_file() or "t5xxl_fp8_e4m3fn_scaled.safetensors"
        hw = detect_hardware_profile()
        text_device = "default" if (hw.get("vram_gb") or 0) >= 12 else "cpu"
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": model_file or "ltx-video-2b-v0.9.5.safetensors",
                },
            },
            "2": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": text_encoder,
                    "type": "ltxv",
                    "device": text_device,
                },
            },
            "3": {"class_type": "LoadImage", "inputs": {"image": "keyframe.png"}},
            "4": {"class_type": "LTXVPreprocess", "inputs": {"image": ["3", 0], "img_compression": 40}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "{prompt}", "clip": ["2", 0]}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{negative}", "clip": ["2", 0]}},
            "7": {
                "class_type": "LTXVImgToVideo",
                "inputs": {
                    "positive": ["5", 0],
                    "negative": ["6", 0],
                    "vae": ["1", 2],
                    "image": ["4", 0],
                    "width": "{width}",
                    "height": "{height}",
                    "length": "{frames}",
                    "batch_size": 1,
                    "strength": 1.0,
                },
            },
            "8": {
                "class_type": "LTXVConditioning",
                "inputs": {
                    "positive": ["7", 0],
                    "negative": ["7", 1],
                    "frame_rate": "{fps}",
                },
            },
            "9": {
                "class_type": "LTXVScheduler",
                "inputs": {
                    "steps": "{steps}",
                    "max_shift": 2.05,
                    "base_shift": 0.95,
                    "stretch": True,
                    "terminal": 0.1,
                    "latent": ["7", 2],
                },
            },
            "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
            "11": {
                "class_type": "SamplerCustom",
                "inputs": {
                    "model": ["1", 0],
                    "add_noise": True,
                    "noise_seed": "{seed}",
                    "cfg": 3.0,
                    "positive": ["8", 0],
                    "negative": ["8", 1],
                    "sampler": ["10", 0],
                    "sigmas": ["9", 0],
                    "latent_image": ["7", 2],
                },
            },
            "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["1", 2]}},
            "13": {
                "class_type": "VHS_VideoCombine",
                "inputs": {
                    "images": ["12", 0],
                    "frame_rate": "{fps}",
                    "loop_count": 0,
                    "filename_prefix": "manga_video",
                    "format": "video/h264-mp4",
                    "pingpong": False,
                    "save_output": True,
                },
            },
        }
    raise SystemExit(
        "no built-in workflow for this model family; export a workflow from ComfyUI "
        "and save it as outputs/<project>/video_workflow.json with the placeholders listed in the docstring"
    )


def render_workflow(
    workflow: Dict[str, Any],
    values: Dict[str, Any],
    image_name: str,
    model_file: Optional[str],
    comfy_url: str = "",
    image_aliases: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, Any]:
    rendered = json.loads(json.dumps(workflow))

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            try:
                return node.format(**values)
            except (KeyError, ValueError, IndexError):
                return node
        return node

    rendered = walk(rendered)
    schema_info = available_node_classes(comfy_url) if comfy_url else {}
    for node in rendered.values():
        inputs = node.get("inputs", {})
        if isinstance(inputs, dict):
            if node.get("class_type") == "LoadImage" and inputs.get("image") == "keyframe.png" and image_name:
                inputs["image"] = image_name
            for key in ("ckpt_name", "model", "unet_name"):
                if isinstance(inputs.get(key), str) and model_file:
                    inputs[key] = model_file
            schema = schema_info.get(node.get("class_type", ""), {})
            input_schema: Dict[str, Any] = {}
            for group in ("required", "optional"):
                input_schema.update(schema.get("input", {}).get(group, {}))
            for key, value in list(inputs.items()):
                if not isinstance(value, str):
                    continue
                field_type = input_schema.get(key, [None])[0]
                try:
                    if field_type == "INT":
                        inputs[key] = int(value)
                    elif field_type == "FLOAT":
                        inputs[key] = float(value)
                    elif field_type == "BOOLEAN":
                        inputs[key] = str(value).lower() in ("1", "true", "yes")
                except ValueError:
                    pass
    if image_aliases:
        next_id = max((int(k) for k in rendered if str(k).isdigit()), default=0) + 1
        additions: Dict[str, Dict[str, Any]] = {}
        for node in rendered.values():
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            for key, alias in image_aliases.items():
                if not alias:
                    continue
                if isinstance(inputs.get(key), str) and inputs[key] == alias:
                    load_id = str(next_id)
                    next_id += 1
                    additions[load_id] = {"class_type": "LoadImage", "inputs": {"image": alias}}
                    inputs[key] = [load_id, 0]
        rendered.update(additions)
    return rendered


def attach_optional_image_nodes(
    workflow: Dict[str, Any],
    start_image_name: Optional[str],
    end_image_name: Optional[str],
    override_start: bool = False,
) -> None:
    """Wire start/end frame LoadImage nodes into the I2V encoder."""
    next_id = max((int(k) for k in workflow if str(k).isdigit()), default=0) + 1
    additions: Dict[str, Dict[str, Any]] = {}
    for node in workflow.values():
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        if node.get("class_type") != "WanVideoImageToVideoEncode":
            continue
        if start_image_name and (override_start or inputs.get("start_image") is None):
            load_id = str(next_id)
            next_id += 1
            additions[load_id] = {"class_type": "LoadImage", "inputs": {"image": start_image_name}}
            inputs["start_image"] = [load_id, 0]
        if end_image_name and inputs.get("end_image") is None:
            load_id = str(next_id)
            next_id += 1
            additions[load_id] = {"class_type": "LoadImage", "inputs": {"image": end_image_name}}
            inputs["end_image"] = [load_id, 0]
    workflow.update(additions)
    return None


REFERENCE_PREFERENCE = [
    "character_front",
    "character_three_quarter",
    "composition_reference",
    "scene_wide",
    "style_reference",
    "character_expression",
    "character_action",
    "scene_detail",
    "character_side",
]


def upload_reference_images(bundle: Dict[str, Any], base_dir: Path, comfy_url: str, limit: int = 2) -> list[str]:
    names: list[str] = []
    for slot in REFERENCE_PREFERENCE:
        value = bundle.get("images", {}).get(slot)
        if not value:
            continue
        path = base_dir / value
        if path.exists():
            name = upload_to_comfyui(comfy_url, path, "ref")
            if name:
                names.append(name)
        if len(names) >= limit:
            break
    return names


def build_reference_grid_pillow(paths: list[Path], dest: Path, target_size: tuple[int, int] = (512, 256)) -> Optional[Path]:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    count = len(paths)
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    cell_w = target_size[0] // cols
    cell_h = target_size[1] // rows
    canvas = Image.new("RGB", target_size, (12, 12, 16))
    for idx, path in enumerate(paths):
        try:
            img = Image.open(path).convert("RGB")
            img = ImageOps.fit(img, (cell_w, cell_h), Image.LANCZOS)
            row, col = divmod(idx, cols)
            canvas.paste(img, (col * cell_w, row * cell_h))
        except Exception as exc:
            print(f"reference grid skipped {path.name}: {exc}")
    canvas.save(dest, "PNG")
    return dest if dest.exists() else None


def build_reference_grid_ffmpeg(paths: list[Path], dest: Path, target_size: tuple[int, int] = (512, 256)) -> Optional[Path]:
    exe = tool_path("ffmpeg")
    if not exe:
        return None
    count = len(paths)
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    cell_w = target_size[0] // cols
    cell_h = target_size[1] // rows
    inputs: list[str] = []
    filters: list[str] = []
    vidx = 0
    row_labels: list[str] = []
    for row_idx in range(rows):
        row_paths = paths[row_idx * cols:(row_idx + 1) * cols]
        start = vidx
        for path in row_paths:
            inputs += ["-i", str(path)]
            filters.append(f"[{vidx}:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=increase,crop={cell_w}:{cell_h},setsar=1[v{vidx}]")
            vidx += 1
        end = vidx
        if len(row_paths) == 1:
            filters.append(f"[v{start}]null[row{row_idx}]")
        else:
            row_input = "".join(f"[v{i}]" for i in range(start, end))
            filters.append(f"{row_input}hstack=inputs={len(row_paths)}[row{row_idx}]")
        row_labels.append(f"[row{row_idx}]")
    if rows == 1:
        filters.append(f"[row0]null[grid]")
    else:
        filters.append(f"{''.join(row_labels)}vstack=inputs={rows}[grid]")
    cmd = [exe, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[grid]", "-frames:v", "1", "-update", "1", str(dest)]
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return dest if dest.exists() else None


def normalize_reference_image_ffmpeg(path: Path, dest: Path, target_size: tuple[int, int]) -> Optional[Path]:
    exe = tool_path("ffmpeg")
    if not exe:
        return None
    cmd = [
        exe, "-y", "-loglevel", "error", "-i", str(path), "-vf",
        f"scale={target_size[0]}:{target_size[1]}:force_original_aspect_ratio=decrease,"
        f"pad={target_size[0]}:{target_size[1]}:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
        "-frames:v", "1", "-update", "1", str(dest),
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return dest if dest.exists() else None


def build_reference_grid(paths: list[Path], dest: Path, target_size: tuple[int, int] = (512, 256)) -> Optional[Path]:
    if not paths:
        return None
    if len(paths) == 1:
        normalized = normalize_reference_image_ffmpeg(paths[0], dest, target_size)
        if normalized is not None:
            print(f"reference grid (normalized single): {normalized}")
            return normalized
        return paths[0]
    grid = build_reference_grid_pillow(paths, dest, target_size)
    if grid is not None:
        print(f"reference grid: {grid} ({len(paths)} sources)")
        return grid
    grid = build_reference_grid_ffmpeg(paths, dest, target_size)
    if grid is not None:
        print(f"reference grid (ffmpeg): {grid} ({len(paths)} sources)")
        return grid
    print("reference grid build failed; using first reference only")
    return paths[0]


def collect_reference_images(bundle: Dict[str, Any], base_dir: Path, work_dir: Path, exe: Optional[str]) -> list[Path]:
    paths: list[Path] = []
    for slot in REFERENCE_PREFERENCE:
        value = bundle.get("images", {}).get(slot)
        if not value:
            continue
        path = base_dir / value
        if path.exists():
            paths.append(path)
    for slot in ("motion_primary", "action_beat", "camera_move"):
        value = bundle.get("videos", {}).get(slot)
        if not value:
            continue
        video = base_dir / value
        if not video.exists():
            continue
        frame = work_dir / f"{slot}_first.png"
        if not frame.exists() and exe:
            subprocess.run(
                [exe, "-y", "-loglevel", "error", "-i", str(video), "-frames:v", "1", str(frame)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        if frame.exists():
            paths.append(frame)
    return paths


def find_clip_vision_file() -> Optional[str]:
    comfy_dir = find_comfyui_dir()
    bases = [comfy_dir] if comfy_dir else []
    bases.append(Path("E:/soft/manga-drama-image"))
    for base in bases:
        if base is None:
            continue
        folder = base / "models" / "clip_vision"
        if folder.is_dir():
            files = sorted(folder.glob("*.safetensors"))
            if files and files[0].stat().st_size > 1024 * 1024 and not list(folder.glob(files[0].name + ".part*")):
                return files[0].name
    return None


def add_clip_reference_nodes(workflow: Dict[str, Any], ref_names: list[str], clip_model_name: str) -> None:
    if not ref_names:
        return
    next_id = max((int(k) for k in workflow if str(k).isdigit()), default=0) + 1
    load_ids: list[str] = []
    for name in ref_names[:2]:
        load_id = str(next_id)
        next_id += 1
        workflow[load_id] = {"class_type": "LoadImage", "inputs": {"image": name}}
        load_ids.append(load_id)
    loader_id = str(next_id)
    next_id += 1
    workflow[loader_id] = {
        "class_type": "LoadWanVideoClipTextEncoder",
        "inputs": {
            "model_name": clip_model_name,
            "precision": "fp16",
            "load_device": "offload_device",
        },
    }
    encode_id = str(next_id)
    next_id += 1
    encode_inputs: Dict[str, Any] = {
        "clip_vision": [loader_id, 0],
        "image_1": [load_ids[0], 0],
        "strength_1": 0.8,
        "strength_2": 0.8,
        "crop": "center",
        "combine_embeds": "average",
        "force_offload": True,
    }
    if len(load_ids) > 1:
        encode_inputs["image_2"] = [load_ids[1], 0]
    workflow[encode_id] = {"class_type": "WanVideoClipVisionEncode", "inputs": encode_inputs}
    for node in workflow.values():
        inputs = node.get("inputs", {})
        if isinstance(inputs, dict) and node.get("class_type") == "WanVideoImageToVideoEncode":
            inputs["clip_embeds"] = [encode_id, 0]
    return None


def validate_workflow(workflow: Dict[str, Any], comfy_url: str) -> bool:
    info = available_node_classes(comfy_url)
    if not info:
        print("could not read ComfyUI node schemas; skipping validation")
        return True
    errors: list[str] = []
    for node_id, node in workflow.items():
        class_type = node.get("class_type")
        schema = info.get(class_type)
        if schema is None:
            errors.append(f"node {node_id}: unknown class {class_type}")
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        required = schema.get("input", {}).get("required", {})
        optional = schema.get("input", {}).get("optional", {})
        for key in required:
            if key not in inputs:
                errors.append(f"node {node_id} {class_type}: missing required input {key}")
        for key in inputs:
            if key not in required and key not in optional:
                errors.append(f"node {node_id} {class_type}: unknown input {key}")
    if errors:
        print("workflow validation failed:")
        for error in errors[:60]:
            print("  " + error)
        return False
    print("workflow validation ok")
    return True


def sanitize_input_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return base or "frame"


def upload_to_comfyui(comfy_url: str, path: Optional[Path], prefix: str) -> Optional[str]:
    if path is None or not path.exists():
        return None
    boundary = "----manga" + uuid.uuid4().hex
    filename = f"{prefix}_{sanitize_input_name(path.name)}"
    payload = path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="image"; filename="' + filename + '"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + payload + (
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
    except Exception as exc:
        print(f"image upload failed: {exc}")
        return None
    return result.get("name") or filename


def output_node_id(workflow: Dict[str, Any]) -> str:
    for node_id, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") in ("VHS_VideoCombine", "SaveVideo", "SaveAnimatedWEBP"):
            return str(node_id)
    return "8"


def submit_and_poll(comfy_url: str, workflow: Dict[str, Any], output: Path, timeout: int = 7200) -> bool:
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    info = http_json(comfy_url.rstrip("/") + "/prompt", payload)
    if not info:
        return False
    prompt_id = info.get("prompt_id")
    if not prompt_id:
        print(f"ComfyUI returned no prompt_id: {info}")
        return False
    node_id = output_node_id(workflow)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        history = http_json(comfy_url.rstrip("/") + "/history/" + prompt_id)
        if not history or prompt_id not in history:
            continue
        entry = history[prompt_id]
        if entry.get("status", {}).get("status_str") == "error":
            print("ComfyUI execution error:")
            print(json.dumps(entry.get("status", {}), ensure_ascii=False, indent=2)[:3000])
            return False
        outputs = entry.get("outputs", {}).get(node_id, {})
        videos = outputs.get("gifs") or outputs.get("videos") or outputs.get("images")
        if not videos:
            continue
        item = videos[0]
        file_url = (
            comfy_url.rstrip("/") + "/view?filename=" + item.get("filename", "")
            + "&subfolder=" + item.get("subfolder", "")
            + "&type=" + item.get("type", "output")
        )
        try:
            urllib.request.urlretrieve(file_url, str(output))
        except Exception as exc:
            print(f"download clip failed: {exc}")
            return False
        return output.exists() and output.stat().st_size > 0
    print("timed out waiting for ComfyUI video output")
    return False


def pad_video_to_frames(output: Path, target_frames: int, fps: int) -> None:
    if target_frames <= 0:
        return
    ffprobe = tool_path("ffprobe")
    ffmpeg = tool_path("ffmpeg")
    if not ffprobe or not ffmpeg:
        return
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=nb_frames,duration", "-of", "json", str(output)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        stream = json.loads(result.stdout)["streams"][0]
        actual = int(stream.get("nb_frames") or round(float(stream.get("duration", 0)) * fps))
    except Exception:
        return
    if actual >= target_frames:
        return
    stop_duration = max(0.0, (target_frames - actual) / fps)
    temp = output.with_suffix(".pad.mp4")
    cmd = [
        ffmpeg, "-y", "-loglevel", "error", "-i", str(output),
        "-vf", f"tpad=stop_mode=clone:stop_duration={stop_duration:.4f}",
        "-r", str(fps), "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "copy", str(temp),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and temp.exists():
            temp.replace(output)
            print(f"padded video from {actual} to {target_frames} frames")
    except Exception as exc:
        print(f"pad video failed: {exc}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate real-motion clips.")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default=DEFAULT_NEGATIVE)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--model", choices=("auto", "wan", "hunyuan", "ltx"), default="auto")
    parser.add_argument("--profile", choices=("auto", "wan-low", "wan-8gb", "wan-12gb", "wan-high"), default="auto")
    parser.add_argument("--model-file", default=None)
    parser.add_argument("--project-dir", type=Path, default=None)
    parser.add_argument("--start-image", type=Path, default=None, help="previous shot last frame for long-shot chaining")
    parser.add_argument("--end-image", type=Path, default=None, help="next shot first frame target")
    parser.add_argument("--ref-bundle", type=Path, default=None, help="reference_bundle.json path")
    parser.add_argument("--comfy-url", default=COMFY_URL)
    parser.add_argument("--timeout", type=int, default=7200, help="seconds to wait for ComfyUI output (default 7200)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.dry_run and not probe_comfyui():
        print("ComfyUI API is not reachable at http://127.0.0.1:8188")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    keyframe_name = upload_to_comfyui(args.comfy_url, args.image, "key")
    start_name = None
    override_start = False
    if args.start_image:
        if args.image and args.start_image.resolve() == args.image.resolve():
            start_name = keyframe_name
        else:
            start_name = upload_to_comfyui(args.comfy_url, args.start_image, "start")
            override_start = True
    end_name = upload_to_comfyui(args.comfy_url, args.end_image, "end")
    wan_model = find_model_file(args.comfy_url, "wan")
    ltx_model = find_model_file(args.comfy_url, "ltx")
    hunyuan_model = find_model_file(args.comfy_url, "hunyuan")
    hardware = detect_hardware_profile(wan_available=bool(wan_model), ltx_available=bool(ltx_model))
    rec = hardware["recommended"]
    if args.profile != "auto":
        rec = recommend(args.profile, bool(wan_model), bool(ltx_model), hardware.get("ram_gb"))
    model_choice = args.model
    if model_choice == "auto":
        model_choice = rec.get("model", "wan")
        if model_choice == "ltx" and not ltx_model:
            model_choice = "wan" if wan_model else "ltx"
        elif model_choice == "wan" and not wan_model:
            model_choice = "ltx" if ltx_model else "wan"
    args.model = model_choice
    args.width = args.width if args.width is not None else rec.get("width", 480)
    args.height = args.height if args.height is not None else rec.get("height", 832)
    args.frames = args.frames if args.frames is not None else rec.get("frames", 25)
    args.steps = args.steps if args.steps is not None else rec.get("steps", 12)
    model_file = args.model_file or (wan_model if args.model == "wan" else ltx_model if args.model == "ltx" else hunyuan_model)
    if not model_file and not args.dry_run:
        print(f"no complete {args.model} model found; run scripts/install_video_engine.py <project> --auto first")
        return 1
    print(
        f"hardware profile: {hardware.get('profile')} | model={args.model} "
        f"{args.width}x{args.height} frames={args.frames} steps={args.steps} "
        f"block_swap={rec.get('block_swap')}"
    )
    try:
        workflow = load_workflow_template(args.project_dir, args.comfy_url, args.model, model_file)
    except SystemExit as exc:
        print(str(exc))
        return 2

    values = {
        "prompt": args.prompt,
        "negative": args.negative,
        "seed": args.seed,
        "width": args.width,
        "height": args.height,
        "frames": args.frames,
        "fps": args.fps,
        "steps": args.steps,
        "block_swap": rec.get("block_swap", 20),
        "start_image": start_name or "start_frame.png",
        "end_image": end_name or "end_frame.png",
    }
    bundle_path = args.ref_bundle or (
        (args.project_dir / "reference_bundle.json") if args.project_dir else None
    )
    bundle: Dict[str, Any] = {}
    if bundle_path and bundle_path.exists():
        try:
            bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
            for group, prefix in (("images", "ref_image"), ("videos", "ref_video"), ("audio", "ref_audio")):
                for idx, value in enumerate(bundle.get(group, {}).values(), start=1):
                    if value:
                        values[f"{prefix}_{idx}"] = str(Path(bundle_path).parent / value)
        except json.JSONDecodeError as exc:
            print(f"reference bundle is not valid JSON: {exc}")
    base_dir = bundle_path.parent if bundle_path else Path(".")
    ref_work = args.output.parent / ".ref_grid"
    ref_work.mkdir(parents=True, exist_ok=True)
    ref_paths = collect_reference_images(bundle, base_dir, ref_work, tool_path("ffmpeg"))
    grid_target = (args.width or 480, args.height or 832)
    grid_path = build_reference_grid(ref_paths, ref_work / "reference_grid.png", grid_target)
    ref_names: list[str] = []
    if grid_path is not None:
        name = upload_to_comfyui(args.comfy_url, grid_path, "refgrid")
        if name:
            ref_names.append(name)
    composition_value = bundle.get("images", {}).get("composition_reference")
    composition_path = base_dir / composition_value if composition_value else None
    if composition_path is not None and composition_path.exists():
        same_as_grid = grid_path is not None and composition_path.resolve() == grid_path.resolve()
        if same_as_grid:
            composition_path = None
        else:
            normalized_composition = None
            if grid_path is not None:
                normalized_composition = normalize_reference_image_ffmpeg(
                    composition_path, ref_work / "composition_reference.png", grid_target
                )
            upload_path = normalized_composition or composition_path
            name = upload_to_comfyui(args.comfy_url, upload_path, "comp")
            if name and name not in ref_names:
                ref_names.append(name)
    if not ref_names and composition_path is not None and composition_path.exists():
        name = upload_to_comfyui(args.comfy_url, composition_path, "ref")
        if name:
            ref_names.append(name)
    rendered = render_workflow(
        workflow,
        values,
        keyframe_name or "keyframe.png",
        model_file,
        args.comfy_url,
        {"start_image": start_name, "end_image": end_name},
    )
    attach_optional_image_nodes(rendered, start_name, end_name, override_start)
    clip_model = find_clip_vision_file()
    if args.model == "wan" and ref_names and clip_model:
        add_clip_reference_nodes(rendered, ref_names, clip_model)
    elif args.model == "wan" and ref_names:
        print("CLIP vision model not found; reference images were skipped")
    if args.model != "wan" and ref_paths:
        print("LTX built-in workflow has no reference-conditioning node; pass --workflow with {ref_image_N} / {reference_grid} to use the reference bundle")

    if args.dry_run:
        valid = validate_workflow(rendered, args.comfy_url)
        print(json.dumps(rendered, ensure_ascii=False, indent=2))
        return 0 if valid else 1

    if not validate_workflow(rendered, args.comfy_url):
        return 1

    ok = submit_and_poll(args.comfy_url, rendered, args.output, args.timeout)
    if ok:
        pad_video_to_frames(args.output, args.frames, args.fps)
        meta = {
            "prompt": args.prompt,
            "negative_prompt": args.negative,
            "seed": args.seed,
            "width": args.width,
            "height": args.height,
            "frames": args.frames,
            "fps": args.fps,
            "steps": args.steps,
            "model": args.model,
            "profile": args.profile,
            "hardware_profile": hardware.get("profile"),
            "model_file": model_file,
            "keyframe": str(args.image) if args.image else None,
            "start_image": str(args.start_image) if args.start_image else None,
            "end_image": str(args.end_image) if args.end_image else None,
            "reference_bundle": str(bundle_path) if bundle_path and bundle_path.exists() else None,
            "reference_grid": str(grid_path) if grid_path is not None else None,
            "reference_count": len(ref_paths),
        }
        (args.output.with_suffix(".json")).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"generated: {args.output}")
        return 0
    print("video generation failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
