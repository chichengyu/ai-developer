"""Lazy-load and auto-install optional Python dependencies.

Desktop apps should not import optional heavy modules at startup. This
helper checks a module only when a feature needs it, then installs it into
an app-local directory in source mode. Frozen (PyInstaller) EXEs must
bundle optional dependencies at build time; the helper detects that case
instead of trying to run pip on the recipient's machine.

Usage:
    status = check_python_dependency("openpyxl", target_dir=target)
    ensure_python_dependency(
        "openpyxl",
        target_dir=target,
        progress=lambda stage, percent, message: print(stage, percent, message),
        cancel=lambda: False,
    )
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class DependencyError(RuntimeError):
    """Raised when an optional Python dependency cannot be loaded."""


def default_target_dir(app_name: str = "DesktopApp") -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return base / app_name / "runtime" / "py-deps"


def _find_target_path(name: str, target_dir: Path | None) -> Path | None:
    if target_dir is None:
        return None
    candidates = (
        target_dir / name,
        target_dir / f"{name}.py",
        target_dir / (name.replace("-", "_")),
        target_dir / (name.replace("-", "_") + ".py"),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if target_dir.exists():
        matches = list(target_dir.glob(f"{name.replace('-', '_')}-*.dist-info"))
        if matches:
            return matches[0]
    return None


def check_python_dependency(
    name: str,
    target_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Return dependency status without importing or installing anything."""
    spec = importlib.util.find_spec(name)
    if spec is not None and spec.origin is not None:
        return {
            "name": name,
            "installed": True,
            "source": "site-packages",
            "path": str(spec.origin),
        }
    target = Path(target_dir) if target_dir else None
    found = _find_target_path(name, target)
    if found is not None:
        return {
            "name": name,
            "installed": True,
            "source": "app-local",
            "path": str(found),
        }
    return {
        "name": name,
        "installed": False,
        "source": "missing",
        "path": str(target or ""),
    }


def install_python_dependency(
    name: str,
    target_dir: str | Path,
    progress: Callable[[str, float | None, str], None] | None = None,
    cancel: Callable[[], bool] | None = None,
    timeout_seconds: float = 900.0,
) -> dict[str, Any]:
    """Install a package into target_dir and return its new status."""
    target = Path(target_dir)
    status = check_python_dependency(name, target)
    if status["installed"]:
        if progress:
            progress(name, 1.0, f"{name} already available ({status['source']})")
        return status

    if getattr(sys, "frozen", False):
        raise DependencyError(
            f"{name} is not bundled in this EXE. Rebuild with "
            "build_python.ps1 -InstallDeps after adding it to requirements.txt."
        )

    target.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--target",
        str(target),
        name,
    ]
    if progress:
        progress(name, 0.1, f"installing {name} into {target}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    lines: list[str] = []
    deadline = time.monotonic() + timeout_seconds
    assert process.stdout is not None
    while True:
        if cancel and cancel():
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            raise DependencyError(f"{name} install cancelled")
        line = process.stdout.readline()
        if line:
            lines.append(line.rstrip())
            if progress:
                progress(name, None, line.rstrip())
            continue
        if process.poll() is not None:
            break
        if time.monotonic() >= deadline:
            process.kill()
            raise DependencyError(f"{name} install timed out")
        time.sleep(0.05)

    if process.returncode != 0:
        tail = "\n".join(lines[-8:])
        raise DependencyError(f"pip install {name} failed:\n{tail}")
    status = check_python_dependency(name, target)
    if not status["installed"]:
        raise DependencyError(f"pip install {name} completed but the module is missing")
    if progress:
        progress(name, 1.0, f"{name} ready ({status['source']})")
    return status


def ensure_python_dependency(
    name: str,
    target_dir: str | Path,
    progress: Callable[[str, float | None, str], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Check first, install only when the calling feature needs the module."""
    status = check_python_dependency(name, target_dir)
    if status["installed"]:
        return status
    return install_python_dependency(name, target_dir, progress=progress, cancel=cancel)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lazy Python dependency manager")
    parser.add_argument("name")
    parser.add_argument("--target-dir", default=None)
    parser.add_argument("--check", action="store_true", help="check only, no install")
    parser.add_argument("--app-name", default="DesktopApp")
    args = parser.parse_args(argv)
    target = Path(args.target_dir) if args.target_dir else default_target_dir(args.app_name)
    if args.check:
        status = check_python_dependency(args.name, target)
    else:
        status = ensure_python_dependency(
            args.name,
            target,
            progress=lambda stage, percent, message: print(
                f"[{stage}] {percent or 0:.0%} {message}"
            ),
        )
    print(status)
    return 0 if status["installed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
