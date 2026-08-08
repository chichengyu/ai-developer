"""Runtime dependency manager for the media acquisition pipeline.

Checks and installs:
- Python packages: playwright, pycryptodome, pillow, pytesseract (OCR)
- Chromium browser via `playwright install chromium`
- Portable ffmpeg / ffprobe for Windows

Default mode is check-only. Pass `--install` (or call
`install_dependencies(install=True)`) to actually download and install.
The desktop UI should run this on a worker thread and forward progress
events to the UI.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

ProgressFn = Callable[[str, float | None, str], None]

DEFAULT_RUNTIME_DIR = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MediaPipelineRuntime"
)
FFMPEG_WINDOWS_URL = os.environ.get(
    "FFMPEG_DOWNLOAD_URL",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
)
PYTHON_PACKAGES = ["playwright", "pycryptodome", "pillow", "pytesseract"]


def _noop_progress(stage: str, percent: float | None, message: str) -> None:
    print(f"[{stage}] {percent or 0:.0%} {message}")


def check_status(runtime_dir: str | Path | None = None) -> dict:
    runtime = Path(runtime_dir) if runtime_dir else DEFAULT_RUNTIME_DIR
    bin_dir = runtime / "bin"
    ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    ffprobe_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    ffmpeg = bool(shutil.which("ffmpeg") or (bin_dir / ffmpeg_name).exists())
    ffprobe = bool(shutil.which("ffprobe") or (bin_dir / ffprobe_name).exists())
    playwright_installed = importlib.util.find_spec("playwright") is not None
    pycryptodome_installed = importlib.util.find_spec("Crypto") is not None
    ocr_installed = (
        importlib.util.find_spec("PIL") is not None
        and importlib.util.find_spec("pytesseract") is not None
        and bool(shutil.which("tesseract"))
    )
    chromium_browser = _chromium_browser_path().exists()
    return {
        "playwright": playwright_installed,
        "pycryptodome": pycryptodome_installed,
        "ocr": ocr_installed,
        "chromium": playwright_installed and chromium_browser,
        "ffmpeg": bool(ffmpeg),
        "ffprobe": bool(ffprobe),
        "runtime_dir": str(runtime),
        "ready": bool(
            playwright_installed
            and pycryptodome_installed
            and chromium_browser
            and ffmpeg
            and ffprobe
        ),
    }


def _chromium_browser_path() -> Path:
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override:
        root = Path(override)
    else:
        candidates: list[Path] = []
        if sys.platform == "win32":
            local = os.environ.get("LOCALAPPDATA")
            if local:
                candidates.append(Path(local) / "ms-playwright")
        elif sys.platform == "darwin":
            candidates.append(Path.home() / "Library" / "Caches" / "ms-playwright")
        else:
            candidates.append(Path.home() / ".cache" / "ms-playwright")
        candidates.append(Path.home() / "ms-playwright")
        root = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
    candidates = sorted(root.glob("chromium-*"), key=lambda p: p.name, reverse=True)
    return candidates[0] if candidates else root


def install_dependencies(
    progress: ProgressFn | None = None,
    install: bool = False,
    runtime_dir: str | Path | None = None,
    ffmpeg_url: str | None = None,
) -> dict:
    """Install missing runtime pieces, or only report status."""
    report = progress or _noop_progress
    if not install:
        return check_status(runtime_dir)

    runtime = Path(runtime_dir) if runtime_dir else DEFAULT_RUNTIME_DIR
    runtime.mkdir(parents=True, exist_ok=True)
    report("packages", 0.1, "installing playwright + pycryptodome + OCR packages")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", *PYTHON_PACKAGES],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pip install failed: {result.stderr[-500:]}")

    report("chromium", 0.4, "downloading chromium via playwright")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"playwright install failed: {result.stderr[-500:]}")

    status = check_status(runtime)
    if not status["ffmpeg"] or not status["ffprobe"]:
        if sys.platform == "win32":
            report("ffmpeg", 0.7, "downloading portable ffmpeg")
            _install_ffmpeg_windows(runtime, report, ffmpeg_url or FFMPEG_WINDOWS_URL)
        else:
            raise RuntimeError(
                "ffmpeg not found; install it with your package manager "
                "(apt install ffmpeg / brew install ffmpeg / choco install ffmpeg)"
            )

    _write_manifest(runtime, check_status(runtime))
    report("done", 1.0, "media runtime ready")
    return check_status(runtime)


def _zip_member_is_safe(member_name: str) -> bool:
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        return False
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    return bool(parts) and all(part != ".." for part in parts)


def _install_ffmpeg_windows(
    runtime: Path,
    progress: ProgressFn,
    url: str,
) -> None:
    zip_path = runtime / "ffmpeg.zip"
    extract_dir = runtime / "ffmpeg-src"
    bin_dir = runtime / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(url, headers={"User-Agent": "MediaPipeline/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, zip_path.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            percent = (downloaded / total) if total else None
            progress("ffmpeg", percent, f"downloaded {downloaded:,} bytes")

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if not _zip_member_is_safe(member.filename):
                raise RuntimeError(f"unsafe path in ffmpeg archive: {member.filename}")
        archive.extractall(extract_dir)
    zip_path.unlink()

    copied: list[str] = []
    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        source = next(extract_dir.rglob(exe), None)
        if source is None:
            raise RuntimeError(f"{exe} not found in ffmpeg archive")
        target = bin_dir / exe
        shutil.copy2(source, target)
        copied.append(str(target))
    shutil.rmtree(extract_dir)
    progress("ffmpeg", 1.0, "ffmpeg ready: " + ", ".join(copied))


def _write_manifest(runtime: Path, status: dict) -> None:
    manifest = runtime / "manifest.json"
    manifest.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check or install media pipeline runtime dependencies"
    )
    parser.add_argument("--check-only", action="store_true", help="default: no install")
    parser.add_argument("--install", action="store_true", help="install missing pieces")
    parser.add_argument("--runtime-dir", default=None, help="override runtime dir")
    parser.add_argument("--ffmpeg-url", default=None, help="override ffmpeg zip URL")
    args = parser.parse_args(argv)
    if args.install:
        result = install_dependencies(
            progress=_noop_progress,
            install=True,
            runtime_dir=args.runtime_dir,
            ffmpeg_url=args.ffmpeg_url,
        )
    else:
        result = check_status(args.runtime_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ready") or not args.install else 1


if __name__ == "__main__":
    raise SystemExit(main())
