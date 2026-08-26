"""Tests for the deep reverse-engineering analyzer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from deep_hook import deep_hook_js  # noqa: E402
from deep_reverse import (  # noqa: E402
    acorn_available,
    analyze_capture,
    analyze_device_fingerprint,
    analyze_js,
    analyze_request_sites,
    analyze_signature_recipes,
    analyze_timestamp_fields,
    cross_script_refs,
    decode_base64_calls,
    decode_js_escapes,
    decode_string_arrays_dynamic,
    decode_vlq_mappings,
    deobfuscate_js,
    detect_bundle_framework,
    detect_obfuscation,
    ensure_acorn,
    ensure_jsbeautifier,
    evaluate_js,
    extract_secret_hints,
    extract_webpack_modules,
    find_signature_candidates,
    find_source_mapping_url,
    jsbeautifier_available,
    map_analysis_lines,
    map_position,
    node_available,
    resolve_string_arrays,
    run_signature_function,
    unwrap_eval_calls,
)


def test_decode_escapes_and_base64() -> None:
    js = r'var a = "\x68\x69"; var b = atob("aGVsbG8=");'
    decoded = decode_base64_calls(decode_js_escapes(js))
    assert '"hi"' in decoded
    assert '"hello"' in decoded


def test_resolve_string_arrays() -> None:
    js = 'var _0xabc=["sign","token"]; var s = _0xabc[1];'
    out = resolve_string_arrays(js)
    assert '"token"' in out
    assert "_0xabc[1]" not in out


def test_unwrap_eval_calls() -> None:
    js = 'eval("var x=1;");'
    out = unwrap_eval_calls(js)
    assert "var x=1;" in out


def test_deobfuscate_js_resolves_packed_array() -> None:
    js = r'var _0x=["\x73\x69\x67\x6e","\x74\x6f\x6b\x65\x6e"]; var s=_0x[1];'
    result = deobfuscate_js(js)
    assert '"token"' in result.output


def test_detect_obfuscation_scores_packed_code() -> None:
    profile = detect_obfuscation('var _0xabc=["a"];eval("x");')
    assert profile.score >= 20
    assert any(signal.name == "packed_arrays" for signal in profile.signals)


def test_request_sites_expose_dynamic_fields() -> None:
    js = (
        'fetch("/api/x?sign="+Date.now(),'
        '{method:"POST",headers:{"X-Token":getToken()},'
        'body:JSON.stringify({nonce:"n",sig:md5("a")})});'
    )
    sites = analyze_request_sites(js)
    assert sites
    kinds = {field.kind for site in sites for field in site.dynamic_fields}
    assert "signature" in kinds
    assert "timestamp" in kinds


def test_signature_candidates_are_located() -> None:
    js = 'function genSign(a,b){return md5(a+b);} genSign("x","y");'
    candidates = find_signature_candidates(js)
    assert any(candidate.name == "genSign" for candidate in candidates)
    assert any("MD5" in candidate.algorithm for candidate in candidates)


def test_analyze_capture_extracts_scripts_and_candidates() -> None:
    html = '<html><script>function sign(){return md5("x")}</script></html>'
    report = analyze_capture({"url": "https://example.com/", "html": html, "network": []})
    assert report.summary["scripts"] == 1
    assert report.summary["signature_candidates"] >= 1


def test_analyze_capture_keeps_runtime_hook() -> None:
    report = analyze_capture(
        {
            "url": "https://example.com/",
            "html": "",
            "network": [],
            "hook": {
                "requests": [
                    {
                        "kind": "fetch",
                        "url": "https://example.com/api?sign=x",
                        "stack": ["at build (bundle.js:1:1)"],
                        "device": {"navigator": {"userAgent": "Mozilla/5.0"}},
                    }
                ]
            },
        }
    )
    assert report.summary["hook_requests"] == 1
    assert report.hook["requests"][0]["url"].endswith("/api?sign=x")


def test_node_evaluate_when_available() -> None:
    if not node_available():
        pytest.skip("node is not available")
    result = evaluate_js("({ok:true, n:1+1})")
    assert result["ok"] is True
    assert result["value"] == {"ok": True, "n": 2}


def test_node_run_signature_function_when_available() -> None:
    if not node_available():
        pytest.skip("node is not available")
    js = 'function genSign(a,b){return a+":"+b;}'
    result = run_signature_function(js, "genSign", ["x", "y"])
    assert result["ok"] is True
    assert result["value"] == "x:y"


def test_node_browser_stubs_when_available() -> None:
    if not node_available():
        pytest.skip("node is not available")
    result = evaluate_js("navigator.userAgent + '|' + screen.width")
    assert result["ok"] is True
    assert "Mozilla" in result["value"]
    assert "1920" in result["value"]
    result2 = run_signature_function(
        "function deviceTag(){return navigator.userAgent.slice(0, 12);}",
        "deviceTag",
    )
    assert result2["ok"] is True
    assert result2["value"] == "Mozilla/5.0 "


def test_device_fingerprint_usage_is_detected() -> None:
    js = 'const ua = navigator.userAgent; canvas.getContext("2d").toDataURL();'
    fields = analyze_device_fingerprint(js)
    names = {field.name for field in fields}
    assert "navigator.userAgent" in names
    assert "canvas" in names


def test_timestamp_unit_inference() -> None:
    seconds = analyze_timestamp_fields("Math.floor(Date.now()/1000)")
    assert seconds
    assert seconds[0].unit == "seconds"
    base36 = analyze_timestamp_fields("const ts = Date.now().toString(36);")
    assert base36
    assert base36[0].unit == "base36"


def test_signature_recipe_extracts_secret_and_order() -> None:
    js = 'function genSign(a,b){var key="secret";return md5(["a","b",key].sort().join(""));}'
    candidates = find_signature_candidates(js)
    recipes = analyze_signature_recipes(js, candidates)
    recipe = next(item for item in recipes if item.function_name == "genSign")
    assert "secret" in recipe.secret_keys
    assert recipe.parameter_order


def test_deep_hook_js_contains_wrappers() -> None:
    hook = deep_hook_js()
    assert "window.fetch" in hook
    assert "XMLHttpRequest.prototype.open" in hook
    assert "setRequestHeader" in hook
    assert "NativeWebSocket" in hook
    assert "sendBeacon" in hook
    assert "EventSource" in hook
    assert "performanceResources" in hook
    assert "__deep_reverse_hook" in hook
    assert "enumerable: false" in hook
    assert "resource_timing" in hook
    assert "cookies:" in hook


def test_deep_hook_js_supports_random_non_enumerable_global() -> None:
    custom = deep_hook_js("__custom_deep_hook_abc")
    assert "__custom_deep_hook_abc" in custom
    assert 'window["__custom_deep_hook_abc"]' in custom
    assert "Object.defineProperty" in custom


def test_data_flow_links_sources_to_request_params() -> None:
    js = (
        "function genSign(x){return md5(x)}"
        "var ua=navigator.userAgent;"
        "var sig=genSign(ua);"
        'fetch("/api?device="+ua,{headers:{"X-Token":sig}});'
    )
    analysis = analyze_js(js)
    links = analysis.data_flow
    assert any(
        link.source_kind == "device" and link.target == "device" and link.variable == "ua"
        for link in links
    )
    assert any(
        link.source_kind == "signature" and link.target == "X-Token" and link.variable == "sig"
        for link in links
    )


def test_source_map_vlq_decoding_and_mapping() -> None:
    rows = decode_vlq_mappings("AAAA")
    assert rows
    assert rows[0]["generated_line"] == 0
    assert rows[0]["source_index"] == 0
    source_map = {
        "version": 3,
        "sources": ["app.js"],
        "names": ["sign"],
        "mappings": "AAAA",
    }
    mapped = map_position(source_map, 1, 0)
    assert mapped["source"] == "app.js"
    assert mapped["original_line"] == 1


def test_source_mapping_url_detection() -> None:
    assert find_source_mapping_url("//# sourceMappingURL=app.js.map") == "app.js.map"
    assert find_source_mapping_url("var a = 1;") is None


def test_obfuscation_detects_long_identifiers() -> None:
    js = "var aVeryLongIdentifierNameForObfuscationPurpose = 1;"
    profile = detect_obfuscation(js)
    assert any(signal.name == "long_identifiers" for signal in profile.signals)


def test_bundle_framework_detection() -> None:
    js = "window.webpackJsonp=[];" "function(module, exports, __webpack_require__){return 1;}"
    bundle = detect_bundle_framework(js)
    assert "webpack" in bundle["frameworks"]
    assert bundle["webpack_modules"] >= 1


def test_dynamic_string_decoder_resolves_obfuscated_array() -> None:
    if not node_available():
        pytest.skip("node is not available")
    js = 'function _0xdec(i){var a=["hello","world"];return a[i];}' "var x=_0xdec(0);"
    result = decode_string_arrays_dynamic(js, max_indices=4)
    assert '"hello"' in result.output
    assert "_0xdec(0)" not in result.output


def test_webpack_module_table_extraction() -> None:
    js = (
        '{"123":function(module,exports,__webpack_require__){'
        "/*! ./src/a.js */ return 1;},"
        '"456":function(module,exports,__webpack_require__){return 2;}}'
    )
    detail = extract_webpack_modules(js)
    assert "123" in detail["ids"]
    assert "456" in detail["ids"]
    assert detail["module_count"] == 2
    assert any("./src/a.js" in name for name in detail["named_modules"])


def test_cross_script_references() -> None:
    sources = [
        {"name": "a.js", "content": "function genSign(x){return x}"},
        {"name": "b.js", "content": "genSign(1)"},
    ]
    refs = cross_script_refs(sources)
    assert any(
        item["function"] == "genSign"
        and item["defined_in"] == "a.js"
        and item["referenced_in"] == "b.js"
        for item in refs
    )


def test_map_analysis_lines_returns_original_positions() -> None:
    js = "function genSign(x){return x}"
    analysis = analyze_js(js)
    source_map = {
        "version": 3,
        "sources": ["src/app.js"],
        "names": [],
        "mappings": "AAAA",
    }
    mapped = map_analysis_lines(analysis, source_map)
    signature_rows = [item for item in mapped if item["kind"] == "signature_candidate"]
    assert signature_rows
    assert signature_rows[0]["source"] == "src/app.js"
    assert signature_rows[0]["original_line"] == 1


def test_extract_secret_hints_from_js_literals() -> None:
    js = 'var appKey="abc12345"; const signSecret="xyz789"; var normal=1;'
    secrets = extract_secret_hints(js)
    assert "abc12345" in secrets
    assert "xyz789" in secrets
    assert "1" not in secrets


def test_jsbeautifier_and_acorn_offline_checks() -> None:
    beautify_status = ensure_jsbeautifier(install=False)
    assert beautify_status["ok"] is jsbeautifier_available()
    acorn_status = ensure_acorn(install=False)
    assert acorn_status["ok"] is acorn_available()
