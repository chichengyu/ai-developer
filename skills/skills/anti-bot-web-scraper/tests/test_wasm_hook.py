"""Tests for WASM boundary hooking and parsing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from wasm_hook import (  # noqa: E402
    analyze_wasm_capture,
    decompile_wasm,
    decompile_wasm_available,
    decompile_wasm_pseudocode,
    parse_wasm_imports_exports,
    run_wasm_probe,
    wasm_hook_js,
    wasm_memory_diff,
)


def test_wasm_hook_js_contains_wrappers() -> None:
    js = wasm_hook_js("__wasm_test")
    assert "__wasm_test" in js
    assert "WebAssembly.instantiate" in js
    assert "wasm_export_call" in js


def test_parse_wasm_exports_minimal_binary() -> None:
    data = b"\x00asm\x01\x00\x00\x00\x07\x05\x01\x01e\x00\x00"
    parsed = parse_wasm_imports_exports(data)
    assert parsed["ok"] is True
    assert parsed["exports"] == [{"name": "e", "kind": 0, "index": 0}]


def test_analyze_wasm_capture_finds_wasm_urls() -> None:
    capture = {
        "html": '<script src="https://cdn.example.com/sign.wasm?v=1"></script>',
        "network": [{"url": "https://cdn.example.com/sign.wasm"}],
    }
    report = analyze_wasm_capture(capture)
    assert report["ok"] is True
    assert any("sign.wasm" in url for url in report["urls"])


def test_run_wasm_probe_returns_non_fatal_on_invalid_binary() -> None:
    result = run_wasm_probe(b"not-wasm", timeout=3)
    assert result["ok"] is False


def test_wasm_memory_diff_finds_changed_ranges() -> None:
    before = b"abcdef"
    after = b"abXdef"
    ranges = wasm_memory_diff(before, after)
    assert ranges == [{"start": 2, "end": 2, "bytes": 1}]


def test_wasm_decompile_reports_unavailable_tool() -> None:
    if decompile_wasm_available():
        return
    result = decompile_wasm(b"not-wasm")
    assert result["ok"] is False
    assert "not installed" in result["error"]


def test_wasm_pseudocode_reports_unavailable_wasm2c() -> None:
    import shutil

    if shutil.which("wasm2c"):
        return
    result = decompile_wasm_pseudocode(b"not-wasm")
    assert result["ok"] is False
    assert "wasm2c" in result["error"]
