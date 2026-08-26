"""Tests for call-chain reconstruction and Node replay."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from call_chain import (  # noqa: E402
    extract_stack_calls,
    find_probe_args,
    match_call_chain,
    replay_call_chain,
)
from deep_reverse import node_available  # noqa: E402


def _capture() -> dict:
    return {
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": "https://example.com/api?sign=x:y",
                    "stack": ["at genSign (https://example.com/bundle.js:12:3)"],
                }
            ]
        },
        "function_probes": {
            "function_calls": [{"name": "genSign", "args": ["x", "y"]}]
        },
        "network": [],
    }


def _fake_analysis() -> object:
    return type(
        "A",
        (),
        {
            "signature_candidates": [
                type(
                    "C",
                    (),
                    {
                        "name": "genSign",
                        "algorithm": "md5",
                        "line": 12,
                        "confidence": 0.9,
                    },
                )()
            ],
        },
    )()


def test_extract_stack_calls_and_probe_args() -> None:
    calls = extract_stack_calls(_capture())
    assert calls and calls[0]["function"] == "genSign"
    assert calls[0]["line"] == 12
    assert find_probe_args(_capture(), "genSign") == ["x", "y"]


def test_match_call_chain_joins_stack_and_candidates() -> None:
    matches = match_call_chain(_fake_analysis(), extract_stack_calls(_capture()))
    assert matches
    assert matches[0]["candidate"] == "genSign"
    assert matches[0]["algorithm"] == "md5"


@pytest.mark.skipif(not node_available(), reason="node is not available")
def test_replay_call_chain_verifies_captured_signature() -> None:
    js = "function genSign(a,b){return a+':'+b;}"
    report = replay_call_chain(js, _capture(), _fake_analysis())
    assert report["ok"] is True
    assert report["summary"]["replayed"] >= 1
    assert report["summary"]["verified"] >= 1
