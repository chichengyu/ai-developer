"""Tests for bounded concolic dependency tracing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from concolic_runner import run_concolic_function  # noqa: E402
from deep_reverse import node_available  # noqa: E402


@pytest.mark.skipif(not node_available(), reason="node is not available")
def test_concolic_detects_input_dependencies() -> None:
    result = run_concolic_function(
        "function add(a,b){return a+':'+b;}",
        "add",
        ["x", "y"],
    )
    assert result.ok is True
    assert all(item["changed"] for item in result.dependencies)


@pytest.mark.skipif(not node_available(), reason="node is not available")
def test_concolic_ignores_unused_inputs() -> None:
    result = run_concolic_function(
        "function fixed(a,b){return 'constant';}",
        "fixed",
        ["x", "y"],
    )
    assert result.ok is True
    assert all(item["changed"] is False for item in result.dependencies)


def test_concolic_returns_non_fatal_without_node() -> None:
    if node_available():
        return
    result = run_concolic_function("var a=1;", "a", [])
    assert result.ok is False
