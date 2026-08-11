"""On-demand deep deobfuscation for strongly obfuscated scripts.

The built-in ``deep_reverse.deobfuscate_js`` remains the default path for
ordinary/minified code.  This module is only triggered when a script is
classified as strong obfuscation (or when ``mode="always"``) and then runs
the heavier passes: dynamic string-array decoding through Node, acorn AST
validation, and the optional webcrack deobfuscator.  Every tool is optional;
missing tools are reported instead of failing the whole analysis.
"""

from __future__ import annotations

from typing import Any

STRONG_OBFUSCATION_SCORE = 70


def deep_deobfuscate(
    js: str,
    mode: str = "auto",
    *,
    auto_install: bool = False,
    max_passes: int = 12,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Run built-in plus deep deobfuscation passes for strong bundles."""
    try:
        from deep_reverse import (
            acorn_extract_functions,
            decode_string_arrays_dynamic,
            deobfuscate_js,
            detect_obfuscation,
            ensure_acorn,
            node_available,
            webcrack_available,
            webcrack_deobfuscate,
        )
    except Exception:
        return {"ok": False, "error": "deep_reverse unavailable", "triggered": False}

    mode = str(mode or "auto").lower()
    builtin = deobfuscate_js(js, max_passes=max_passes)
    profile = detect_obfuscation(builtin.output or js)
    strong = profile.score >= STRONG_OBFUSCATION_SCORE
    triggered = mode == "always" or (mode == "auto" and strong)
    passes = list(builtin.passes)
    output = builtin.output
    tools: dict[str, Any] = {
        "builtin": bool(builtin.passes),
        "dynamic_decode": False,
        "acorn": False,
        "webcrack": False,
    }
    if not triggered:
        return {
            "ok": True,
            "triggered": False,
            "mode": mode,
            "score": profile.score,
            "level": profile.level,
            "output": output,
            "passes": passes,
            "tools": tools,
        }

    if node_available():
        try:
            dynamic = decode_string_arrays_dynamic(js)
            if dynamic.passes:
                output = dynamic.output
                passes.extend(dynamic.passes)
                tools["dynamic_decode"] = True
        except Exception:
            pass

    acorn = ensure_acorn(install=auto_install)
    if acorn.get("ok"):
        try:
            parsed = acorn_extract_functions(output, auto_install=False)
            tools["acorn"] = bool(parsed.get("ok"))
        except Exception:
            tools["acorn"] = False

    if webcrack_available() or auto_install:
        try:
            result = webcrack_deobfuscate(output, auto_install=auto_install, timeout=timeout)
            if result.get("ok"):
                candidate = str(result.get("output", "") or "")
                if len(candidate) >= max(64, len(output) // 2):
                    output = candidate
                    passes.append("webcrack")
                    tools["webcrack"] = True
        except Exception:
            tools["webcrack"] = False

    return {
        "ok": True,
        "triggered": True,
        "mode": mode,
        "score": profile.score,
        "level": profile.level,
        "output": output,
        "passes": passes,
        "tools": tools,
    }


def _self_test() -> None:
    result = deep_deobfuscate("var a = 1;", mode="disabled")
    assert result["ok"] is True
    assert result["triggered"] is False
    print("deep_deobfuscation self-test OK")


if __name__ == "__main__":
    _self_test()
