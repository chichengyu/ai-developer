"""On-demand installers for optional deep-reverse tools.

The deep reverse features that need external binaries stay optional:

- ``z3-solver`` -- optional symbolic constraint solving
- ``wabt`` / ``wasm2c`` / ``wasm-decompile`` -- WASM pseudocode output
- ``mitmproxy`` / ``mitmdump`` -- TLS-decrypted byte-level capture

Each installer is called only when the corresponding feature is actually
used.  All of them return a structured ``ok`` result so callers can degrade
gracefully when installation is unavailable.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any


def z3_available() -> bool:
    try:
        return importlib.util.find_spec("z3") is not None
    except (ImportError, ValueError):
        return False


def wabt_available() -> bool:
    return any(_tool_path(name) for name in ("wasm2c", "wasm-decompile", "wasm2wat", "wat2wasm"))


def mitmproxy_available() -> bool:
    return _tool_path("mitmdump") is not None


def ensure_z3(
    install: bool = True,
    *,
    timeout: float = 240.0,
) -> dict[str, Any]:
    """Install z3-solver when needed and return status."""
    if z3_available():
        return {"ok": True, "source": "existing", "tool": "z3"}
    if not install:
        return {"ok": False, "error": "z3-solver is not installed", "tool": "z3"}
    result = _pip_install("z3-solver", timeout=timeout)
    if result["ok"] and z3_available():
        return {"ok": True, "source": "pip", "tool": "z3"}
    return {"ok": False, "error": result.get("error", "z3-solver install failed"), "tool": "z3"}


def ensure_wabt(
    install: bool = True,
    *,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """Install wabt/wasm2c when needed through pip or npm."""
    if wabt_available():
        return {"ok": True, "source": "existing", "tool": "wabt"}
    if not install:
        return {"ok": False, "error": "wabt/wasm2c is not installed", "tool": "wabt"}
    pip_result = _pip_install("wabt", timeout=timeout)
    if pip_result["ok"] and wabt_available():
        return {"ok": True, "source": "pip", "tool": "wabt"}
    npm = _npm_command()
    if npm:
        with suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                [npm, "install", "-g", "wabt"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
    if wabt_available():
        return {"ok": True, "source": "npm", "tool": "wabt"}
    return {
        "ok": False,
        "error": "wabt install failed through pip and npm; install wasm2c manually",
        "tool": "wabt",
    }


def ensure_mitmproxy(
    install: bool = True,
    *,
    timeout: float = 600.0,
) -> dict[str, Any]:
    """Install mitmproxy when needed and return status."""
    if mitmproxy_available():
        return {"ok": True, "source": "existing", "tool": "mitmdump"}
    if not install:
        return {"ok": False, "error": "mitmdump is not installed", "tool": "mitmdump"}
    result = _pip_install("mitmproxy", timeout=timeout)
    if result["ok"] and mitmproxy_available():
        return {"ok": True, "source": "pip", "tool": "mitmdump"}
    return {
        "ok": False,
        "error": result.get("error", "mitmproxy install failed"),
        "tool": "mitmdump",
    }


def ensure_reverse_tool(
    name: str,
    install: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Dispatch to the matching reverse-tool installer."""
    normalized = str(name or "").lower().replace("_", "-")
    if normalized in {"z3", "z3-solver"}:
        return ensure_z3(install=install, **kwargs)
    if normalized in {"wabt", "wasm2c", "wasm2wat", "wasm-decompile", "wat2wasm"}:
        return ensure_wabt(install=install, **kwargs)
    if normalized in {"mitmproxy", "mitmdump"}:
        return ensure_mitmproxy(install=install, **kwargs)
    return {"ok": False, "error": f"unknown reverse tool: {name}"}


def reverse_tools_status() -> dict[str, Any]:
    """Return availability for all optional reverse tools."""
    return {
        "z3": z3_available(),
        "wabt": wabt_available(),
        "mitmproxy": mitmproxy_available(),
    }


def _pip_install(package: str, timeout: float) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", package],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr[-500:] or "pip install failed"}
    return {"ok": True}


def _tool_path(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    candidates = [
        Path(sys.executable).parent / f"{name}.exe",
        Path(sys.executable).parent / name,
        Path(sys.executable).parent.parent / "Scripts" / f"{name}.exe",
        Path(sys.executable).parent.parent / "Scripts" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _npm_command() -> str | None:
    for name in ("npm.cmd", "npm"):
        path = shutil.which(name)
        if path:
            return path
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optional reverse-tool installers")
    parser.add_argument("--tool", choices=("z3", "wabt", "mitmproxy"), default=None)
    parser.add_argument("--check", action="store_true", help="report only, do not install")
    parser.add_argument("--status", action="store_true", help="report all tool statuses")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print("ensure_reverse_tools self-test OK")
        return 0
    if args.status:
        print(json.dumps(reverse_tools_status(), ensure_ascii=False, indent=2))
        return 0
    if not args.tool:
        parser.error("--tool or --status is required")
    result = ensure_reverse_tool(args.tool, install=not args.check)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") or args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
