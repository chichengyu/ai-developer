#!/usr/bin/env python3
"""Install or detect the best local image engine for manga-drama generation.

Engine priority:
  1. Codex imagegen skill / MCP (handled by engine_plan.py as assumed_mcp)
  2. Running local ComfyUI API (http://127.0.0.1:8188)
  3. Running local Stable Diffusion WebUI API (http://127.0.0.1:7860)
  4. Auto-install diffusers runtime + RealVisXL realistic checkpoint
     (or ComfyUI when --engine comfyui is requested)

Usage:
    python install_image_engine.py --check
    python install_image_engine.py --dry-run
    python install_image_engine.py --auto-install [--engine diffusers|comfyui]
    python install_image_engine.py --start

Writes:
    <runtime_dir>/image_engine_report.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_ffmpeg_vapoursynth import tool_path


COMFYUI_URL = "https://github.com/comfyanonymous/ComfyUI.git"
IPADAPTER_NODE_URL = "https://github.com/cubiq/ComfyUI_IPAdapter_plus"
MODEL_NAME = "RealVisXL_V4.0.safetensors"
MODEL_URLS = [
    "https://hf-mirror.com/SG161222/RealVisXL_V4.0/resolve/main/RealVisXL_V4.0.safetensors",
    "https://huggingface.co/SG161222/RealVisXL_V4.0/resolve/main/RealVisXL_V4.0.safetensors",
]
IPADAPTER_MODEL_NAME = "ip-adapter_sdxl_vit-h.safetensors"
IPADAPTER_MODEL_URLS = [
    "https://hf-mirror.com/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl_vit-h.safetensors",
    "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl_vit-h.safetensors",
]


def default_runtime_dir() -> Path:
    override = os.environ.get("MANGA_IMAGE_RUNTIME_DIR")
    if override:
        return Path(override)
    if Path("E:/soft").is_dir():
        return Path("E:/soft/manga-drama-image")
    local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    return Path(local) / "manga-drama-video" / "image-engine"


SDXL_CONFIG_REPO = "stabilityai/stable-diffusion-xl-base-1.0"
SDXL_CONFIG_PATTERNS = [
    "model_index.json",
    "scheduler/*",
    "text_encoder/config.json",
    "text_encoder_2/config.json",
    "tokenizer/*",
    "tokenizer_2/*",
    "unet/config.json",
    "vae/config.json",
]


def ensure_sdxl_config(base: Path) -> bool:
    config = base / "sdxl-config"
    if (config / "model_index.json").exists():
        return True
    py = venv_python(base)
    if not py.exists():
        print(f"SDXL config needs the runtime venv: {py}")
        return False
    code = r"""
import os, sys
from huggingface_hub import snapshot_download
repo = sys.argv[1]
dest = sys.argv[2]
patterns = sys.argv[3].split("|")
try:
    snapshot_download(repo, local_dir=dest, allow_patterns=patterns, max_workers=4)
except Exception as exc:
    print(exc)
    raise SystemExit(1)
