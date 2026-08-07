#!/usr/bin/env python3
"""Generate realistic manga-drama images with the installed local engine.

Uses the diffusers runtime + RealVisXL checkpoint installed by
install_image_engine.py. Falls back to ComfyUI API when available.

Usage:
    python generate_images.py --prompt "..." --output out.png --seed 1101
      [--width 832 --height 1216 --steps 24 --negative "..."]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_image_engine import (
    MODEL_NAME,
    default_runtime_dir,
    probe_comfyui,
    probe_sd_webui,
    venv_python,
)
from generate_video import build_reference_grid, upload_to_comfyui


def load_report(base: Path) -> Dict[str, Any]:
    path = base / "image_engine_report.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def generate_diffusers(base: Path, prompt: str, negative: str, seed: int, width: int, height: int, steps: int, output: Path) -> bool:
    py = venv_python(base)
    model = base / "models" / "checkpoints" / MODEL_NAME
    config = base / "sdxl-config"
    if not py.exists():
        print(f"image engine not installed: {py}")
        return False
    if not model.exists():
        print(f"model not found: {model}")
        return False
    if not (config / "model_index.json").exists():
        print(f"SDXL config not found: {config}")
        return False
    script = r"""
import argparse, json, sys
import torch
from diffusers import StableDiffusionXLPipeline, DPMSolverMultistepScheduler

parser = argparse.ArgumentParser()
parser.add_argument("--model")
parser.add_argument("--config")
parser.add_argument("--prompt")
parser.add_argument("--negative")
parser.add_argument("--seed", type=int)
parser.add_argument("--width", type=int)
parser.add_argument("--height", type=int)
parser.add_argument("--steps", type=int)
parser.add_argument("--output")
args = parser.parse_args()

pipe = StableDiffusionXLPipeline.from_single_file(
    args.model,
    config=args.config,
    torch_dtype=torch.float16,
    use_safetensors=True,
)
pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
if torch.cuda.is_available():
    pipe = pipe.to("cuda")
    try:
        pipe.enable_model_cpu_offload()
    except Exception:
        pipe.enable_attention_slicing()
else:
    pipe = pipe.to("cpu")
    pipe.enable_attention_slicing()

generator = torch.Generator(device="cpu").manual_seed(args.seed)
image = pipe(
    prompt=args.prompt,
    negative_prompt=args.negative,
    num_inference_steps=args.steps,
    guidance_scale=5.0,
    width=args.width,
    height=args.height,
    generator=generator,
).images[0]
image.save(args.output)
print(json.dumps({"ok": True, "output": args.output}))
"""
    code = r"""
