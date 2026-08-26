"""One-command deep reverse-engineering pipeline.

This wrapper only orchestrates the existing modules:

- ``deep_hook.run_browser_hook`` -- optional runtime capture
- ``deep_reverse.analyze_capture`` / ``analyze_js`` -- static analysis
- ``reverse_lab.analyze_capture_set`` -- cross-request lab analysis

It adds no behavior to the existing automatic flow; every feature can still
be invoked directly through the original scripts.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

try:
    from deep_reverse import (  # type: ignore
        DeobfuscationResult,
        acorn_extract_functions,
        analyze_capture,
        analyze_js,
        analyze_source_map,
        decode_string_arrays_dynamic,
        ensure_jsbeautifier,
        load_source_map,
        map_analysis_lines,
        webcrack_deobfuscate,
    )
except Exception:  # pragma: no cover - scripts directory is normally on sys.path
    DeobfuscationResult = object  # type: ignore[assignment]
    acorn_extract_functions = None  # type: ignore[assignment]
    analyze_capture = None  # type: ignore[assignment]
    analyze_js = None  # type: ignore[assignment]
    analyze_source_map = None  # type: ignore[assignment]
    decode_string_arrays_dynamic = None  # type: ignore[assignment]
    ensure_jsbeautifier = None  # type: ignore[assignment]
    load_source_map = None  # type: ignore[assignment]
    map_analysis_lines = None  # type: ignore[assignment]
    webcrack_deobfuscate = None  # type: ignore[assignment]

try:
    from reverse_lab import analyze_capture_set  # type: ignore
except Exception:  # pragma: no cover
    analyze_capture_set = None  # type: ignore[assignment]

try:
    from deep_hook import run_browser_hook  # type: ignore
except Exception:  # pragma: no cover
    run_browser_hook = None  # type: ignore[assignment]


def run_auto(
    captures: list[dict[str, Any]],
    js: str | None = None,
    js_url: str | None = None,
    secrets: list[str] | None = None,
    algorithms: list[str] | None = None,
    brute_force: bool = False,
    brute_max_length: int = 3,
    brute_charset: str = "abcdefghijklmnopqrstuvwxyz0123456789",
    exclude_params: list[str] | None = None,
    max_functions: int = 15,
    source_map_path: str | None = None,
    use_webcrack: bool = False,
    use_acorn: bool = False,
    install_beautifier: bool = False,
    dynamic_decode: bool = False,
    deep_deobfuscation: str = "auto",
    run_bundle: str = "auto",
    active_diff: bool | dict[str, Any] | None = None,
    active_diff_sender: Any = None,
    auto_install: bool = False,
    knowledge_store: str | None = None,
    replay_call_chain: bool = False,
    symbolic: bool = False,
) -> dict[str, Any]:
    """Run static + lab analysis and return one combined report dict."""
    captures = [copy.deepcopy(capture) for capture in captures]
    capture = captures[0] if captures else {}
    static = (
        analyze_capture(
            capture,
            deep_deobfuscation=deep_deobfuscation,
            auto_install=auto_install,
            run_bundle=run_bundle,
        )
        if analyze_capture is not None
        else None
    )

    js_analysis = None
    source_map_summary: dict[str, Any] | None = None
    if js and analyze_js is not None:
        if install_beautifier and ensure_jsbeautifier is not None:
            ensure_jsbeautifier(install=True)
        js_analysis = analyze_js(
            js,
            js_url,
            deep_deobfuscation=deep_deobfuscation,
            auto_install=auto_install,
            run_bundle=run_bundle,
        )
        if source_map_path and analyze_source_map is not None and map_analysis_lines is not None:
            source_map_summary = analyze_source_map(
                js,
                source_map_path=source_map_path,
                js_path=js_url,
            )
            if source_map_summary.get("ok") and load_source_map is not None:
                source_map_summary["mapped_analysis"] = map_analysis_lines(
                    js_analysis,
                    load_source_map(source_map_path),
                )
        if use_webcrack and webcrack_deobfuscate is not None:
            result = webcrack_deobfuscate(js)
            if result.get("ok"):
                js_analysis.deobfuscated = DeobfuscationResult(
                    output=str(result.get("output", "")),
                    passes=["webcrack"],
                )
        if dynamic_decode and decode_string_arrays_dynamic is not None:
            decoded = decode_string_arrays_dynamic(js)
            if decoded.passes:
                js_analysis.deobfuscated = DeobfuscationResult(
                    output=decoded.output,
                    passes=(js_analysis.deobfuscated.passes if js_analysis.deobfuscated else [])
                    + decoded.passes,
                )
        if use_acorn and acorn_extract_functions is not None:
            acorn_result = acorn_extract_functions(js)
            if acorn_result.get("ok"):
                js_analysis.bundle["acorn"] = {
                    "functions": acorn_result.get("functions", []),
                    "strings": acorn_result.get("strings", []),
                }

    lab = (
        analyze_capture_set(
            captures,
            secrets=secrets,
            algorithms=algorithms,
            brute_force=brute_force,
            brute_max_length=brute_max_length,
            brute_charset=brute_charset,
            exclude_params=exclude_params,
            max_functions=max_functions,
            js_bundle=js,
            active_diff=active_diff,
            active_diff_sender=active_diff_sender,
            knowledge_store=knowledge_store,
        )
        if analyze_capture_set is not None
        else None
    )
    lab_dict = lab.to_dict() if lab is not None else {}
    call_chain_report: dict[str, Any] = {}
    if replay_call_chain and js and captures and js_analysis is not None:
        try:
            from call_chain import replay_call_chain

            call_chain_report = replay_call_chain(js, capture, js_analysis)
        except Exception as exc:
            call_chain_report = {"ok": False, "error": str(exc)}
    symbolic_report: dict[str, Any] = {}
    if symbolic and js:
        try:
            from symbolic_probe import analyze_symbolic_flow, solve_short_secret_constraints

            symbolic_report = analyze_symbolic_flow(js)
            if symbolic_report.get("constraints"):
                symbolic_report["solver"] = solve_short_secret_constraints(
                    symbolic_report["constraints"],
                    auto_install=True,
                )
        except Exception as exc:
            symbolic_report = {"ok": False, "error": str(exc)}
    summary = {
        "captures": len(captures),
        "js_bundle": bool(js),
        "static_scripts": len(static.scripts) if static is not None else 0,
        "static_request_sites": len(static.analysis.request_sites) if static is not None else 0,
        "ast_data_flow_links": len(static.analysis.ast_data_flow) if static is not None else 0,
        "function_calls": len(
            (capture.get("function_probes") or {}).get("function_calls", [])
        )
        if captures
        else 0,
        "wasm_calls": len(
            (capture.get("wasm_calls") or {}).get("wasm_calls", [])
        )
        if captures
        else 0,
        "native_calls": len(
            (capture.get("native_probes") or {}).get("native_calls", [])
        )
        if captures
        else 0,
        "bundle_execution_matched": (
            (js_analysis.bundle.get("execution") or {}).get("summary", {}).get("matched", 0)
            if js_analysis is not None
            else 0
        ),
        "signature_candidates": (
            len(static.analysis.signature_candidates) if static is not None else 0
        ),
        "lab_verified_signatures": lab_dict.get("summary", {}).get("verified_signatures", 0),
        "lab_js_replay_matched": lab_dict.get("summary", {}).get("js_replay_matched", 0),
        "lab_generated_python": len(lab_dict.get("generated_python", [])) if lab_dict else 0,
        "lab_generated_node": len(lab_dict.get("generated_node", [])) if lab_dict else 0,
        "lab_active_diff": lab_dict.get("summary", {}).get("active_diff", 0) if lab_dict else 0,
        "lab_secret_candidates": (
            lab_dict.get("summary", {}).get("secret_candidates", 0) if lab_dict else 0
        ),
        "lab_knowledge_entries": (
            lab_dict.get("summary", {}).get("knowledge_entries", 0) if lab_dict else 0
        ),
        "call_chain_verified": call_chain_report.get("summary", {}).get("verified", 0),
        "symbolic_constraints": symbolic_report.get("summary", {}).get("constraints", 0),
    }
    return {
        "url": capture.get("url"),
        "capture": capture,
        "deep_reverse": static.to_dict() if static is not None else {},
        "js_analysis": js_analysis.to_dict() if js_analysis is not None else None,
        "source_map": source_map_summary,
        "reverse_lab": lab_dict,
        "call_chain": call_chain_report,
        "symbolic_flow": symbolic_report,
        "summary": summary,
    }


def _load_capture(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _self_test() -> None:
    capture = {
        "url": "https://example.com/",
        "html": '<script>function sign(){return md5("x")} fetch("/api?sign="+sign())</script>',
        "network": [],
    }
    report = run_auto([capture], js="function sign(){return 'abc'}")
    assert report["summary"]["captures"] == 1
    assert "reverse_lab" in report
    assert "js_analysis" in report
    print("deep_reverse_auto self-test OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-command deep reverse pipeline")
    parser.add_argument("--url", default=None, help="capture a page with deep_hook")
    parser.add_argument("--capture", action="append", default=[], help="capture JSON file")
    parser.add_argument("--html", default=None, help="HTML file")
    parser.add_argument("--js", default=None, help="JS bundle for static + dynamic analysis")
    parser.add_argument("--output", default=None, help="write combined report JSON")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--engine", default="playwright")
    parser.add_argument("--wait-ms", type=float, default=5000)
    parser.add_argument("--timeout-ms", type=float, default=30000)
    parser.add_argument("--secrets", default="")
    parser.add_argument("--algorithms", default="md5,sha1,sha256,hmac-md5,hmac-sha1,hmac-sha256")
    parser.add_argument("--brute-secret", action="store_true")
    parser.add_argument("--brute-max", type=int, default=3)
    parser.add_argument("--brute-charset", default="abcdefghijklmnopqrstuvwxyz0123456789")
    parser.add_argument("--exclude-params", default="")
    parser.add_argument("--max-functions", type=int, default=15)
    parser.add_argument("--source-map", default=None)
    parser.add_argument("--webcrack", action="store_true")
    parser.add_argument("--acorn", action="store_true")
    parser.add_argument("--install-beautifier", action="store_true")
    parser.add_argument("--dynamic-decode", action="store_true")
    parser.add_argument(
        "--deep-deobfuscation",
        default="auto",
        choices=("auto", "always", "disabled"),
        help="enable deep deobfuscation on strong obfuscation",
    )
    parser.add_argument(
        "--run-bundle",
        default="auto",
        choices=("auto", "always", "disabled"),
        help="execute whole JS bundles in Node on demand",
    )
    parser.add_argument(
        "--probe-patterns",
        default="",
        help="comma-separated function patterns for browser function tracing",
    )
    parser.add_argument(
        "--wasm-hook",
        action="store_true",
        help="install the WASM export-call hook during browser capture",
    )
    parser.add_argument(
        "--native-probe",
        action="store_true",
        help="install the native API probe during browser capture",
    )
    parser.add_argument(
        "--wasm",
        default=None,
        help="local .wasm file to probe in Node",
    )
    parser.add_argument(
        "--cdp-probe",
        action="store_true",
        help="run CDP breakpoint probing against the target URL",
    )
    parser.add_argument(
        "--cdp-wait-ms",
        type=float,
        default=5000,
        help="networkidle wait after CDP breakpoint reload",
    )
    parser.add_argument(
        "--cdp-return-probe",
        action="store_true",
        help="capture entry arguments and return values with CDP step-out",
    )
    parser.add_argument(
        "--coverage-probe",
        action="store_true",
        help="run CDP precise coverage and filter executed candidates",
    )
    parser.add_argument(
        "--active-diff",
        action="store_true",
        help="run oracle-guided active differential verification",
    )
    parser.add_argument(
        "--auto-install",
        action="store_true",
        help="auto-install acorn/webcrack for strong obfuscation",
    )
    parser.add_argument(
        "--knowledge-store",
        default=None,
        help="JSON path for cross-site signature knowledge reuse",
    )
    parser.add_argument(
        "--replay-call-chain",
        action="store_true",
        help="replay hook stack functions with function-probe arguments",
    )
    parser.add_argument(
        "--symbolic",
        action="store_true",
        help="run lightweight symbolic expression tracing on the JS bundle",
    )
    parser.add_argument(
        "--concolic",
        action="store_true",
        help="run bounded concolic dependency tracing on candidate functions",
    )
    parser.add_argument(
        "--replay-trace",
        action="store_true",
        help="capture a browser execution trace and replay scripts in Node",
    )
    parser.add_argument(
        "--vendor-sensor",
        default="",
        help="vendor name for sensor simulation (cloudflare/datadome/akamai/perimeterx)",
    )
    parser.add_argument(
        "--byte-compare",
        action="store_true",
        help="compare captured request bytes with replayed request bytes",
    )
    parser.add_argument(
        "--wasm-pseudocode",
        action="store_true",
        help="decompile local .wasm to C-style pseudocode (auto-installs wabt)",
    )
    parser.add_argument(
        "--mitm-capture",
        default=None,
        help="capture TLS-decrypted traffic for this URL with mitmproxy",
    )
    parser.add_argument(
        "--mitm-output",
        default="mitm.log",
        help="mitmproxy flow output path",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        _self_test()
        return 0

    captures: list[dict[str, Any]] = []
    if args.capture:
        captures.extend(_load_capture(path) for path in args.capture)
    elif args.html:
        html = Path(args.html).read_text(encoding="utf-8")
        captures.append({"url": str(Path(args.html).resolve()), "html": html, "network": []})
    elif args.url:
        if run_browser_hook is None:
            print("deep_hook is not available", file=sys.stderr)
            return 2
        hook = run_browser_hook(
            args.url,
            headless=not args.no_headless,
            engine=args.engine,
            probe_patterns=[
                item.strip() for item in args.probe_patterns.split(",") if item.strip()
            ],
            wasm_hook=args.wasm_hook,
            native_probe=args.native_probe,
            wait_ms=args.wait_ms,
            timeout_ms=args.timeout_ms,
        )
        if not hook.ok:
            print(hook.error or "browser capture failed", file=sys.stderr)
            return 2
        captures.append(hook.to_dict())

    js = Path(args.js).read_text(encoding="utf-8") if args.js else None
    if not captures and not js:
        parser.error("one of --url, --capture, --html, --js is required")

    secrets = [item.strip() for item in args.secrets.split(",") if item.strip()] or None
    algorithms = [item.strip() for item in args.algorithms.split(",") if item.strip()]
    exclude_params = [item.strip() for item in args.exclude_params.split(",") if item.strip()]

    active_sender = None
    active_session = None
    if args.active_diff and captures:
        from smart_fetch import create_fetch_session

        session = create_fetch_session(
            {"fetch": {"backend": "auto", "auto_install": False}},
            min_interval=0.0,
        )
        active_session = session

        def active_sender(
            method: str,
            url: str,
            headers: dict[str, str] | None = None,
            data: Any = None,
            body: Any = None,
        ) -> tuple[int, str, dict[str, str]]:
            try:
                result_body, status, response_headers = session.request_json_with_meta(
                    method,
                    url,
                    headers=headers,
                    data=data,
                    json_body=body,
                    timeout=20.0,
                )
                import json as _json

                text = (
                    _json.dumps(result_body, ensure_ascii=False)
                    if result_body is not None
                    else ""
                )
                return int(status or 0), text, response_headers
            except Exception as exc:
                return 0, str(exc), {}

    try:
        report = run_auto(
            captures,
            js=js,
            js_url=args.js,
            secrets=secrets,
            algorithms=algorithms,
            brute_force=args.brute_secret,
            brute_max_length=args.brute_max,
            brute_charset=args.brute_charset,
            exclude_params=exclude_params or None,
            max_functions=args.max_functions,
            source_map_path=args.source_map,
            use_webcrack=args.webcrack,
            use_acorn=args.acorn,
            install_beautifier=args.install_beautifier,
            dynamic_decode=args.dynamic_decode,
            deep_deobfuscation=args.deep_deobfuscation,
            run_bundle=args.run_bundle,
            active_diff=True if args.active_diff else None,
            active_diff_sender=active_sender,
            auto_install=args.auto_install,
            knowledge_store=args.knowledge_store,
            replay_call_chain=args.replay_call_chain,
            symbolic=args.symbolic,
        )
    finally:
        if active_session is not None:
            active_session.close()
    if args.wasm:
        from wasm_hook import parse_wasm_imports_exports, run_wasm_probe

        wasm_bytes = Path(args.wasm).read_bytes()
        parsed = parse_wasm_imports_exports(wasm_bytes)
        wasm_report = {
            "parsed": parsed,
            "execution": run_wasm_probe(
                wasm_bytes,
                export_names=[item["name"] for item in parsed.get("exports", [])],
            ),
        }
        if args.wasm_pseudocode:
            from wasm_hook import decompile_wasm_pseudocode

            wasm_report["pseudocode"] = decompile_wasm_pseudocode(
                wasm_bytes,
                auto_install=True,
            )
        report["wasm_probe"] = wasm_report
    if args.mitm_capture:
        from byte_capture import capture_with_mitmproxy

        report["mitm_capture"] = capture_with_mitmproxy(
            args.mitm_capture,
            output=args.mitm_output,
            auto_install=True,
        )
    if args.cdp_probe and args.url:
        from cdp_probe import build_breakpoints_from_analysis, run_url_cdp_probe

        analysis = (report.get("deep_reverse") or {}).get("analysis") or {}
        breakpoints = build_breakpoints_from_analysis(analysis, args.js or "bundle.js")
        report["cdp_probe"] = run_url_cdp_probe(
            args.url,
            breakpoints,
            headless=not args.no_headless,
            engine=args.engine,
            wait_ms=args.cdp_wait_ms,
        ).to_dict()
    if args.cdp_return_probe and args.url:
        from cdp_probe import build_breakpoints_from_analysis, run_url_cdp_return_probe

        analysis = (report.get("deep_reverse") or {}).get("analysis") or {}
        breakpoints = build_breakpoints_from_analysis(analysis, args.js or "bundle.js")
        report["cdp_return_probe"] = run_url_cdp_return_probe(
            args.url,
            breakpoints,
            headless=not args.no_headless,
            engine=args.engine,
            wait_ms=args.cdp_wait_ms,
        ).to_dict()
    if args.coverage_probe and args.url:
        from coverage_probe import run_url_coverage_probe

        report["coverage_probe"] = run_url_coverage_probe(
            args.url,
            headless=not args.no_headless,
            engine=args.engine,
            wait_ms=args.cdp_wait_ms,
        ).to_dict()
    if args.concolic and js:
        from concolic_runner import run_concolic_function
        from deep_reverse import find_function_names

        names = find_function_names(js)[:5]
        report["concolic"] = [
            run_concolic_function(
                js,
                name,
                ["a=1&b=2&ts=1786000000"],
            ).to_dict()
            for name in names
        ]
    if args.replay_trace and args.url:
        from replay_trace import run_url_execution_trace

        report["replay_trace"] = run_url_execution_trace(
            args.url,
            headless=not args.no_headless,
            engine=args.engine,
            wait_ms=args.cdp_wait_ms,
        )
    if args.vendor_sensor and js:
        from vendor_sensor import simulate_vendor_sensor

        report["vendor_sensor"] = simulate_vendor_sensor(args.vendor_sensor, js)
    if args.byte_compare and captures:
        from byte_capture import build_request_bytes, compare_replay_bytes

        request = next(
            (
                item
                for item in (captures[0].get("hook") or {}).get("requests", []) or []
                if isinstance(item, dict) and item.get("url")
            ),
            {},
        )
        if request:
            captured = build_request_bytes(
                str(request.get("method", "GET") or "GET"),
                str(request.get("url", "") or ""),
                request.get("headers") or {},
            )
            replay = build_request_bytes(
                str(request.get("method", "GET") or "GET"),
                str(request.get("url", "") or ""),
                request.get("headers") or {},
            )
            report["byte_compare"] = compare_replay_bytes(captured, replay)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
