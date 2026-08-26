"""Tests for whole-bundle Node execution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bundle_runner import extract_webpack_module_table, run_bundle_execution  # noqa: E402
from deep_reverse import node_available  # noqa: E402


@pytest.mark.skipif(not node_available(), reason="node is not available")
def test_bundle_execution_calls_candidate_function() -> None:
    js = "function genSign(a,b){return a+':'+b;}"
    result = run_bundle_execution(js, candidate_names=["genSign"], timeout=5)
    assert result["ok"] is True
    trace = next(item for item in result["traces"] if item["name"] == "genSign")
    assert trace["ok"] is True
    assert trace["result"] == "a=1&b=2&ts=1786000000:1786000000"


@pytest.mark.skipif(not node_available(), reason="node is not available")
def test_bundle_execution_handles_browser_stubs() -> None:
    js = (
        "function deviceTag(){return navigator.userAgent.slice(0, 9);}"
        "window.__bundleReady = true;"
    )
    result = run_bundle_execution(js, candidate_names=["deviceTag"], timeout=5)
    assert result["ok"] is True
    assert any(trace["name"] == "deviceTag" for trace in result["traces"])


def test_bundle_execution_returns_non_fatal_without_node() -> None:
    if node_available():
        return
    result = run_bundle_execution("var a=1;", candidate_names=["a"])
    assert result["ok"] is False
    assert "node" in result.get("error", "")


def test_extract_webpack_module_table() -> None:
    js = (
        'var __webpack_modules__ = {"1":function(module,exports,__webpack_require__){'
        "exports.genSign=function(a,b){return a+':'+b;}}}"
    )
    modules = extract_webpack_module_table(js)
    assert "1" in modules
    assert "genSign" in modules["1"]


@pytest.mark.skipif(not node_available(), reason="node is not available")
def test_bundle_execution_takes_over_webpack_modules() -> None:
    js = (
        'var __webpack_modules__ = {"1":function(module,exports,__webpack_require__){'
        "exports.genSign=function(a,b){return a+':'+b;}}}"
    )
    result = run_bundle_execution(js, candidate_names=["genSign"], timeout=5)
    assert result["ok"] is True
    assert result["summary"]["webpack_modules_executed"] >= 1
    assert any(trace["name"] == "genSign" for trace in result["traces"])
