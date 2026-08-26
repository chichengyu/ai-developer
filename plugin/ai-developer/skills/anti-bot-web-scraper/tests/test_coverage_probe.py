"""Tests for CDP coverage-guided candidate filtering."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from browser_session import BrowserSession  # noqa: E402
from coverage_probe import CoverageCapture, filter_candidates_by_coverage  # noqa: E402


def test_filter_candidates_by_coverage() -> None:
    analysis = {
        "signature_candidates": [
            {"name": "genSign", "line": 12},
            {"name": "unused", "line": 99},
        ]
    }
    coverage = CoverageCapture(
        ok=True,
        scripts=[
            {
                "url": "https://example.com/bundle.js",
                "functions": [
                    {
                        "functionName": "genSign",
                        "ranges": [{"startOffset": 0, "endOffset": 100, "count": 2}],
                    }
                ],
            }
        ],
    )
    kept = filter_candidates_by_coverage(analysis, coverage)
    assert kept and kept[0]["name"] == "genSign"
    assert kept[0]["covered"] is True


def test_browser_session_coverage_method_returns_capture() -> None:
    class FakeCdp:
        def send(self, _method: str, _params: dict | None = None) -> dict:
            if _method == "Profiler.takePreciseCoverage":
                return {"result": []}
            return {}

    class FakeContext:
        def new_cdp_session(self, _page: object) -> FakeCdp:
            return FakeCdp()

    class FakePage:
        def reload(self, **_kwargs: object) -> None:
            pass

        def wait_for_load_state(self, **_kwargs: object) -> None:
            pass

    session = BrowserSession(headless=True)
    session.context = FakeContext()
    session.page = FakePage()
    result = session.capture_cdp_coverage(wait_ms=0)
    assert result["ok"] is True
