#!/usr/bin/env python3
"""Auto-install FFmpeg, VapourSynth, plugins, and enhancement models.

Usage:
    python install_ffmpeg_vapoursynth.py <project_dir> --auto-install
    python install_ffmpeg_vapoursynth.py <project_dir> --install-ffmpeg
    python install_ffmpeg_vapoursynth.py <project_dir> --install-vapoursynth
    python install_ffmpeg_vapoursynth.py <project_dir> --install-plugins
    python install_ffmpeg_vapoursynth.py <project_dir> --install-models --model-dir <dir>

Writes:
    <project_dir>/install_report.json
    <project_dir>/09_install_report.md
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional


MODEL_REGISTRY = {
    "realesrgan_x4plus": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
    "realesrgan_x4plus_anime_6b": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
}

PLUGIN_REGISTRY = {
    "KNLMeansCL": "Khanattila/KNLMeansCL",
    "mvtools": "dubhater/vapoursynth-mvtools",
    "nnedi3": "dubhater/vapoursynth-nnedi3",
}

VSREPO_PLUGINS = [
    "mvsfunc",
    "havsfunc",
    "VSUtil",
    "fmtconv",
    "FFTW3 Library",
    "MVTools",
    "DFTTest",
    "BM3D",
    "NNEDI3",
    "NNEDI3 Weights",
    "CAS",
    "AWarpSharp2",
    "Neo f3kdb",
    "Deblock",
    "FFmpegSource2",
]


_EXTRA_TOOL_DIR = Path(os.environ["MANGA_TOOL_DIR"]) if os.environ.get("MANGA_TOOL_DIR") else None
KNOWN_WINDOWS_TOOL_DIRS = ([_EXTRA_TOOL_DIR] if _EXTRA_TOOL_DIR else []) + [
    Path("E:/soft/ffmpeg-8.1.2-full_build/bin"),
    Path("C:/ffmpeg/bin"),
    Path("C:/Program Files/ffmpeg/bin"),
    Path("C:/Program Files (x86)/ffmpeg/bin"),
    Path("E:/soft/node"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python313",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python313" / "Scripts",
]


def tool_path(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    if platform.system().lower() == "windows":
        exe = name + (".exe" if os.name == "nt" else "")
        for base in KNOWN_WINDOWS_TOOL_DIRS:
            candidate = base / exe
            if candidate.is_file():
                return str(candidate)
    return None


def have_tool(name: str) -> bool:
    return tool_path(name) is not None


def run(cmd: List[str], cwd: Optional[Path] = None) -> int:
    print("$ " + " ".join(cmd))
    try:
        result = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
        return result.returncode
    except FileNotFoundError:
        print(f"command not found: {cmd[0]}")
        return 1


def tool_version(name: str) -> str:
    try:
        result = subprocess.run(
            [name, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return (result.stdout or result.stderr).strip().splitlines()[0][:160]
        return (result.stdout or result.stderr).strip().splitlines()[0][:120]
    except Exception:
        return "unavailable"


def compat_tags() -> List[str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        if "64" in machine or "amd64" in machine:
            return ["win64", "x64", "amd64", "windows"]
        return ["win32", "x86", "windows"]
    if system == "linux":
        if machine in ("x86_64", "amd64"):
            return ["linux", "x86_64", "amd64"]
        if machine in ("aarch64", "arm64"):
            return ["linux", "aarch64", "arm64"]
        return ["linux"]
    if system == "darwin":
        if machine in ("arm64", "aarch64"):
            return ["darwin", "macos", "arm64", "aarch64"]
        return ["darwin", "macos", "x86_64", "amd64"]
    return [system]


def download_file(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "codex-manga-drama-video/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as fh:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    fh.write(chunk)
        return True
    except Exception as exc:
        print(f"download failed {dest.name}: {exc}")
        return False


def latest_release_assets(repo: str) -> List[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "codex-manga-drama-video/1.0", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("prerelease") is True or data.get("draft") is True:
        raise RuntimeError(f"{repo} latest release is marked prerelease/draft")
    return data.get("assets", [])


def install_ffmpeg_windows() -> bool:
    ffmpeg = tool_path("ffmpeg")
    ffprobe = tool_path("ffprobe")
    if ffmpeg and ffprobe:
        print(f"ffmpeg already available: {ffmpeg}")
        return True
    for cmd in (
        ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-source-agreements", "--accept-package-agreements"],
        ["choco", "install", "ffmpeg", "-y"],
        ["scoop", "install", "ffmpeg"],
    ):
        if run(cmd) == 0 and have_tool("ffmpeg") and have_tool("ffprobe"):
            return True
    return False


PYTHON_INSTALLER_URL = "https://www.python.org/ftp/python/3.13.14/python-3.13.14-amd64.exe"
VS_R78_FALLBACK = "https://github.com/vapoursynth/vapoursynth/releases/download/R78/VapourSynth-x64-R78.exe"


def python_installer_candidates() -> List[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python"
    candidates = [
        local / "Python313" / "python.exe",
        local / "Python312" / "python.exe",
        Path("C:/Python313/python.exe"),
        Path("C:/Python312/python.exe"),
        Path("C:/Program Files/Python313/python.exe"),
        Path("C:/Program Files/Python312/python.exe"),
    ]
    return [c for c in candidates if c.is_file()]


def install_python_windows(project: Path) -> bool:
    python = tool_path("python")
    if python:
        print(f"Python already available: {python}")
        return True
    installer = project / "installers" / "python-3.13.14-amd64.exe"
    print("installing Python 3.13.14 (required by VapourSynth installer)...")
    if not download_file(PYTHON_INSTALLER_URL, installer):
        return False
    return run([
        str(installer), "/quiet", "InstallAllUsers=0", "PrependPath=1",
        "Include_launcher=1", "Include_test=0", "Include_doc=0",
        "Include_tcltk=0", "Include_pip=1", "Shortcuts=0", "AssociateFiles=0",
    ]) == 0


def install_vapoursynth_windows(project: Path) -> bool:
    if have_tool("vspipe"):
        print("VapourSynth already available")
        return True
    if not python_installer_candidates() and not install_python_windows(project):
        print("Python is required for the VapourSynth installer and could not be installed")
        return False
    assets = []
    try:
        assets = latest_release_assets("vapoursynth/vapoursynth")
    except Exception as exc:
        print(f"cannot query VapourSynth releases: {exc}; trying R78 direct download")
        assets = []
    candidates = [
        a for a in assets
        if a.get("name", "").lower().endswith(".exe")
        and any(tag in a.get("name", "").lower() for tag in compat_tags())
    ]
    if not candidates:
        print("no GitHub installer asset found; trying known R78 direct download")
        asset = {"name": "VapourSynth-x64-R78.exe", "browser_download_url": VS_R78_FALLBACK}
    else:
        asset = candidates[0]
    installer = project / "installers" / asset["name"]
    if not download_file(asset["browser_download_url"], installer):
        return False
    return run([
        str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
    ]) == 0


def find_plugin_dir() -> Optional[Path]:
    candidates = [
        Path(os.environ.get("APPDATA", "")) / "VapourSynth" / "plugins64",
        Path(os.environ.get("LOCALAPPDATA", "")) / "VapourSynth" / "plugins64",
        Path("C:/Program Files/VapourSynth/plugins64"),
        Path("C:/Program Files (x86)/VapourSynth/plugins64"),
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def install_plugins() -> bool:
    vsrepo = tool_path("vsrepo")
    if vsrepo:
        print("using vsrepo to install plugins")
        cmd = [vsrepo, "install", *VSREPO_PLUGINS]
        if run(cmd) == 0:
            return True
        print("vsrepo install failed; falling back to direct downloads")
    plugin_dir = find_plugin_dir()
    if plugin_dir is None:
        print("VapourSynth plugin directory not found; install VapourSynth first")
        return False
    ok = True
    for name, repo in PLUGIN_REGISTRY.items():
        try:
            assets = latest_release_assets(repo)
        except Exception as exc:
            print(f"cannot query {name}: {exc}")
            ok = False
            continue
        tags = compat_tags()
        compatible = [
            a for a in assets
            if any(tag in a.get("name", "").lower() for tag in tags)
            and a.get("name", "").lower().endswith((".zip", ".7z", ".tar.gz", ".tgz"))
        ]
        if not compatible:
            print(f"no compatible asset for {name} on {platform.system()} {platform.machine()}")
            ok = False
            continue
        asset = compatible[0]
        zip_path = plugin_dir / asset["name"]
        if not download_file(asset["browser_download_url"], zip_path):
            ok = False
            continue
        try:
            if zip_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(zip_path) as zf:
                    for member in zf.namelist():
                        if member.lower().endswith((".dll", ".so")):
                            zf.extract(member, plugin_dir)
            elif have_tool("7z") or have_tool("7za"):
                seven_zip = "7z" if have_tool("7z") else "7za"
                run([seven_zip, "x", "-y", str(zip_path), f"-o{plugin_dir}"])
            else:
                print(f"archive format {zip_path.suffix} needs 7-Zip; install 7-Zip or provide a zip asset")
                ok = False
        except Exception as exc:
            print(f"extract failed for {name}: {exc}")
            ok = False
    return ok


def install_models(model_dir: Path) -> bool:
    model_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, url in MODEL_REGISTRY.items():
        dest = model_dir / f"{name}.pth"
        if dest.exists():
            print(f"model {name}: ok")
            continue
        if not download_file(url, dest):
            ok = False
    return ok


def install_linux_macos() -> bool:
    system = platform.system().lower()
    if "linux" in system:
        for cmd in (
            ["sudo", "apt-get", "install", "-y", "ffmpeg", "vapoursynth"],
            ["sudo", "pacman", "-S", "--noconfirm", "ffmpeg", "vapoursynth"],
        ):
            if run(cmd) == 0:
                return True
    elif "darwin" in system:
        return run(["brew", "install", "ffmpeg", "vapoursynth"]) == 0
    return False


def write_report(project: Path, statuses: Dict[str, str]) -> None:
    report_json = project / "install_report.json"
    report_data = {
        "os": platform.platform(),
        "arch": platform.machine(),
        "policy": "latest-stable-os-compatible",
        **statuses,
    }
    report_json.write_text(json.dumps(report_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Install Report",
        "",
        f"- os: {platform.platform()}",
        "",
        "| component | status |",
        "| --- | --- |",
    ]
    for key, value in statuses.items():
        lines.append(f"| {key} | {value} |")
    lines.extend([
        "",
        f"- OS: {platform.platform()}",
        f"- Arch: {platform.machine()}",
        "- Policy: latest stable, compatible with current OS/architecture",
    ])
    report_md = project / "09_install_report.md"
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {report_json}")
    print(f"wrote: {report_md}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Auto-install post-processing dependencies.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--auto-install", action="store_true")
    parser.add_argument("--install-ffmpeg", action="store_true")
    parser.add_argument("--install-vapoursynth", action="store_true")
    parser.add_argument("--install-plugins", action="store_true")
    parser.add_argument("--install-models", action="store_true")
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project = args.project_dir
    project.mkdir(parents=True, exist_ok=True)
    model_dir = args.model_dir or (project / "models")
    do_all = args.auto_install or not any([args.install_ffmpeg, args.install_vapoursynth, args.install_plugins, args.install_models])
    statuses: Dict[str, str] = {
        "ffmpeg": "already" if tool_path("ffmpeg") and tool_path("ffprobe") else "pending",
        "vapoursynth": "already" if tool_path("vspipe") else "pending",
        "plugins": "pending",
        "models": "pending",
    }

    if args.dry_run:
        statuses = {key: "dry-run" for key in statuses}
        print("dry run: no system changes")
    else:
        system = platform.system().lower()
        if do_all or args.install_ffmpeg:
            if system == "windows":
                statuses["ffmpeg"] = "ok" if install_ffmpeg_windows() else "failed"
            else:
                statuses["ffmpeg"] = "ok" if install_linux_macos() else "failed"
        if do_all or args.install_vapoursynth:
            if system == "windows":
                statuses["vapoursynth"] = "ok" if install_vapoursynth_windows(project) else "failed"
            else:
                statuses["vapoursynth"] = "ok" if have_tool("vspipe") else "failed"
        if do_all or args.install_plugins:
            statuses["plugins"] = "ok" if install_plugins() else "failed"
        if do_all or args.install_models:
            statuses["models"] = "ok" if install_models(model_dir) else "failed"

    ffmpeg_path = tool_path("ffmpeg")
    vspipe_path = tool_path("vspipe")
    statuses["ffmpeg_path"] = ffmpeg_path or "unavailable"
    statuses["vspipe_path"] = vspipe_path or "unavailable"
    statuses["ffmpeg_version"] = tool_version(ffmpeg_path) if ffmpeg_path else "unavailable"
    statuses["vapoursynth_version"] = tool_version(vspipe_path) if vspipe_path else "unavailable"

    write_report(project, statuses)
    failed = [key for key, value in statuses.items() if value in ("failed", "pending")]
    if failed:
        print(f"failed or pending: {', '.join(failed)}")
        return 1
    print("auto install complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
