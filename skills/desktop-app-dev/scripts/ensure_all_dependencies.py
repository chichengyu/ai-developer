"""Unified dependency installer for the desktop-app-dev pipeline.

Checks and installs the web-fetch stack, the media runtime, and an
optional manifest-driven app dependency set in one pass. The default is
check-only; pass ``--install`` to download and install missing pieces.
Frozen PyInstaller EXEs refuse installs with a clear message because
their dependencies must be bundled at build time.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dependency_center import DependencyCenter
from ensure_web_fetch_dependencies import check_status as fetch_check_status
from ensure_web_fetch_dependencies import ensure as ensure_fetch_dependencies
from media_dependencies import check_status as media_check_status
from media_dependencies import install_dependencies


def status(manifest_path: str | Path | None = None) -> dict[str, Any]:
    """Return a combined check-only status for every dependency group."""
    fetch = fetch_check_status()
    media = media_check_status()
    manifest: dict[str, Any] | None = None
    if manifest_path:
        center = DependencyCenter(manifest_path)
        manifest = center.check_status()
    ready = bool(
        fetch.get("ready") and media.get("ready") and (manifest is None or manifest.get("ready"))
    )
    return {
        "web_fetch": fetch,
        "media": media,
        "manifest": manifest,
        "ready": ready,
    }


def ensure(
    install: bool = False,
    manifest_path: str | Path | None = None,
    runtime_dir: str | Path | None = None,
    ffmpeg_url: str | None = None,
) -> dict[str, Any]:
    """Install missing dependency groups when requested, then report status."""
    if install:
        if getattr(sys, "frozen", False):
            raise RuntimeError(
                "Dependencies are not bundled in this EXE. Rebuild with "
                "build_python.ps1 -InstallDeps or install through the dependency center."
            )
        ensure_fetch_dependencies(install=True)
        install_dependencies(
            install=True,
            runtime_dir=runtime_dir,
            ffmpeg_url=ffmpeg_url,
        )
        if manifest_path:
            DependencyCenter(manifest_path).install_all()
    return status(manifest_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or install all optional dependency groups.")
    parser.add_argument("--check", action="store_true", help="check only, no installs")
    parser.add_argument("--install", action="store_true", help="install missing dependencies")
    parser.add_argument("--manifest", default=None, help="optional dependencies.json manifest")
    parser.add_argument("--runtime-dir", default=None, help="media runtime directory")
    parser.add_argument("--ffmpeg-url", default=None, help="override ffmpeg zip URL")
    args = parser.parse_args(argv)
    result = ensure(
        install=args.install,
        manifest_path=args.manifest,
        runtime_dir=args.runtime_dir,
        ffmpeg_url=args.ffmpeg_url,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ready") or args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