import json, sys
exec(sys.stdin.read())
"""
    cmd = [
        str(py), "-c", code,
        "--model", str(model),
        "--config", str(config),
        "--prompt", prompt,
        "--negative", negative,
        "--seed", str(seed),
        "--width", str(width),
        "--height", str(height),
        "--steps", str(steps),
        "--output", str(output),
    ]
    env = os.environ.copy()
    env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    env["HF_HOME"] = str(base / "hf-cache")
    env["HF_HUB_OFFLINE"] = "1"
    proc = subprocess.run(cmd, input=script, text=True, capture_output=True, timeout=1800, env=env)
    if proc.returncode != 0:
        print(proc.stderr[-2000:])
        return False
    return output.exists()


def generate_comfyui(url: str, prompt: str, negative: str, seed: int, width: int, height: int, steps: int, output: Path) -> bool:
    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": 5.0,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": MODEL_NAME},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "manga", "images": ["8", 0]},
        },
    }
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + "/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"ComfyUI request failed: {exc}")
        return False
    prompt_id = info.get("prompt_id")
    if not prompt_id:
        print(f"ComfyUI returned no prompt_id: {info}")
        return False
    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(3)
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/history/" + prompt_id, timeout=10) as resp:
                history = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        if prompt_id in history:
            images = history[prompt_id].get("outputs", {}).get("9", {}).get("images", [])
            if images:
                img_url = url.rstrip("/") + "/view?filename=" + images[0]["filename"] + "&subfolder=" + images[0].get("subfolder", "") + "&type=" + images[0].get("type", "output")
                urllib.request.urlretrieve(img_url, str(output))
                return output.exists()
    return False


def generate_custom_workflow(comfy_url: str, workflow: Dict[str, Any], output: Path) -> bool:
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        comfy_url.rstrip("/") + "/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"custom workflow request failed: {exc}")
        return False
    prompt_id = info.get("prompt_id")
    if not prompt_id:
        print(f"no prompt_id: {info}")
        return False
    deadline = time.time() + 1800
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
            images = node.get("images")
            if images:
                item = images[0]
                img_url = (
                    comfy_url.rstrip("/") + "/view?filename=" + item.get("filename", "")
                    + "&subfolder=" + item.get("subfolder", "")
                    + "&type=" + item.get("type", "output")
                )
                try:
                    urllib.request.urlretrieve(img_url, str(output))
                    return output.exists()
                except Exception as exc:
                    print(f"download failed: {exc}")
                    return False
    return False


def render_values(workflow: Dict[str, Any], values: Dict[str, Any]) -> Dict[str, Any]:
    rendered = json.loads(json.dumps(workflow))

    def walk(node: Any, key: Optional[str] = None) -> Any:
        if isinstance(node, dict):
            return {k: walk(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, key) for v in node]
        if isinstance(node, str):
            value = node.format(**values)
            if key in ("seed", "width", "height", "steps"):
                try:
                    return int(value)
                except ValueError:
                    return value
            if key in ("cfg", "weight", "start_at", "end_at", "denoise"):
                try:
                    return float(value)
                except ValueError:
                    return value
            return value
        return node

    return walk(rendered)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate images with local engine.")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default="lowres, bad anatomy, bad hands, extra fingers, blurry, plastic skin, text, watermark")
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--width", type=int, default=832)
    parser.add_argument("--height", type=int, default=1216)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, default=None)
    parser.add_argument("--workflow", type=Path, default=None, help="custom ComfyUI API workflow JSON with {prompt} and reference placeholders")
    parser.add_argument("--ref-image", action="append", type=Path, default=[], help="reference image; may be repeated")
    parser.add_argument("--ref-bundle", type=Path, default=None, help="reference_bundle.json path")
    parser.add_argument("--require-reference", action="store_true", help="fail unless references are actually applied through --workflow")
    args = parser.parse_args(argv)

    base = args.runtime_dir or default_runtime_dir()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    ref_paths = list(args.ref_image)
    bundle_path = args.ref_bundle
    bundle: Dict[str, Any] = {}
    if bundle_path and bundle_path.exists():
        try:
            bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            print(f"reference bundle is not valid JSON: {exc}")
        else:
            for value in bundle.get("images", {}).values():
                if value:
                    candidate = bundle_path.parent / value
                    if candidate.exists():
                        ref_paths.append(candidate)

    if args.workflow:
        if not probe_comfyui():
            print("ComfyUI API is not reachable")
            return 1
        workflow = json.loads(args.workflow.read_text(encoding="utf-8"))
        workflow_text = json.dumps(workflow)
        if args.require_reference:
            if not ref_paths:
                print("--require-reference set but no reference images were provided; generation blocked")
                return 1
            if "{ref_image_" not in workflow_text and "{reference_grid}" not in workflow_text:
                print("--require-reference set but the custom workflow has no {ref_image_N} or {reference_grid} placeholder; generation blocked")
                return 1
        values: Dict[str, Any] = {
            "prompt": args.prompt,
            "negative": args.negative,
            "seed": args.seed,
            "width": args.width,
            "height": args.height,
            "steps": args.steps,
        }
        uploaded: Dict[str, str] = {}
        for idx, ref in enumerate(ref_paths, start=1):
            name = upload_to_comfyui("http://127.0.0.1:8188", ref, "ref")
            if name is None:
                print(f"reference upload failed: {ref}")
                return 1
            uploaded[str(ref)] = name
            values[f"ref_image_{idx}"] = name
        grid_path = build_reference_grid(ref_paths, args.output.parent / "reference_grid.png") if ref_paths else None
        if grid_path is not None:
            name = upload_to_comfyui("http://127.0.0.1:8188", grid_path, "refgrid")
            values["reference_grid"] = name if name else str(grid_path)
        rendered = render_values(workflow, values)
        ok = generate_custom_workflow("http://127.0.0.1:8188", rendered, args.output)
        if ok:
            meta = {
                "prompt": args.prompt,
                "negative": args.negative,
                "seed": args.seed,
                "width": args.width,
                "height": args.height,
                "steps": args.steps,
                "workflow": str(args.workflow),
                "reference_used": bool(ref_paths),
                "reference_warning": None,
            }
            (args.output.with_suffix(".json")).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"generated: {args.output}")
            return 0
        print("custom workflow image generation failed")
        return 1

    comfy = probe_comfyui()
    reference_warning = None
    if ref_paths:
        reference_warning = (
            "reference images provided; the default SDXL/ComfyUI workflow has no IPAdapter conditioning. "
            "Pass --workflow with {ref_image_N} or {reference_grid}, or install ComfyUI_IPAdapter_plus + "
            "IPAdapter SDXL models for true reference conditioning."
        )
        print(reference_warning)
        if args.require_reference:
            print("--require-reference set but no custom multi-reference workflow was applied; generation blocked")
            return 1
    elif args.require_reference:
        print("--require-reference set but no reference images were provided; generation blocked")
        return 1
    if comfy:
        ok = generate_comfyui("http://127.0.0.1:8188", args.prompt, args.negative, args.seed, args.width, args.height, args.steps, args.output)
    else:
        ok = generate_diffusers(base, args.prompt, args.negative, args.seed, args.width, args.height, args.steps, args.output)

    if ok:
        meta = {
            "prompt": args.prompt,
            "negative_prompt": args.negative,
            "seed": args.seed,
            "width": args.width,
            "height": args.height,
            "steps": args.steps,
            "reference_used": False,
            "reference_warning": reference_warning,
        }
        (args.output.with_suffix(".json")).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"generated: {args.output}")
        return 0
    print("image generation failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
