"""Tests for CDP breakpoint-level reverse probing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from browser_session import BrowserSession  # noqa: E402
from cdp_probe import build_breakpoints_from_analysis, build_paused_record  # noqa: E402


def _fake_analysis() -> object:
    return type(
        "A",
        (),
        {
            "signature_candidates": [
                type("C", (), {"name": "genSign", "line": 12, "confidence": 0.9})()
            ],
            "request_sites": [
                type("S", (), {"line": 20, "method": "GET", "url": "/api"})()
            ],
        },
    )()


def test_build_breakpoints_from_analysis() -> None:
    breakpoints = build_breakpoints_from_analysis(_fake_analysis(), "bundle.js")
    assert any(item["function"] == "genSign" and item["line"] == 12 for item in breakpoints)
    assert any(item["reason"] == "request_site" for item in breakpoints)


def test_build_paused_record() -> None:
    record = build_paused_record(
        {
            "callFrames": [
                {
                    "functionName": "genSign",
                    "location": {"url": "bundle.js", "lineNumber": 11, "columnNumber": 2},
                    "callFrameId": "frame-1",
                }
            ]
        },
        evaluate=lambda _frame_id: {"args": ["x"]},
    )
    assert record["functionName"] == "genSign"
    assert record["line"] == 12
    assert record["evaluation"] == {"args": ["x"]}


def test_browser_session_cdp_method_returns_capture() -> None:
    class FakeCdp:
        def send(self, _method: str, _params: dict | None = None) -> dict:
            return {}

        def on(self, _event: str, _handler: object) -> None:
            pass

    class FakeContext:
        def new_cdp_session(self, _page: object) -> FakeCdp:
            return FakeCdp()

    class FakePage:
        def reload(self, **_kwargs: object) -> None:
            pass

    session = BrowserSession(headless=True)
    session.context = FakeContext()
    session.page = FakePage()
    result = session.capture_cdp_function_calls(
        [{"url": "bundle.js", "line": 12, "column": 0}],
        reload=False,
        wait_ms=0,
    )
    assert result["ok"] is True


def test_browser_session_cdp_return_probe_returns_capture() -> None:
    class FakeCdp:
        def send(self, _method: str, _params: dict | None = None) -> dict:
            return {}

        def on(self, _event: str, _handler: object) -> None:
            pass

    class FakeContext:
        def new_cdp_session(self, _page: object) -> FakeCdp:
            return FakeCdp()

    class FakePage:
        def reload(self, **_kwargs: object) -> None:
            pass

    session = BrowserSession(headless=True)
    session.context = FakeContext()
    session.page = FakePage()
    result = session.capture_cdp_return_calls(
        [{"url": "bundle.js", "line": 12, "column": 0}],
        reload=False,
        wait_ms=0,
    )
    assert result["ok"] is True
