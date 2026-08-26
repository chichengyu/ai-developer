"""Tests for lightweight symbolic flow tracing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from symbolic_probe import analyze_symbolic_flow, solve_short_secret_constraints  # noqa: E402


def test_symbolic_flow_tracks_signature_derivation() -> None:
    report = analyze_symbolic_flow(
        "const ts = Date.now(); const sign = md5(ts + secretKey);"
    )
    assert report["ok"] is True
    assert report["summary"]["dynamic_sources"] >= 1
    assert report["summary"]["constraints"] >= 1
    assert any("md5" in item["expression"] for item in report["constraints"])


def test_symbolic_solver_reports_z3_missing() -> None:
    result = solve_short_secret_constraints([{"expression": "a == b"}])
    if "z3-solver" in result.get("error", ""):
        assert result["ok"] is False
    else:
        assert result["ok"] is True
