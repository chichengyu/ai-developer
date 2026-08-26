"""Cross-chunk / cross-bundle interprocedural taint.

Single-file AST flow cannot see that ``a.js`` defines ``genSign`` while
``b.js`` calls it with a device fingerprint.  This module joins
``cross_script_refs`` with per-script data-flow edges so a source in one
chunk is propagated to a request target in another chunk.
"""

from __future__ import annotations

from typing import Any


def analyze_interprocedural_flow(
    sources: list[dict[str, Any]],
    combined_analysis: Any = None,
) -> dict[str, Any]:
    """Build interprocedural taint edges across script/chunk boundaries."""
    try:
        from deep_reverse import analyze_js, cross_script_refs
    except Exception:
        return {"ok": False, "error": "deep_reverse unavailable"}
    analyses: dict[str, Any] = {}
    for source in sources:
        name = str(source.get("name", "") or "script")
        content = str(source.get("content", "") or "")
        analyses[name] = analyze_js(content, name)
    sources_by_name = {str(source.get("name", "") or f"script-{index}"): source for index, source in enumerate(sources)}
    refs = cross_script_refs(
        [
            {
                "name": str(source.get("name", "") or f"script-{index}"),
                "content": str(source.get("content", "") or ""),
            }
            for index, source in enumerate(sources)
        ]
    )
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str, int]] = set()
    for ref in refs:
        function_name = str(ref.get("function", "") or "")
        defined_in = str(ref.get("defined_in", "") or "")
        referenced_in = str(ref.get("referenced_in", "") or "")
        defined = analyses.get(defined_in)
        referenced = analyses.get(referenced_in)
        if defined is None or referenced is None:
            continue
        defined_assign = _assignment_map(str(sources_by_name.get(defined_in, {}).get("content", "") or ""))
        referenced_assign = _assignment_map(str(sources_by_name.get(referenced_in, {}).get("content", "") or ""))
        for site in referenced.request_sites:
            raw = " ".join(
                str(value)
                for value in (
                    getattr(site, "url", ""),
                    getattr(site, "raw", ""),
                    getattr(site, "headers", {}),
                    getattr(site, "params", {}),
                    getattr(site, "body", ""),
                )
            )
            direct_call = re_search(rf"\b{_escape(function_name)}\s*\(", raw)
            called_via_var = any(
                name in raw and function_name in expression
                for name, expression in referenced_assign.items()
            )
            if not direct_call and not called_via_var:
                continue
            defined_links = [
                link
                for link in defined.data_flow
                if link.source_kind in {"device", "timestamp", "crypto", "signature"}
            ]
            source_links = defined_links or [
                link
                for link in referenced.data_flow
                if link.source_kind in {"device", "timestamp", "crypto"}
            ]
            for link in source_links:
                target = (
                    f"{getattr(site, 'url', '')}"
                    if not any(
                        str(key) in str(value)
                        for key, value in getattr(site, "headers", {}).items()
                    )
                    and not getattr(site, "params", {})
                    else "request"
                )
                key = (
                    link.source,
                    link.source_kind,
                    function_name,
                    defined_in,
                    referenced_in,
                    int(getattr(site, "line", 0) or 0),
                )
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    {
                        "source": link.source,
                        "source_kind": link.source_kind,
                        "function": function_name,
                        "defined_in": defined_in,
                        "referenced_in": referenced_in,
                        "target": target,
                        "line": int(getattr(site, "line", 0) or 0),
                        "confidence": min(0.95, 0.6 + float(getattr(link, "confidence", 0.5) or 0.5) * 0.3),
                    }
                )
            if not source_links:
                for variable, expression in defined_assign.items():
                    kind = _classify_expression(expression)
                    if not kind:
                        continue
                    used = variable in raw or called_via_var or any(
                        variable in expression for expression in referenced_assign.values()
                    )
                    if not used:
                        continue
                    key = (
                        variable,
                        kind,
                        function_name,
                        defined_in,
                        referenced_in,
                        int(getattr(site, "line", 0) or 0),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append(
                        {
                            "source": variable,
                            "source_kind": kind,
                            "function": function_name,
                            "defined_in": defined_in,
                            "referenced_in": referenced_in,
                            "target": str(getattr(site, "url", "") or "request"),
                            "line": int(getattr(site, "line", 0) or 0),
                            "confidence": 0.72,
                        }
                    )
    return {
        "ok": True,
        "edges": edges,
        "cross_refs": refs,
        "summary": {"edges": len(edges), "cross_refs": len(refs)},
    }


def _escape(value: str) -> str:
    import re

    return re.escape(value)


def _assignment_map(content: str) -> dict[str, str]:
    import re

    return {
        match.group(1): match.group(2)
        for match in re.finditer(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;{}]+?);", content)
    }


def _classify_expression(expression: str) -> str:
    import re

    if re.search(r"navigator\.|screen\.|canvas|WebGL|devicePixelRatio|timezone", expression, re.I):
        return "device"
    if re.search(r"Date\.now|performance\.now|Math\.random", expression, re.I):
        return "timestamp"
    if re.search(r"md5|sha|hmac|crypto|encrypt|cipher", expression, re.I):
        return "crypto"
    return ""


def re_search(pattern: str, text: str) -> Any:
    import re

    return re.search(pattern, text)


def _self_test() -> None:
    sources = [
        {
            "name": "a.js",
            "content": "function genSign(x){return md5(x)} var ua=navigator.userAgent;",
        },
        {
            "name": "b.js",
            "content": "var sig=genSign(ua); fetch('/api?device='+ua,{headers:{'X-Token':sig}});",
        },
    ]
    report = analyze_interprocedural_flow(sources)
    assert report["ok"] is True
    assert report["summary"]["edges"] >= 1
    print("bundle_taint self-test OK")


if __name__ == "__main__":
    _self_test()
