#!/usr/bin/env python3
"""Detect current hardware and recommend manga-drama generation settings."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any, Dict, Optional


def detect_vram_gb() -> Optional[float]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return None
        line = result.stdout.strip().splitlines()[0]
        name, mem = line.rsplit(",", 1)
        return float(mem.strip()) / 1024.0
    except Exception:
        return None


def detect_ram_gb() -> Optional[float]:
    if platform.system().lower() == "windows":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullTotalPhys / (1024 ** 3)
        except Exception:
            return None
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb / (1024 ** 2)
    except Exception:
        return None
    return None


def pick_profile(vram_gb: Optional[float], ram_gb: Optional[float]) -> str:
    vram = vram_gb if vram_gb is not None else 8.0
    if vram < 7.5:
        return "wan-low"
    if vram < 12:
        return "wan-8gb"
    if vram < 16:
        return "wan-12gb"
    return "wan-high"


def recommend(profile: str, wan_available: bool, ltx_available: bool, ram_gb: Optional[float]) -> Dict[str, Any]:
    ram = ram_gb if ram_gb is not None else 16.0
    defaults: Dict[str, Any] = {
        "wan-low": {
            "model": "ltx" if ltx_available else "wan",
            "width": 384,
            "height": 384,
            "frames": 9,
            "steps": 8,
            "block_swap": 20 if not ltx_available else 0,
            "force_offload": True,
            "text_device": "cpu",
        },
        "wan-8gb": {
            "model": "wan",
            "width": 480,
            "height": 832,
            "frames": 25,
            "steps": 12,
            "block_swap": 20,
            "force_offload": True,
            "text_device": "cpu",
        },
        "wan-12gb": {
            "model": "wan",
            "width": 480,
            "height": 832,
            "frames": 33,
            "steps": 16,
            "block_swap": 12,
            "force_offload": True,
            "text_device": "cpu",
        },
        "wan-high": {
            "model": "wan",
            "width": 832,
            "height": 480,
            "frames": 49,
            "steps": 20,
            "block_swap": 6,
            "force_offload": False,
            "text_device": "gpu",
        },
    }
    rec = dict(defaults.get(profile, defaults["wan-8gb"]))
    if ram < 16:
        rec["frames"] = max(9, int(rec["frames"] * 0.75))
        rec["steps"] = max(4, int(rec["steps"] * 0.75))
        rec["block_swap"] = min(rec["block_swap"], 12)
    elif ram >= 32:
        rec["block_swap"] = max(rec["block_swap"], 20)
    if rec.get("model") == "wan" and not wan_available:
        rec["model"] = "ltx" if ltx_available else "wan"
    return rec


def detect_hardware_profile(wan_available: bool = True, ltx_available: bool = False) -> Dict[str, Any]:
    vram = detect_vram_gb()
    ram = detect_ram_gb()
    profile = pick_profile(vram, ram)
    rec = recommend(profile, wan_available, ltx_available, ram)
    return {
        "profile": profile,
        "vram_gb": vram,
        "ram_gb": ram,
        "recommended": rec,
        "gpu_name": _gpu_name(),
    }


def _gpu_name() -> Optional[str]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip().splitlines()[0] if result.returncode == 0 else None
    except Exception:
        return None


def main() -> int:
    import json

    print(json.dumps(detect_hardware_profile(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
