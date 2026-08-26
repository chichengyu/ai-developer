"""Tests for cross-chunk interprocedural taint."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bundle_taint import analyze_interprocedural_flow  # noqa: E402
from deep_reverse import analyze_script_bundle  # noqa: E402


def test_interprocedural_flow_propagates_across_scripts() -> None:
    sources = [
        {
            "name": "a.js",
            "content": "function genSign(x){return md5(x)} var ua=navigator.userAgent;",
        },
        {
            "name": "b.js",
            "content": "var sig=genSign(ua); fetch('/api?device='+ua,{headers:{'X-Token':sig}});",
        },
    ]
    report = analyze_interprocedural_flow(sources)
    assert report["ok"] is True
    assert report["summary"]["cross_refs"] >= 1
    assert report["summary"]["edges"] >= 1


def test_analyze_script_bundle_includes_interprocedural_flow() -> None:
    sources = [
        {"name": "a.js", "content": "function sign(x){return md5(x)}"},
        {"name": "b.js", "content": "fetch('/api?sign='+sign('a'))"},
    ]
    report = analyze_script_bundle(sources)
    assert "interprocedural_flow" in report
    assert report["interprocedural_flow"]["ok"] is True
