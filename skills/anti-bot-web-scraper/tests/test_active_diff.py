"""Tests for oracle-guided active differential verification."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from active_diff import (  # noqa: E402
    run_active_diff_oracle,
    run_active_diff_tree,
    run_active_differential,
)


def _sender(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    data: Any = None,
    body: Any = None,
) -> tuple[int, str, dict[str, str]]:
    if "ts=" in url and "ts=1786000000" not in url:
        return 403, '{"error":"signature expired"}', {}
    if "a=__active_diff__" in url:
        return 200, '{"ok":true}', {}
    return 200, '{"ok":true}', {}


def test_active_differential_classifies_signed_and_unsigned_fields() -> None:
    capture = {
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": "https://example.com/api?sign=x&a=1&ts=1786000000",
                }
            ]
        },
        "network": [],
    }
    report = run_active_differential([capture], _sender)
    assert report.summary["requests"] == 2
    ts_row = next(item for item in report.results if item.field == "ts")
    a_row = next(item for item in report.results if item.field == "a")
    assert ts_row.changed is True
    assert ts_row.error_hint == "signature"
    assert a_row.changed is False


def test_active_differential_returns_empty_without_signature() -> None:
    capture = {
        "hook": {"requests": [{"method": "GET", "url": "https://example.com/api?a=1"}]},
        "network": [],
    }
    report = run_active_differential([capture], _sender)
    assert report.summary["requests"] == 0


def test_active_diff_tree_adds_combination_rounds() -> None:
    capture = {
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": "https://example.com/api?sign=x&a=1&ts=1786000000",
                }
            ]
        },
        "network": [],
    }
    report = run_active_diff_tree([capture], _sender, max_requests=12)
    assert "decision_tree" in report.summary
    assert report.summary["decision_tree"]["tree_requests"] >= 1
    assert report.summary["decision_tree"]["signed_fields"] == ["ts"]


def _oracle_sender(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    data: Any = None,
    body: Any = None,
) -> tuple[int, str, dict[str, str]]:
    if headers and headers.get("X-Oracle-Ok") == "1":
        return 200, '{"ok":true}', {}
    return 403, '{"error":"bad signature"}', {}


def test_active_diff_oracle_converges_on_accepted_request() -> None:
    capture = {
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": "https://example.com/api?sign=x&a=1&ts=1786000000",
                }
            ]
        },
        "network": [],
    }
    report = run_active_diff_oracle([capture], _oracle_sender, max_rounds=3)
    assert report.summary["oracle"]["converged"] is True
    assert report.summary["accepted_status"] == 200
