"""AST-based data-flow analysis for protected JavaScript.

The static analyzer in ``deep_reverse.py`` is deliberately conservative and
regex-driven.  This module adds a second pass that uses the acorn AST (when
Node.js and acorn are available) to track assignments and call sites more
precisely.  It stays optional: when acorn is missing the module returns a
non-fatal ``ok: false`` result and the pipeline continues with the existing
regex data flow.
"""

from __future__ import annotations

from typing import Any


def build_ast_data_flow(
    flow: list[dict[str, Any]],
    analysis: Any,
) -> dict[str, Any]:
    """Turn acorn ``flow`` entries into source-to-request-target edges."""
    from deep_reverse import _assignment_sources

    candidates = list(getattr(analysis, "signature_candidates", []) or [])
    request_sites = list(getattr(analysis, "request_sites", []) or [])
    assignments: dict[str, list[tuple[str, str]]] = {}
    assignment_lines: dict[str, int] = {}
    for entry in flow:
        if entry.get("kind") not in {"assignment", "variable"}:
            continue
        target = str(entry.get("target") or entry.get("name") or "")
        value = str(entry.get("value") or entry.get("init") or "")
        if not target or not value:
            continue
        sources = _assignment_sources(value, candidates)
        if sources:
            assignments.setdefault(target, []).extend(sources)
            assignment_lines.setdefault(target, int(entry.get("line") or 0))

    def resolve_sources(expression: str) -> list[tuple[str, str, str]]:
        """Resolve direct sources plus sources assigned to referenced vars."""
        out: list[tuple[str, str, str]] = []
        direct = _assignment_sources(expression, candidates)
        out.extend((source, kind, expression) for source, kind in direct)
        for variable in _variable_names(expression):
            for source, kind in assignments.get(variable, []):
                out.append((source, kind, variable))
        return list(dict.fromkeys(out))

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str, int, str]] = set()
    for site in request_sites:
        raw = f"{getattr(site, 'url', '')} {getattr(site, 'raw', '')}"
        site_line = int(getattr(site, "line", 0) or 0)
        call_entries = [
            entry for entry in flow if entry.get("kind") == "call" and abs(
                int(entry.get("line") or 0) - site_line
            )
            <= 3
        ]
        expressions = [str(entry.get("args", "") or "") for entry in call_entries]
        if not expressions:
            expressions = [raw]
        for expression in expressions:
            for source, source_kind, variable in resolve_sources(expression):
                targets: list[tuple[str, str]] = []
                for key, value in (getattr(site, "headers", {}) or {}).items():
                    if variable in str(value) or source in str(value):
                        targets.append((str(key), "header"))
                for key, value in (getattr(site, "params", {}) or {}).items():
                    if variable in str(value) or source in str(value):
                        targets.append((str(key), "param"))
                body = getattr(site, "body", None)
                if isinstance(body, dict):
                    for key, value in body.items():
                        if variable in str(value) or source in str(value):
                            targets.append((str(key), "body"))
                if not targets:
                    for match in _QUERY_PARAM_RE.finditer(raw):
                        if variable in match.group(2) or source in match.group(2):
                            targets.append((match.group(1), "param"))
                if not targets and (variable in raw or source in raw):
                    targets.append(("url", "url"))
                if not targets:
                    targets.append(("request.options", "options"))
                for target, target_kind in targets:
                    key = (
                        source,
                        source_kind,
                        variable,
                        target,
                        target_kind,
                        site_line,
                        expression,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(
                        {
                            "source": source,
                            "source_kind": source_kind,
                            "variable": variable,
                            "target": target,
                            "target_kind": target_kind,
                            "line": site_line,
                            "assignment_line": assignment_lines.get(variable, site_line),
                            "confidence": 0.92 if target_kind != "options" else 0.68,
                            "method": "ast",
                            "expression": expression[:300],
                        }
                    )
    edges.sort(key=lambda item: (item["line"], item["source_kind"]))
    return {
        "ok": True,
        "edges": edges,
        "summary": {
            "assignments": len(assignments),
            "edges": len(edges),
            "request_sites": len(request_sites),
        },
    }


def analyze_ast_data_flow(
    js: str,
    analysis: Any,
    *,
    auto_install: bool = False,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Run acorn and build AST data-flow edges for one JS source."""
    try:
        from deep_reverse import acorn_available, ensure_acorn, run_acorn
    except Exception:
        return {"ok": False, "error": "deep_reverse unavailable"}
    if not acorn_available() and not auto_install:
        return {"ok": False, "error": "acorn is not installed"}
    ensure = ensure_acorn(install=auto_install)
    if not ensure.get("ok"):
        return {"ok": False, "error": ensure.get("error", "acorn unavailable")}
    parsed = run_acorn(js, auto_install=False, timeout=timeout)
    if not parsed.get("ok"):
        return {"ok": False, "error": parsed.get("error", "acorn parse failed")}
    return build_ast_data_flow(list(parsed.get("flow", []) or []), analysis)


def _variable_names(expression: str) -> list[str]:
    return [
        match.group(1)
        for match in _VARIABLE_RE.finditer(expression)
        if match.group(1) not in _KEYWORD_FILTER
    ]


import re  # noqa: E402

_VARIABLE_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\b")
_QUERY_PARAM_RE = re.compile(r"[?&]([A-Za-z_$][\w$]*)=([^&]*)")
_KEYWORD_FILTER = {
    "Date",
    "Math",
    "JSON",
    "Object",
    "Array",
    "String",
    "Number",
    "Boolean",
    "window",
    "document",
    "navigator",
    "performance",
    "screen",
    "fetch",
    "headers",
    "method",
    "body",
    "url",
    "params",
}


def _self_test() -> None:
    analysis = _FakeAnalysis()
    flow = [
        {"kind": "variable", "name": "ts", "init": "Date.now()", "line": 1},
        {"kind": "call", "callee": "fetch", "args": "'/api?ts=' + ts", "line": 2},
    ]
    report = build_ast_data_flow(flow, analysis)
    assert report["ok"] is True
    assert any(edge["source_kind"] == "timestamp" for edge in report["edges"])
    print("ast_dataflow self-test OK")


class _FakeAnalysis:
    signature_candidates: list[Any] = []
    request_sites: list[Any] = [
        type("Site", (), {"url": "/api?ts=1", "line": 2, "raw": "'/api?ts=' + ts", "headers": {}, "params": {"ts": 1}, "body": None})()
    ]


if __name__ == "__main__":
    _self_test()
