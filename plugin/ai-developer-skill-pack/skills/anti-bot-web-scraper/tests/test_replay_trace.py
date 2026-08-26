"""Tests for execution-trace capture and Node replay."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from deep_reverse import node_available  # noqa: E402
from replay_trace import capture_execution_trace, replay_execution_trace  # noqa: E402


def test_replay_execution_trace_replays_scripts() -> None:
    trace = {
        "scripts": [{"scriptId": "1", "url": "bundle.js", "source": "var a = 1;"}],
        "console_events": [],
    }
    result = replay_execution_trace(trace)
    if node_available():
        assert result["summary"]["replayed"] == 1
    else:
        assert result["ok"] is False


@pytest.mark.skipif(not node_available(), reason="node is not available")
def test_replay_execution_trace_handles_missing_sources() -> None:
    result = replay_execution_trace(
        {"scripts": [{"scriptId": "1", "url": "bundle.js", "source": ""}]}
    )
    assert result["summary"]["replayed"] == 0


def test_capture_execution_trace_returns_non_fatal_without_session() -> None:
    result = capture_execution_trace(None)
    assert result["ok"] is False
