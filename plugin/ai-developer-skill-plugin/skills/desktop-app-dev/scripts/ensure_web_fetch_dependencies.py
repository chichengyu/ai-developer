"""Ensure optional web-fetch dependencies for the adaptive fetch stack.

`smart_fetch.py` uses these packages when they are installed:

- `curl_cffi` -- browser TLS/JA3/JA4 + HTTP/2 impersonation
- `cloudscraper` -- Cloudflare JS challenge / Turnstile solving
- `httpx` -- HTTP/2 client
- `h2` -- HTTP/2 protocol support used by httpx
- `patchright` -- undetected Playwright
- `nodriver` -- CDP-only Chromium automation
- `DrissionPage` -- Chromium automation with a self-developed core

The CLI defaults to automatic mode: it checks for missing packages and
installs them with pip. Use `--check` to only report status without
downloading anything, or `--http-only` to skip the stealth-browser packages.
This script deliberately does not install Playwright's Chromium or ffmpeg;
use `media_dependencies.py --install` for those.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

WEB_FETCH_PACKAGES = ("curl_cffi", "cloudscraper", "httpx", "h2")
STEALTH_BROWSER_PACKAGES = ("patchright", "nodriver", "DrissionPage")
ALL_WEB_FETCH_PACKAGES = (*WEB_FETCH_PACKAGES, *STEALTH_BROWSER_PACKAGES)
WEB_FETCH_LABELS = {
    "curl_cffi": "browser TLS/JA3/JA4 + HTTP/2 impersonation",
    "cloudscraper": "Cloudflare JS challenge / Turnstile solving",
    "httpx": "HTTP/2 client",
    "h2": "HTTP/2 protocol support",
    "patchright": "undetected Playwright (drop-in sync API)",
    "nodriver": "CDP-only Chromium automation, no WebDriver",
    "DrissionPage": "Chromium automation with a self-developed core",
}
ProgressFn = Callable[[str, float | None, str], None]


class DependencyInstallError(RuntimeError):
    """Raised when pip cannot install a required web-fetch package."""


def _noop_progress(stage: str, percent: float | None, message: str) -> None:
    print(f"[{stage}] {percent or 0:.0%} {message}")


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def check_status() -> dict[str, Any]:
    """Return installed status for every optional web-fetch package."""
    return {
        "python": sys.executable,
        "packages": [
            {
                "name": name,
                "installed": _module_available(name),
                "description": WEB_FETCH_LABELS[name],
            }
            for name in ALL_WEB_FETCH_PACKAGES
        ],
        "ready": all(_module_available(name) for name in ALL_WEB_FETCH_PACKAGES),
    }


def missing_packages() -> list[str]:
    """Return the subset of web-fetch packages that are not installed."""
    return [name for name in ALL_WEB_FETCH_PACKAGES if not _module_available(name)]


def ensure(
    install: bool = True,
    progress: ProgressFn | None = None,
    packages: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Ensure the web-fetch stack is available, installing when requested."""
    report = progress or _noop_progress
    wanted = tuple(packages) if packages else ALL_WEB_FETCH_PACKAGES
    missing = [name for name in wanted if not _module_available(name)]
    if not missing:
        return check_status()
    if not install:
        return check_status()
    if getattr(sys, "frozen", False):
        raise DependencyInstallError(
            f"{', '.join(missing)} is not bundled in this EXE. Rebuild with "
            "build_python.ps1 -InstallDeps or install through the dependency center."
        )

    report(
        "ensure",
        0.1,
        f"installing missing web-fetch packages: {', '.join(missing)}",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", *missing],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DependencyInstallError(
            f"pip install failed for {', '.join(missing)}: {result.stderr[-500:]}"
        )
    status = check_status()
    report("done", 1.0, "web-fetch dependencies ready")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check or auto-install web-fetch dependencies " "(default: install missing packages)"
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="only report status; do not download anything",
    )
    parser.add_argument(
        "--packages",
        default=None,
        help="comma-separated package subset, e.g. curl_cffi,cloudscraper",
    )
    parser.add_argument(
        "--http-only",
        action="store_true",
        help="only check/install HTTP backends, skip stealth browser packages",
    )
    args = parser.parse_args(argv)
    packages = (
        [item.strip() for item in args.packages.split(",") if item.strip()]
        if args.packages
        else None
    )
    if args.http_only and packages is None:
        packages = list(WEB_FETCH_PACKAGES)
    result = ensure(install=not args.check, packages=packages)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ready") or args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