"""
    env = os.environ.copy()
    env["HF_ENDPOINT"] = "https://hf-mirror.com"
    env["HF_HOME"] = str(base / "hf-cache")
    print(f"downloading SDXL config skeleton to {config} ...", flush=True)
    result = subprocess.run(
        [str(py), "-c", code, SDXL_CONFIG_REPO, str(config), "|".join(SDXL_CONFIG_PATTERNS)],
        capture_output=True,
        text=True,
        timeout=1800,
        env=env,
    )
    if result.returncode != 0:
        print(result.stderr[-1500:])
        return False
    return (config / "model_index.json").exists()


def http_json(url: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "manga-drama-video/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def probe_comfyui() -> Optional[str]:
    if isinstance(http_json("http://127.0.0.1:8188/system_stats"), dict):
        return "comfyui"
    return None


def probe_sd_webui() -> Optional[str]:
    if isinstance(http_json("http://127.0.0.1:7860/sdapi/v1/options"), dict):
        return "sd-webui"
    return None


def probe_cli_engines() -> List[str]:
    return [name for name in ("comfy", "comfyui", "invokeai", "sd") if shutil.which(name)]


def probe_local_image_engines() -> Dict[str, Any]:
    engines: Dict[str, Any] = {}
    engine = probe_comfyui()
    if engine:
        engines["comfyui"] = {"status": "available", "endpoint": "http://127.0.0.1:8188"}
    engine = probe_sd_webui()
    if engine:
        engines["sd-webui"] = {"status": "available", "endpoint": "http://127.0.0.1:7860"}
    cli = probe_cli_engines()
    if cli:
        engines.setdefault("cli", {"status": "available", "commands": cli})
    base = default_runtime_dir()
    model = base / "models" / "checkpoints" / MODEL_NAME
    if venv_python(base).exists() and model.exists():
        engines["diffusers"] = {
            "status": "available",
            "runtime_dir": str(base),
            "model": str(model),
            "generate": "generate_images.py",
        }
    return engines


def has_gpu() -> bool:
    if platform.system().lower() != "windows":
        return shutil.which("nvidia-smi") is not None
    return Path("C:/Windows/System32/nvidia-smi.exe").exists() or shutil.which("nvidia-smi") is not None


def run(cmd: List[str], cwd: Optional[Path] = None, timeout: Optional[int] = None) -> int:
    print("$ " + " ".join(str(c) for c in cmd), flush=True)
    try:
        result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, timeout=timeout)
        return result.returncode
    except FileNotFoundError:
        print(f"command not found: {cmd[0]}")
        return 1
    except subprocess.TimeoutExpired:
        print(f"timeout: {cmd[0]}")
        return 1


def probe_size(url: str) -> Optional[int]:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "manga-drama-video/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            length = resp.headers.get("Content-Length")
            return int(length) if length else None
    except Exception:
        return None


def pick_model_url() -> Tuple[str, Optional[int]]:
    for url in MODEL_URLS:
        size = probe_size(url)
        if size:
            return url, size
    return MODEL_URLS[0], None


def download_chunk(url: str, dest: Path, start: int, end: int, attempts: int = 4) -> bool:
    original_start = start
    existing = dest.stat().st_size if dest.exists() else 0
    if existing > end - start + 1:
        existing = end - start + 1
    start += existing
    if start > end:
        return True
    headers = {"User-Agent": "manga-drama-video/1.0", "Range": f"bytes={start}-{end}"}
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                with dest.open("ab") as fh:
                    while True:
                        chunk = resp.read(1024 * 512)
                        if not chunk:
                            break
                        fh.write(chunk)
            if dest.stat().st_size == end - original_start + 1:
                return True
        except Exception as exc:
            print(f"  chunk {start} attempt {attempt + 1} failed: {exc}", flush=True)
            time.sleep(2)
    return False


def download_chunk_any(urls: List[str], dest: Path, start: int, end: int, attempts: int = 4) -> bool:
    original_start = start
    existing = dest.stat().st_size if dest.exists() else 0
    if existing > end - original_start + 1:
        existing = end - original_start + 1
    start += existing
    if start > end:
        return True
    for url in urls:
        for attempt in range(attempts):
            headers = {"User-Agent": "manga-drama-video/1.0", "Range": f"bytes={start}-{end}"}
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=120) as resp:
                    with dest.open("ab") as fh:
                        while True:
                            chunk = resp.read(1024 * 512)
                            if not chunk:
                                break
                            fh.write(chunk)
                if dest.stat().st_size == end - original_start + 1:
                    return True
            except Exception as exc:
                print(f"  chunk {original_start} attempt {attempt + 1} failed on {url.split('/')[2]}: {exc}", flush=True)
                time.sleep(2)
            existing = dest.stat().st_size if dest.exists() else 0
            start = original_start + min(existing, end - original_start + 1)
            if start > end:
                return True
    return False


def multi_connection_download(url: str, dest: Path, total_size: int, connections: int = 24) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == total_size:
        print(f"model already present: {dest}")
        return True
    chunk_size = max(8 * 1024 * 1024, math.ceil(total_size / connections))
    ranges = []
    start = 0
    while start < total_size:
        end = min(start + chunk_size - 1, total_size - 1)
        ranges.append((start, end))
        start = end + 1
    print(f"downloading {dest.name} ({total_size // 1048576}MB) with {min(connections, len(ranges))} connections", flush=True)
    done = threading.Event()
    progress: Dict[int, int] = {}
    lock = threading.Lock()

    def worker(start: int, end: int) -> bool:
        part = dest.with_name(f"{dest.name}.part{start:012d}")
        ok = download_chunk(url, part, start, end)
        with lock:
            progress[start] = end - start + 1 if ok else 0
            downloaded = sum(progress.values())
            if downloaded and downloaded % (8 * 1024 * 1024) < 4 * 1024 * 1024:
                print(f"\r  {downloaded // 1048576}MB / {total_size // 1048576}MB", end="", flush=True)
        return ok

    with ThreadPoolExecutor(max_workers=connections) as executor:
        futures = [executor.submit(worker, start, end) for start, end in ranges]
        ok = all(f.result() for f in as_completed(futures))
    print()
    if not ok:
        print("download failed for one or more chunks")
        return False
    print("assembling model file ...", flush=True)
    with dest.open("wb") as out:
        for start, _ in ranges:
            part = dest.with_name(f"{dest.name}.part{start:012d}")
            with part.open("rb") as fh:
                shutil.copyfileobj(fh, out, 1024 * 1024)
            part.unlink()
    if dest.stat().st_size != total_size:
        print(f"size mismatch: {dest.stat().st_size} != {total_size}")
        return False
    print(f"model ready: {dest}")
    return True


def resilient_multi_download(urls: List[str], dest: Path, total_size: int, connections: int = 24) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == total_size:
        print(f"model already present: {dest}")
        return True
    chunk_size = max(8 * 1024 * 1024, math.ceil(total_size / connections))
    ranges = []
    start = 0
    while start < total_size:
        end = min(start + chunk_size - 1, total_size - 1)
        ranges.append((start, end))
        start = end + 1
    print(f"downloading {dest.name} ({total_size // 1048576}MB) with {min(connections, len(ranges))} resilient connections", flush=True)
    done = threading.Event()
    progress: Dict[int, int] = {}
    lock = threading.Lock()

    def worker(start: int, end: int) -> bool:
        part = dest.with_name(f"{dest.name}.part{start:012d}")
        ok = download_chunk_any(urls, part, start, end)
        with lock:
            progress[start] = end - start + 1 if ok else 0
            downloaded = sum(progress.values())
            if downloaded and downloaded % (8 * 1024 * 1024) < 4 * 1024 * 1024:
                print(f"\r  {downloaded // 1048576}MB / {total_size // 1048576}MB", end="", flush=True)
        return ok

    with ThreadPoolExecutor(max_workers=connections) as executor:
        futures = [executor.submit(worker, start, end) for start, end in ranges]
        ok = all(f.result() for f in as_completed(futures))
    print()
    if not ok:
        print("resilient download failed for one or more chunks")
        return False
    print("assembling model file ...", flush=True)
    with dest.open("wb") as out:
        for start, _ in ranges:
            part = dest.with_name(f"{dest.name}.part{start:012d}")
            with part.open("rb") as fh:
                shutil.copyfileobj(fh, out, 1024 * 1024)
            part.unlink()
    if dest.stat().st_size != total_size:
        print(f"size mismatch: {dest.stat().st_size} != {total_size}")
        return False
    print(f"model ready: {dest}")
    return True


NODE_DL_JS = r"""
const fs = require("fs");
const url = process.argv[1];
const dest = process.argv[2];
const total = Number(process.argv[3]);
const conns = Number(process.argv[4] || 8);

