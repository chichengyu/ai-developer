"""Tests for the one-command deep reverse pipeline wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from deep_reverse_auto import main, run_auto  # noqa: E402


def _sample_capture() -> dict:
    return {
        "url": "https://example.com/",
        "html": (
            "<script>function sign(x){return md5(x)}"
            'fetch("/api?sign="+sign("a"),{headers:{"X-Token":"tok"}})</script>'
        ),
        "network": [],
    }


def test_run_auto_combines_static_and_lab_reports() -> None:
    capture = _sample_capture()
    report = run_auto(
        [capture],
        js="function sign(x){return x}",
        js_url="bundle.js",
    )
    assert report["summary"]["captures"] == 1
    assert report["deep_reverse"]["analysis"]["request_sites"]
    assert report["js_analysis"]["url"] == "bundle.js"
    assert "reverse_lab" in report
    assert "summary" in report


def test_run_auto_does_not_mutate_input_capture() -> None:
    capture = _sample_capture()
    before = str(capture)
    run_auto([capture])
    assert str(capture) == before


def test_main_self_test() -> None:
    assert main(["--self-test"]) == 0
