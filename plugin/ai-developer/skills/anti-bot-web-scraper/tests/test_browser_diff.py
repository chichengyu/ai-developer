"""Tests for dual-browser DOM/JS diff."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from browser_diff import diff_snapshots, find_injected_scripts, snapshot_page  # noqa: E402


def test_diff_snapshots_finds_injected_artifacts() -> None:
    baseline = {
        "html": '<script src="app.js"></script>',
        "scripts": ["app.js"],
        "global_functions": ["fetch"],
        "storage": {"local": {"a": "1"}},
    }
    target = {
        "html": '<script src="app.js"></script><script src="sensor.js"></script>',
        "scripts": ["app.js", "sensor.js"],
        "global_functions": ["fetch", "genSign"],
        "storage": {"local": {"a": "1", "fp": "x"}},
    }
    report = diff_snapshots(baseline, target)
    assert "sensor.js" in report["added_scripts"]
    assert "genSign" in report["added_functions"]
    assert "fp" in report["added_storage"]
    assert find_injected_scripts(baseline, target) == ["sensor.js"]


def test_snapshot_page_returns_non_fatal_without_session() -> None:
    report = snapshot_page(None)
    assert report["ok"] is False