async function head(u) {
  const r = await fetch(u, { method: "HEAD" });
  if (!r.ok) throw new Error("HEAD " + r.status);
  return Number(r.headers.get("content-length"));
}

async function getRange(u, start, end, part) {
  for (let attempt = 0; attempt < 30; attempt++) {
    const existing = fs.existsSync(part) ? fs.statSync(part).size : 0;
    const s = start + existing;
    if (s > end) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 120000);
    try {
      const r = await fetch(u, { headers: { Range: "bytes=" + s + "-" + end }, signal: ctrl.signal });
      if (!r.ok && r.status !== 206) throw new Error("HTTP " + r.status);
      const fd = fs.openSync(part, existing ? "a" : "w");
      const reader = r.body.getReader();
      for (;;) {
        const d = await reader.read();
        if (d.done) break;
        fs.writeSync(fd, Buffer.from(d.value));
      }
      fs.closeSync(fd);
      clearTimeout(timer);
      return;
    } catch (e) {
      clearTimeout(timer);
      await new Promise(r => setTimeout(r, 4000 + attempt * 2000));
    }
  }
  throw new Error("chunk failed " + part);
}

(async () => {
  const headSize = await head(url);
  const size = total > 0 ? total : headSize;
  if (fs.existsSync(dest) && fs.statSync(dest).size === size) {
    console.log("model already present");
    process.exit(0);
  }
  const chunk = Math.max(8 * 1024 * 1024, Math.ceil(size / conns));
  const ranges = [];
  for (let s = 0; s < size; s += chunk) ranges.push([s, Math.min(s + chunk - 1, size - 1)]);
  const parts = ranges.map(([s]) => dest + ".part" + String(s).padStart(12, "0"));
  await Promise.all(ranges.map(([s, e], i) => getRange(url, s, e, parts[i])));
  const fd = fs.openSync(dest, "w");
  for (const p of parts) {
    const buf = fs.readFileSync(p);
    fs.writeSync(fd, buf);
    fs.unlinkSync(p);
  }
  fs.closeSync(fd);
  if (fs.statSync(dest).size !== size) throw new Error("size mismatch");
  console.log("model ready " + dest);
})().catch(e => { console.error(e.message); process.exit(1); });
"""


def download_model(url: str, dest: Path, total_size: int, connections: int = 24) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    node = tool_path("node")
    if node:
        print("downloading model with Node resume downloader ...", flush=True)
        proc = subprocess.run(
            [node, "-e", NODE_DL_JS, url, str(dest), str(total_size), str(connections)],
            timeout=36000,
        )
        return proc.returncode == 0 and dest.exists() and dest.stat().st_size == total_size
    print("Node not found; falling back to Python single-stream download ...", flush=True)
    return multi_connection_download(url, dest, total_size, connections=1)


def venv_python(base: Path) -> Path:
    venv_dir = Path(os.environ.get("MANGA_VENV_DIR", "")) if os.environ.get("MANGA_VENV_DIR") else base / "venv"
    if platform.system().lower() == "windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def make_venv(base: Path) -> Path:
    python = os.environ.get("MANGA_PYTHON") or tool_path("python") or sys.executable
    venv_dir = Path(os.environ.get("MANGA_VENV_DIR", "")) if os.environ.get("MANGA_VENV_DIR") else base / "venv"
    if not venv_dir.exists():
        print(f"creating Python virtual environment at {venv_dir} ...", flush=True)
        if run([python, "-m", "venv", str(venv_dir)]) != 0:
            raise RuntimeError("failed to create venv")
    py = venv_dir / ("Scripts/python.exe" if platform.system().lower() == "windows" else "bin/python")
    if run([str(py), "-m", "pip", "install", "--upgrade", "pip"]) != 0:
        raise RuntimeError("failed to upgrade pip")
    return py


def local_torch_wheels(wheels_dir: str) -> List[Path]:
    wheels: List[Path] = []
    for wheel in sorted(Path(wheels_dir).glob("*.whl")):
        if "%2B" in wheel.name:
            target = wheel.with_name(wheel.name.replace("%2B", "+"))
            if not target.exists():
                wheel.rename(target)
            wheels.append(target)
        else:
            wheels.append(wheel)
    return wheels


def install_diffusers(base: Path, gpu: bool) -> bool:
    print(f"installing diffusers image engine to {base}")
    base.mkdir(parents=True, exist_ok=True)
    try:
        py = make_venv(base)
        wheels_dir = os.environ.get("TORCH_WHEELS_DIR")
        if wheels_dir:
            wheels = local_torch_wheels(wheels_dir)
            print(f"installing PyTorch from local wheels ({len(wheels)} files) ...", flush=True)
            if not wheels or run([str(py), "-m", "pip", "install", *[str(w) for w in wheels]]) != 0:
                return False
        else:
            torch_index = os.environ.get("TORCH_INDEX_URL") or (
                "https://download.pytorch.org/whl/cu128" if gpu else "https://download.pytorch.org/whl/cpu"
            )
            print("installing PyTorch ...", flush=True)
            if run([str(py), "-m", "pip", "install", "torch", "torchvision", "torchaudio", "--index-url", torch_index]) != 0:
                return False
        print("installing diffusers and image processing dependencies ...", flush=True)
        deps = [
            "diffusers", "transformers", "accelerate", "safetensors", "sentencepiece",
            "pillow", "opencv-python-headless", "numpy",
        ]
        if run([str(py), "-m", "pip", "install", *deps]) != 0:
            return False
    except Exception as exc:
        print(f"install failed: {exc}")
        return False

    model_dir = base / "models" / "checkpoints"
    model_path = model_dir / MODEL_NAME
    if model_path.exists() and model_path.stat().st_size > 1024 * 1024 * 1024:
        print(f"model already present: {model_path}")
    else:
        url, size = pick_model_url()
        if not size:
            print("cannot determine model size; aborting download")
            return False
        if not download_model(url, model_path, size):
            return False
    if not ensure_sdxl_config(base):
        print("SDXL config missing; run install again after network access is restored")
        return False
    return True


def comfy_root_dir(base: Path) -> Path:
    if (base / "main.py").exists():
        return base
    nested = base / "ComfyUI"
    return nested


def link_models_dir(comfy_root: Path, base: Path) -> None:
    target = comfy_root / "models"
    source = base / "models"
    if not source.is_dir():
        return
    if target.exists():
        if any(target.iterdir()):
            return
        target.rmdir()
    try:
        os.symlink(source, target, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(target), str(source)],
        capture_output=True,
        text=True,
    )


def install_comfyui(base: Path, gpu: bool) -> bool:
    comfy_root = comfy_root_dir(base)
    print(f"installing ComfyUI to {comfy_root}")
    base.mkdir(parents=True, exist_ok=True)
    if not comfy_root.exists():
        git = shutil.which("git")
        if not git:
            print("git is required for ComfyUI install; use --engine diffusers instead")
            return False
        if run([git, "clone", "--depth", "1", COMFYUI_URL, str(comfy_root)], timeout=600) != 0:
            return False
    try:
        py = make_venv(base)
        wheels_dir = os.environ.get("TORCH_WHEELS_DIR")
        if wheels_dir:
            wheels = local_torch_wheels(wheels_dir)
            print(f"installing PyTorch from local wheels ({len(wheels)} files) ...", flush=True)
            if not wheels or run([str(py), "-m", "pip", "install", *[str(w) for w in wheels]]) != 0:
                return False
        else:
            torch_index = os.environ.get("TORCH_INDEX_URL") or (
                "https://download.pytorch.org/whl/cu128" if gpu else "https://download.pytorch.org/whl/cpu"
            )
            print("installing PyTorch ...", flush=True)
            if run([str(py), "-m", "pip", "install", "torch", "torchvision", "torchaudio", "--index-url", torch_index]) != 0:
                return False
        if run([str(py), "-m", "pip", "install", "-r", str(comfy_root / "requirements.txt")]) != 0:
            return False
    except Exception as exc:
        print(f"install failed: {exc}")
        return False

    link_models_dir(comfy_root, base)
    model_path = comfy_root / "models" / "checkpoints" / MODEL_NAME
    if not model_path.exists() and not (base / "models" / "checkpoints" / MODEL_NAME).exists():
        url, size = pick_model_url()
        if not size:
            print("cannot determine model size; aborting download")
            return False
        if not download_model(url, model_path, size):
            return False
    return True


def install_ipadapter_node(comfy_root: Path, py: Path) -> bool:
    dest = comfy_root / "custom_nodes" / "ComfyUI_IPAdapter_plus"
    if (dest / "__init__.py").exists():
        print("IPAdapter node already present")
    else:
        git = shutil.which("git")
        if not git:
            print("git is required to install IPAdapter node")
            return False
        print("installing ComfyUI_IPAdapter_plus ...")
        if run([git, "clone", "--depth", "1", IPADAPTER_NODE_URL, str(dest)], timeout=300) != 0:
            print("retrying IPAdapter clone with SSL verification disabled ...")
            if run([git, "-c", "http.sslVerify=false", "clone", "--depth", "1", IPADAPTER_NODE_URL, str(dest)], timeout=300) != 0:
                return False
        requirements = dest / "requirements.txt"
        if requirements.exists():
            print("installing IPAdapter requirements ...")
            if run([str(py), "-m", "pip", "install", "-r", str(requirements)]) != 0:
                return False
    model_dir = comfy_root / "models" / "ipadapter"
    model_path = model_dir / IPADAPTER_MODEL_NAME
    if model_path.exists() and model_path.stat().st_size > 1024 * 1024 * 1024:
        print(f"IPAdapter model already present: {model_path}")
        return True
    size = None
    for url in IPADAPTER_MODEL_URLS:
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "manga-drama-video/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                length = resp.headers.get("Content-Length")
                if length:
                    size = int(length)
                    break
        except Exception:
            continue
    if not size:
        print("cannot determine IPAdapter model size; install failed")
        return False
    print(f"downloading {IPADAPTER_MODEL_NAME} ({size // 1048576}MB) ...")
    return resilient_multi_download(IPADAPTER_MODEL_URLS, model_path, size)


def start_comfyui(base: Path) -> bool:
    comfy_root = comfy_root_dir(base)
    py = venv_python(base)
    if not py.exists():
        print(f"ComfyUI runtime not found: {py}")
        return False
    log = base / "comfyui.log"
    kwargs: Dict[str, Any] = {
        "stdout": log.open("ab"),
        "stderr": log.open("ab"),
    }
    if platform.system().lower() == "windows":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        [str(py), str(comfy_root / "main.py"), "--port", "8188", "--cuda-device", "0" if has_gpu() else "cpu"],
        cwd=str(comfy_root),
        **kwargs,
    )
    (comfy_root / "comfyui.pid").write_text(str(proc.pid), encoding="utf-8")
    print(f"ComfyUI starting pid={proc.pid}")
    deadline = time.time() + 180
    while time.time() < deadline:
        if probe_comfyui():
            print("ComfyUI API ready: http://127.0.0.1:8188")
            return True
        if proc.poll() is not None:
            print(f"ComfyUI exited early with code {proc.returncode}")
            return False
        time.sleep(2)
    print("ComfyUI did not become ready in time; check comfyui.log")
    return False


def diffusers_ready(base: Path) -> bool:
    model = base / "models" / "checkpoints" / MODEL_NAME
    py = venv_python(base)
    if not model.exists() or not py.exists():
        return False
    result = subprocess.run(
        [str(py), "-c", "import torch, diffusers; print(torch.cuda.is_available())"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode == 0 and "True" in (result.stdout or "")


def write_report(base: Path, status: Dict[str, Any]) -> None:
    base.mkdir(parents=True, exist_ok=True)
    report = {
        "os": platform.platform(),
        "arch": platform.machine(),
        "gpu": has_gpu(),
        "runtime_dir": str(base),
        **status,
    }
    path = base / "image_engine_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote: {path}")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Detect/install local image engine.")
    parser.add_argument("--check", action="store_true", help="detect existing engines and exit")
    parser.add_argument("--dry-run", action="store_true", help="report planned installation without changing system")
    parser.add_argument("--auto-install", action="store_true", help="install local image engine when missing")
    parser.add_argument("--engine", choices=("auto", "diffusers", "comfyui"), default="auto")
    parser.add_argument("--force", action="store_true", help="install the selected engine even when another engine exists")
    parser.add_argument("--start", action="store_true", help="start installed engine")
    parser.add_argument("--install-ref-nodes", action="store_true", help="install ComfyUI IPAdapter reference-conditioning nodes")
    parser.add_argument("--runtime-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    base = args.runtime_dir or default_runtime_dir()
    local = probe_local_image_engines()
    print("local image engines:", json.dumps(local, ensure_ascii=False))

    if args.install_ref_nodes:
        comfy_root = comfy_root_dir(base)
        if not comfy_root.exists():
            print("ComfyUI not found; install ComfyUI first or pass --auto-install --engine comfyui")
            return 1
        ok = install_ipadapter_node(comfy_root, venv_python(base))
        write_report(base, {"local_engines": local, "installed": ok, "engine": "comfyui", "ref_nodes": "ipadapter", "result": "ok" if ok else "failed"})
        return 0 if ok else 1

    if args.check:
        write_report(base, {"local_engines": local, "planned": False})
        return 0 if local else 1

    if args.dry_run:
        engine = args.engine if args.engine != "auto" else "diffusers"
        plan = {
            "engine": engine,
            "runtime_dir": str(base),
            "model": MODEL_NAME,
            "ref_model": IPADAPTER_MODEL_NAME,
            "model_urls": MODEL_URLS,
            "ref_model_urls": IPADAPTER_MODEL_URLS,
            "gpu": has_gpu(),
        }
        write_report(base, {"local_engines": local, "planned": True, "install_plan": plan})
        print("dry run: no system changes")
        return 0

    if args.start and not args.auto_install:
        engine = "diffusers"
        if comfy_root_dir(base).exists():
            engine = "comfyui"
        if engine == "comfyui":
            return 0 if start_comfyui(base) else 1
        return 0 if diffusers_ready(base) else 1

    if args.engine == "comfyui" and not probe_comfyui() and not comfy_root_dir(base).exists():
        if not args.auto_install:
            print("ComfyUI not installed; run with --auto-install")
            return 1
        ok = install_comfyui(base, has_gpu())
        if ok and args.start:
            ok = start_comfyui(base)
        if ok and args.auto_install:
            ok = install_ipadapter_node(comfy_root_dir(base), venv_python(base))
        write_report(base, {"local_engines": local, "installed": ok, "engine": "comfyui", "result": "ok" if ok else "failed"})
        return 0 if ok else 1

    if local and not args.force:
        if args.auto_install and "comfyui" in local:
            ok = install_ipadapter_node(comfy_root_dir(base), venv_python(base))
            if not ok:
                write_report(base, {"local_engines": local, "installed": False, "ref_nodes": "ipadapter", "result": "failed"})
                return 1
        write_report(base, {"local_engines": local, "installed": False, "result": "already-available"})
        print("image engine already available; nothing to install")
        return 0

    if not args.auto_install:
        print("no local image engine found; run with --auto-install to install one")
        return 1

    engine = args.engine
    if engine == "auto":
        engine = "diffusers"
    ok = install_diffusers(base, has_gpu()) if engine == "diffusers" else install_comfyui(base, has_gpu())
    if ok and args.start:
        ok = diffusers_ready(base) if engine == "diffusers" else start_comfyui(base)
    if ok and engine == "comfyui" and args.auto_install:
        ok = install_ipadapter_node(comfy_root_dir(base), venv_python(base))
    write_report(base, {"local_engines": local, "installed": ok, "engine": engine, "result": "ok" if ok else "failed"})
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
