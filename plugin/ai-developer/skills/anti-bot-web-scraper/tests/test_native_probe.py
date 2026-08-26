"""Tests for browser native-API probes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from browser_session import BrowserSession  # noqa: E402
from native_probe import native_probe_js, parse_native_probes  # noqa: E402


def test_native_probe_js_wraps_high_value_apis() -> None:
    js = native_probe_js("__native_test")
    assert "__native_test" in js
    assert "Date.now" in js
    assert "crypto.subtle.digest" in js
    assert "TextEncoder.encode" in js
    assert "localStorage.setItem" in js
    assert "WebAssembly.Memory" in js


def test_parse_native_probes_counts_unique_apis() -> None:
    report = parse_native_probes(
        {
            "native_calls": [
                {"name": "Date.now"},
                {"name": "Date.now"},
                {"name": "crypto.subtle.digest"},
            ]
        }
    )
    assert report["summary"]["native_calls"] == 3
    assert report["summary"]["unique_apis"] == 2


def test_browser_session_installs_native_probe() -> None:
    class FakeContext:
        def __init__(self) -> None:
            self.scripts: list[str] = []

        def add_init_script(self, script: str) -> None:
            self.scripts.append(script)

    session = BrowserSession(headless=True, native_probe=True)
    session.deep_hook = True
    session.context = FakeContext()
    session._install_deep_hook()
    assert any("__deep_native_probe" in script for script in session.context.scripts)
    assert any("native_calls" in script for script in session.context.scripts)
