"""Call-chain reconstruction and real-argument replay.

The deep hook records fetch/XHR stacks; the function probe records candidate
function calls.  This module joins the two: stack frames are matched to
static signature candidates, the probe supplies the real arguments, and
Node replays the function.  A replay whose result equals the captured
``sign``/``token`` value closes the reverse loop.
"""

from __future__ import annotations

import re
from typing import Any

_STACK_FRAME_RE = re.compile(
    r"at\s+(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(?([^)]*?):(\d+):(\d+)\)?",
)


def extract_stack_calls(capture: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract function/source/line/column tuples from hook stacks."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()
    for request in (capture.get("hook") or {}).get("requests", []) or []:
        if not isinstance(request, dict):
            continue
        for line in request.get("stack", []) or []:
            match = _STACK_FRAME_RE.search(str(line))
            if not match:
                continue
            function = match.group(1)
            source = match.group(2) or ""
            line_no = int(match.group(3))
            column = int(match.group(4))
            key = (function, source, line_no, column)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "function": function,
                    "source": source,
                    "line": line_no,
                    "column": column,
                    "raw": str(line),
                }
            )
    return out


def find_probe_args(capture: dict[str, Any], function_name: str) -> list[Any]:
    """Return the first matching function-probe arguments."""
    for call in (capture.get("function_probes") or {}).get("function_calls", []) or []:
        if not isinstance(call, dict):
            continue
        if str(call.get("name", "") or "") == function_name:
            args = call.get("args") or []
            if isinstance(args, list):
                return args
            return [args]
    return []


def match_call_chain(
    analysis: Any,
    stack_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match stack frames to static signature candidates."""
    candidates = list(getattr(analysis, "signature_candidates", []) or [])
    by_line = {int(getattr(item, "line", 0) or 0): item for item in candidates}
    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for call in stack_calls:
        function = str(call.get("function", "") or "")
        line = int(call.get("line", 0) or 0)
        candidate = next(
            (item for item in candidates if str(getattr(item, "name", "") or "") == function),
            by_line.get(line),
        )
        if candidate is None:
            continue
        key = (function, str(getattr(candidate, "name", "") or ""))
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            {
                "function": function or str(getattr(candidate, "name", "") or ""),
                "candidate": str(getattr(candidate, "name", "") or ""),
                "algorithm": str(getattr(candidate, "algorithm", "") or ""),
                "line": line,
                "source": str(call.get("source", "") or ""),
                "stack_line": str(call.get("raw", "") or "")[:200],
                "confidence": min(0.98, float(getattr(candidate, "confidence", 0.5) or 0.5) + 0.2),
            }
        )
    return matches


def replay_call_chain(
    js: str,
    capture: dict[str, Any],
    analysis: Any = None,
) -> dict[str, Any]:
    """Replay matched signature functions with real probe arguments."""
    try:
        from deep_reverse import node_available, run_signature_function
    except Exception:
        return {"ok": False, "error": "deep_reverse unavailable"}
    if not node_available():
        return {"ok": False, "error": "node is not available"}
    stack_calls = extract_stack_calls(capture)
    matches = match_call_chain(analysis, stack_calls) if analysis is not None else []
    if not matches and stack_calls:
        matches = [
            {
                "function": str(call.get("function", "") or ""),
                "candidate": str(call.get("function", "") or ""),
                "algorithm": "",
                "line": int(call.get("line", 0) or 0),
                "source": str(call.get("source", "") or ""),
                "stack_line": str(call.get("raw", "") or "")[:200],
                "confidence": 0.5,
            }
            for call in stack_calls[:10]
        ]
    replays: list[dict[str, Any]] = []
    for match in matches[:10]:
        function = str(match.get("function", "") or "")
        args = find_probe_args(capture, function) or ["a=1&b=2&ts=1786000000"]
        result = run_signature_function(js, function, args)
        replays.append(
            {
                "function": function,
                "args": args[:10],
                "ok": bool(result.get("ok")),
                "result": result.get("value"),
                "error": result.get("error"),
                "line": match.get("line"),
                "confidence": match.get("confidence"),
            }
        )
    captured_values = _captured_signature_values(capture)
    for replay in replays:
        if replay.get("result") is not None:
            replay["verified"] = str(replay["result"]) in captured_values
        else:
            replay["verified"] = False
    return {
        "ok": True,
        "stack_calls": len(stack_calls),
        "matches": matches,
        "replays": replays,
        "summary": {
            "stack_calls": len(stack_calls),
            "matched": len(matches),
            "replayed": len(replays),
            "verified": sum(1 for item in replays if item.get("verified")),
        },
    }


def _captured_signature_values(capture: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for request in (capture.get("hook") or {}).get("requests", []) or []:
        if not isinstance(request, dict):
            continue
        url = str(request.get("url", "") or "")
        from urllib.parse import parse_qs, urlsplit

        for value_list in parse_qs(urlsplit(url).query).values():
            values.update(str(value) for value in value_list)
    return values


def _self_test() -> None:
    capture = {
        "hook": {
            "requests": [
                {
                    "url": "https://example.com/api?sign=abc",
                    "stack": ["at genSign (https://example.com/bundle.js:12:3)"],
                }
            ]
        },
        "function_probes": {
            "function_calls": [{"name": "genSign", "args": ["a=1"]}]
        },
        "network": [],
    }
    calls = extract_stack_calls(capture)
    assert calls and calls[0]["function"] == "genSign"
    assert find_probe_args(capture, "genSign") == ["a=1"]
    print("call_chain self-test OK")


if __name__ == "__main__":
    _self_test()
