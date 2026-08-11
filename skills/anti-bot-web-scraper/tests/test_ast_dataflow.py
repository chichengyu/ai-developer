"""Tests for AST-based data-flow tracing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ast_dataflow import analyze_ast_data_flow, build_ast_data_flow  # noqa: E402
from deep_reverse import acorn_available, analyze_js  # noqa: E402


def test_build_ast_data_flow_uses_acorn_flow_rows() -> None:
    analysis = analyze_js("function sign(x){return x} fetch('/api?ts=1');")
    flow = [
        {"kind": "variable", "name": "ts", "init": "Date.now()", "line": 1},
        {"kind": "call", "callee": "fetch", "args": "'/api?ts=' + ts", "line": 2},
    ]
    report = build_ast_data_flow(flow, analysis)
    assert report["ok"] is True
    assert any(
        edge["source_kind"] == "Date.now()" and edge["target"] == "ts"
        for edge in report["edges"]
    )


def test_analyze_ast_data_flow_returns_non_fatal_without_acorn() -> None:
    analysis = analyze_js("var a = 1;")
    report = analyze_ast_data_flow("var a = 1;", analysis, auto_install=False)
    if acorn_available():
        assert report["ok"] is True
    else:
        assert report["ok"] is False
        assert "acorn" in report.get("error", "")


@pytest.mark.skipif(not acorn_available(), reason="acorn is not installed")
def test_analyze_ast_data_flow_runs_real_acorn() -> None:
    js = "const ts = Date.now(); fetch('/api?ts=' + ts);"
    analysis = analyze_js(js)
    report = analyze_ast_data_flow(js, analysis, auto_install=False)
    assert report["ok"] is True
    assert any(edge["source_kind"] == "Date.now()" for edge in report["edges"])
