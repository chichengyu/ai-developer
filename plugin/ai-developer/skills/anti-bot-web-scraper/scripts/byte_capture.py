"""Network byte-level request reconstruction and replay comparison.

Static analysis and browser hooks see logical requests.  This module rebuilds
the exact HTTP/1.1 bytes that would be sent on the wire and compares them to a
replayed signature request.  It also exposes an optional mitmproxy hook for
real TLS-decrypted byte capture when ``mitmdump`` is installed.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def build_request_bytes(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: bytes | str | None = None,
) -> bytes:
    """Build raw HTTP/1.1 request bytes for a logical request."""
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    body_bytes = body.encode("utf-8") if isinstance(body, str) else body or b""
    header_items = dict(headers or {})
    header_items.setdefault("Host", parsed.netloc.split("@")[-1])
    if body_bytes and "Content-Length" not in {key.lower() for key in header_items}:
        header_items["Content-Length"] = str(len(body_bytes))
    lines = [f"{method.upper()} {path} HTTP/1.1"]
    for key, value in header_items.items():
        lines.append(f"{key}: {value}")
    return "\r\n".join(lines).encode("latin-1", "replace") + b"\r\n\r\n" + body_bytes


def capture_request_bytes(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: bytes | str | None = None,
) -> dict[str, Any]:
    """Return a byte-level fingerprint for one logical request."""
    raw = build_request_bytes(method, url, headers, body)
    return {
        "ok": True,
        "method": method.upper(),
        "url": url,
        "headers": headers or {},
        "body_size": len(body) if isinstance(body, bytes | str) else 0,
        "request_bytes": raw.decode("latin-1", "replace"),
        "length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def compare_replay_bytes(
    captured: bytes | dict[str, Any],
    replay: bytes | dict[str, Any],
) -> dict[str, Any]:
    """Compare captured and replayed raw request bytes."""
    if isinstance(captured, dict):
        captured = str(captured.get("request_bytes", "") or "").encode("latin-1", "replace")
    if isinstance(replay, dict):
        replay = str(replay.get("request_bytes", "") or "").encode("latin-1", "replace")
    captured = bytes(captured)
    replay = bytes(replay)
    first_diff = next(
        (index for index in range(min(len(captured), len(replay))) if captured[index] != replay[index]),
        None,
    )
    return {
        "ok": True,
        "equal": captured == replay,
        "first_diff": first_diff,
        "captured_length": len(captured),
        "replay_length": len(replay),
        "captured_sha256": hashlib.sha256(captured).hexdigest(),
        "replay_sha256": hashlib.sha256(replay).hexdigest(),
    }


def capture_with_mitmproxy(
    url: str,
    *,
    script: str | None = None,
    output: str = "mitm.log",
    timeout: float = 30.0,
    auto_install: bool = True,
) -> dict[str, Any]:
    """Run mitmdump against a URL when installed (TLS-decrypted capture)."""
    mitmdump = _find_mitmdump()
    if not mitmdump:
        if auto_install:
            from ensure_reverse_tools import ensure_mitmproxy

            ensure_mitmproxy(install=True, timeout=timeout)
            mitmdump = _find_mitmdump()
        if not mitmdump:
            return {"ok": False, "error": "mitmdump is not installed"}
    args = [mitmdump, "-q", "-w", output]
    if script:
        args.extend(["-s", script])
    args.append(url)
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stderr": (proc.stderr or "")[-2000:],
        "output": output,
    }


def _find_mitmdump() -> str | None:
    found = shutil.which("mitmdump")
    if found:
        return found
    candidates = [
        Path(sys.executable).parent / "mitmdump.exe",
        Path(sys.executable).parent / "mitmdump",
        Path(sys.executable).parent.parent / "Scripts" / "mitmdump.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _self_test() -> None:
    captured = capture_request_bytes("GET", "https://example.com/api?a=1", {"X-Token": "x"})
    replay = capture_request_bytes("GET", "https://example.com/api?a=1", {"X-Token": "x"})
    assert captured["sha256"] == replay["sha256"]
    diff = compare_replay_bytes(captured, replay)
    assert diff["equal"] is True
    print("byte_capture self-test OK")


if __name__ == "__main__":
    _self_test()
