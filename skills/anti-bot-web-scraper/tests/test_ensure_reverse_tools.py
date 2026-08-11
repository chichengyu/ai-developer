"""Tests for on-demand reverse-tool installers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ensure_reverse_tools import (  # noqa: E402
    ensure_mitmproxy,
    ensure_reverse_tool,
    ensure_wabt,
    ensure_z3,
    reverse_tools_status,
    wabt_available,
    z3_available,
)


def test_status_is_boolean_for_all_tools() -> None:
    status = reverse_tools_status()
    assert set(status) == {"z3", "wabt", "mitmproxy"}
    assert all(isinstance(value, bool) for value in status.values())


def test_ensure_z3_check_only() -> None:
    result = ensure_z3(install=False)
    assert result["ok"] is z3_available()


def test_ensure_wabt_check_only() -> None:
    result = ensure_wabt(install=False)
    assert result["ok"] is wabt_available()
    if not result["ok"]:
        assert "wabt" in result["error"]


def test_ensure_mitmproxy_check_only() -> None:
    result = ensure_mitmproxy(install=False)
    if not result["ok"]:
        assert "mitmdump" in result["error"]


def test_ensure_reverse_tool_dispatch() -> None:
    assert ensure_reverse_tool("z3-solver", install=False)["tool"] == "z3"
    assert ensure_reverse_tool("wasm2c", install=False)["tool"] == "wabt"
    assert ensure_reverse_tool("mitmdump", install=False)["tool"] == "mitmdump"
    assert ensure_reverse_tool("unknown", install=False)["ok"] is False
