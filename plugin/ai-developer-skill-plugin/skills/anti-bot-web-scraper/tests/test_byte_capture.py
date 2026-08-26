"""Tests for byte-level request reconstruction and comparison."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from byte_capture import (  # noqa: E402
    build_request_bytes,
    capture_request_bytes,
    capture_with_mitmproxy,
    compare_replay_bytes,
)


def test_build_request_bytes_contains_headers_and_body() -> None:
    raw = build_request_bytes(
        "POST",
        "https://example.com/api?a=1",
        {"X-Token": "abc"},
        b"body",
    )
    assert raw.startswith(b"POST /api?a=1 HTTP/1.1")
    assert b"X-Token: abc" in raw
    assert raw.endswith(b"body")


def test_capture_and_compare_equal_requests() -> None:
    captured = capture_request_bytes("GET", "https://example.com/api?a=1")
    replay = capture_request_bytes("GET", "https://example.com/api?a=1")
    assert captured["sha256"] == replay["sha256"]
    assert compare_replay_bytes(captured, replay)["equal"] is True


def test_compare_detects_diff() -> None:
    captured = build_request_bytes("GET", "https://example.com/api?a=1")
    replay = build_request_bytes("GET", "https://example.com/api?a=2")
    diff = compare_replay_bytes(captured, replay)
    assert diff["equal"] is False
    assert diff["first_diff"] is not None


def test_mitmproxy_reports_unavailable_tool() -> None:
    result = capture_with_mitmproxy("https://example.com/", auto_install=False)
    if result.get("ok"):
        return
    assert "mitmdump" in result.get("error", "")
