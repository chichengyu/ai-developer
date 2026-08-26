"""Tests for on-demand deep deobfuscation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from deep_deobfuscation import STRONG_OBFUSCATION_SCORE, deep_deobfuscate  # noqa: E402


def test_deep_deobfuscation_disabled_never_triggers() -> None:
    result = deep_deobfuscate("var a = 1;", mode="disabled")
    assert result["ok"] is True
    assert result["triggered"] is False
    assert result["mode"] == "disabled"


def test_deep_deobfuscation_always_triggers() -> None:
    result = deep_deobfuscate("var a = 1;", mode="always")
    assert result["ok"] is True
    assert result["triggered"] is True
    assert "tools" in result


def test_strong_threshold_is_public() -> None:
    assert STRONG_OBFUSCATION_SCORE == 70
