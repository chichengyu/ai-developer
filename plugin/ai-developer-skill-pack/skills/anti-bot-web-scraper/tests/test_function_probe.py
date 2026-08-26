"""Tests for browser function-level call tracing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from browser_session import BrowserSession  # noqa: E402
from function_probe import function_probe_js, parse_function_probes  # noqa: E402
from web_data_pipeline import WebDataPipeline  # noqa: E402


def test_function_probe_js_contains_patterns_and_global() -> None:
    js = function_probe_js(["genSign", "device"], "__probe_test")
    assert "__probe_test" in js
    assert "genSign" in js
    assert "device" in js
    assert "function_calls" in js
    assert "rescan" in js


def test_parse_function_probes_counts_calls() -> None:
    report = parse_function_probes(
        {
            "function_calls": [
                {"name": "genSign", "result": "abc", "error": None},
                {"name": "deviceId", "error": "boom"},
            ]
        }
    )
    assert report["summary"]["function_calls"] == 2
    assert report["summary"]["matched"] == 1
    assert report["summary"]["failed"] == 1


def test_browser_session_installs_function_probe_when_configured() -> None:
    class FakeContext:
        def __init__(self) -> None:
            self.scripts: list[str] = []

        def add_init_script(self, script: str) -> None:
            self.scripts.append(script)

    session = BrowserSession(headless=True, function_probe_patterns=["genSign"])
    session.deep_hook = True
    session.context = FakeContext()
    session._install_deep_hook()
    assert len(session.context.scripts) == 2
    assert "__deep_reverse_hook" in session.context.scripts[0]
    assert "__deep_function_probe" in session.context.scripts[1]
    assert "genSign" in session.context.scripts[1]


def test_capture_function_probes_reads_hook() -> None:
    class FakePage:
        def evaluate(self, script: str) -> dict[str, object]:
            if "rescan" in script:
                return 0
            return {
                "function_calls": [
                    {"name": "genSign", "args": ["a"], "result": "sig", "error": None}
                ]
            }

    session = BrowserSession(headless=True, function_probe_patterns=["genSign"])
    session.page = FakePage()
    hook = session.capture_function_probes()
    assert len(hook["function_calls"]) == 1
    assert hook["function_calls"][0]["name"] == "genSign"


def test_pipeline_reads_function_probe_patterns_from_reverse_config() -> None:
    pipeline = WebDataPipeline(
        {
            "reverse": {
                "function_probe_patterns": "genSign,deviceId",
            }
        }
    )
    assert pipeline._function_probe_patterns() == ["genSign", "deviceId"]
