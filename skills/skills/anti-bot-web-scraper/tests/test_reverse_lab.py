"""Tests for the cross-request reverse engineering lab."""

from __future__ import annotations

import email.utils
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from deep_reverse import (  # noqa: E402
    ensure_webcrack,
    node_available,
    webcrack_available,
)
from reverse_lab import (  # noqa: E402
    analyze_capture_set,
    brute_force_secret,
    correlate_timestamps,
    diff_captured_requests,
    generate_device_fingerprint_python,
    generate_node_replay,
    generate_node_request_builder,
    generate_python_replay,
    generate_python_request_builder,
    response_error_signals,
    server_clock_offsets,
    signature_consistency,
    signature_coverage,
    storage_diff,
    tokenize_device_snapshot,
    verify_device_params,
    verify_js_against_captures,
    verify_signature_candidates,
)


def _capture(url: str, captured_at_ms: int | None = None, device: dict | None = None) -> dict:
    return {
        "url": url,
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": url,
                    "captured_at_ms": captured_at_ms,
                    "device": device,
                }
            ]
        },
        "network": [],
    }


def test_diff_captured_requests() -> None:
    captures = [
        _capture("https://example.com/api?sign=a&ts=1&a=1&b=2"),
        _capture("https://example.com/api?sign=b&ts=2&a=1&b=3"),
    ]
    diffs = diff_captured_requests(captures)
    assert len(diffs) == 1
    diff = diffs[0]
    assert diff.constant_params["a"] == "1"
    assert set(diff.changing_params) >= {"sign", "ts", "b"}
    assert "sign" in diff.signature_params
    assert "ts" in diff.timestamp_params


def test_timestamp_correlation_detects_seconds() -> None:
    ts = 1786000000
    capture = _capture(
        f"https://example.com/api?ts={ts}&a=1",
        captured_at_ms=ts * 1000 + 120,
    )
    rows = correlate_timestamps([capture])
    assert rows
    row = rows[0]
    assert row.unit == "seconds"
    assert abs(row.delta_ms - 120) < 2


def test_device_snapshot_tokenization() -> None:
    snapshot = {
        "navigator": {"userAgent": "Mozilla/5.0", "platform": "Win32"},
        "screen": {"width": 1920, "height": 1080},
        "canvas": "data:image/png;base64,abc",
    }
    tokens, fingerprint = tokenize_device_snapshot(snapshot)
    assert len(tokens) >= 3
    assert len(fingerprint) == 64
    assert any(token.name == "navigator.userAgent" for token in tokens)


def test_signature_verification_finds_md5_secret() -> None:
    secret = "s3cret"
    payload = "a=1&b=2"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    capture = _capture(f"https://example.com/api?sign={expected}&a=1&b=2")
    rows = verify_signature_candidates([capture], secrets=[secret, "wrong"], algorithms=["md5"])
    assert any(row.verified and row.secret == secret for row in rows)


def test_generate_python_replay() -> None:
    recipe = {
        "function_name": "genSign",
        "algorithm": "MD5",
        "parameter_order": ["a", "b"],
        "secret_keys": ["s3cret"],
        "encoding": "hex",
        "snippet": "genSign{...}",
        "line": 1,
        "confidence": 0.9,
    }
    code = generate_python_replay(recipe)
    assert "def build_signature" in code
    assert "hashlib.md5" in code
    assert "s3cret" in code


def test_reverse_lab_self_test_path() -> None:
    secret = "lab-secret"
    ts = 1786000000
    payload = "a=1&b=2&ts=1786000000"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    capture = _capture(
        f"https://example.com/api?sign={expected}&ts={ts}&a=1&b=2",
        captured_at_ms=ts * 1000 + 500,
        device={"navigator": {"userAgent": "Mozilla/5.0"}, "screen": {"width": 1920}},
    )
    report = analyze_capture_set([capture], secrets=[secret], algorithms=["md5"])
    assert report.summary["request_diffs"] == 1
    assert report.summary["timestamp_correlations"] == 1
    assert report.summary["verified_signatures"] >= 1


def test_webcrack_availability_is_boolean() -> None:
    assert webcrack_available() in {True, False}
    assert json.dumps({"webcrack": webcrack_available()})


def test_webcrack_install_check_is_offline() -> None:
    status = ensure_webcrack(install=False)
    if webcrack_available():
        assert status["ok"] is True
    else:
        assert status["ok"] is False
        assert "not installed" in status["error"]


def test_signature_verification_auto_extracts_secrets() -> None:
    secret = "storage-secret"
    payload = "a=1&b=2"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    capture = _capture(f"https://example.com/api?sign={expected}&a=1&b=2")
    capture["analysis"] = {
        "signature_recipes": [
            {"function_name": "genSign", "secret_keys": [secret], "algorithm": "MD5"}
        ]
    }
    rows = verify_signature_candidates([capture], algorithms=["md5"])
    assert any(row.verified and row.secret == secret for row in rows)


def test_generate_node_replay() -> None:
    code = generate_node_replay(
        {
            "function_name": "genSign",
            "algorithm": "HMAC-SHA256",
            "parameter_order": ["a", "b"],
            "secret_keys": ["s3cret"],
            "encoding": "hex",
            "snippet": "genSign{...}",
            "line": 1,
            "confidence": 0.9,
        }
    )
    assert "crypto.createHmac" in code
    assert "buildSignature" in code


def test_device_param_matches_fingerprint_hash() -> None:
    device = {
        "navigator": {"userAgent": "Mozilla/5.0", "platform": "Win32"},
        "screen": {"width": 1920, "height": 1080},
    }
    _tokens, fingerprint = tokenize_device_snapshot(device)
    url = f"https://example.com/api?device_id={fingerprint}"
    capture = _capture(url, device=device)
    matches = verify_device_params([capture])
    assert any(item.matched and item.algorithm == "sha256" for item in matches)


def test_server_clock_offset_from_response_header() -> None:
    captured_at_ms = 1_784_000_000_000
    url = "https://example.com/api?a=1"
    capture = {
        "url": url,
        "hook": {"requests": [{"method": "GET", "url": url, "captured_at_ms": captured_at_ms}]},
        "network": [
            {
                "method": "GET",
                "url": url,
                "response_headers": {"date": "Tue, 01 Jan 2030 00:00:00 GMT"},
            }
        ],
    }
    rows = server_clock_offsets([capture])
    assert rows
    row = rows[0]
    assert row.header == "date"
    assert row.server_time_ms == 1_893_456_000_000
    assert row.delta_ms == row.server_time_ms - captured_at_ms


def test_signature_verification_includes_headers() -> None:
    secret = "header-secret"
    payload = "a=1&b=2&X-Token=hdr"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    url = f"https://example.com/api?sign={expected}&a=1&b=2"
    capture = {
        "url": url,
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": url,
                    "headers": {"X-Token": "hdr"},
                }
            ]
        },
        "network": [],
    }
    rows = verify_signature_candidates([capture], secrets=[secret], algorithms=["md5"])
    assert any(row.verified and "X-Token=hdr" in row.payload for row in rows)


def test_signature_consistency_counts_multiple_samples() -> None:
    secret = "consistent"
    captures = []
    for ts in (1_786_000_000, 1_786_000_060):
        payload = f"a=1&b=2&ts={ts}"
        expected = hashlib.md5((payload + secret).encode()).hexdigest()
        captures.append(_capture(f"https://example.com/api?sign={expected}&ts={ts}&a=1&b=2"))
    rows = signature_consistency(captures, secrets=[secret], algorithms=["md5"])
    assert rows
    row = next(item for item in rows if item.secret == secret)
    assert row.verified_samples == 2
    assert row.total_samples == 2


def test_brute_force_secret_finds_short_secret() -> None:
    secret = "ab"
    payload = "a=1"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    capture = _capture(f"https://example.com/api?sign={expected}&a=1")
    found = brute_force_secret(
        [capture],
        max_length=2,
        charset="ab",
        algorithms=["md5"],
    )
    assert secret in found


def test_generate_python_request_builder() -> None:
    secret = "builder-secret"
    payload = "a=1&b=2"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    url = f"https://example.com/api?sign={expected}&a=1&b=2"
    request = {"method": "GET", "url": url}
    verification = next(
        item
        for item in verify_signature_candidates(
            [_capture(url)],
            secrets=[secret],
            algorithms=["md5"],
        )
        if item.verified
    )
    code = generate_python_request_builder(request, verification)
    assert "def build_request" in code
    assert "hashlib.md5" in code
    assert "https://example.com/api" in code


def test_generate_node_request_builder() -> None:
    secret = "node-builder-secret"
    payload = "a=1&b=2"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    url = f"https://example.com/api?sign={expected}&a=1&b=2"
    request = {"method": "GET", "url": url}
    verification = next(
        item
        for item in verify_signature_candidates(
            [_capture(url)],
            secrets=[secret],
            algorithms=["md5"],
        )
        if item.verified
    )
    code = generate_node_request_builder(request, verification)
    assert "function buildRequest" in code
    assert "crypto.createHash" in code
    assert "https://example.com/api" in code


def test_generate_device_fingerprint_python() -> None:
    code = generate_device_fingerprint_python()
    assert "def build_fingerprint" in code
    assert "hashlib.sha256" in code
    namespace: dict[str, Any] = {}
    exec(code, namespace)
    fingerprint = namespace["build_fingerprint"](
        {"navigator": {"userAgent": "Mozilla/5.0"}, "screen": {"width": 1920}}
    )
    assert len(fingerprint) == 64


def test_signature_verification_flattens_nested_json() -> None:
    secret = "nested-secret"
    payload = "user.id=1&user.name=alice"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    capture = {
        "url": "https://example.com/api",
        "hook": {
            "requests": [
                {
                    "method": "POST",
                    "url": "https://example.com/api",
                    "body": {"user": {"id": 1, "name": "alice"}, "sign": expected},
                }
            ]
        },
        "network": [],
    }
    rows = verify_signature_candidates([capture], secrets=[secret], algorithms=["md5"])
    assert any(row.verified and "user.id=1" in row.payload for row in rows)


def test_storage_diff_finds_rotating_values() -> None:
    first = _capture("https://example.com/api?a=1")
    first["hook"]["requests"][0]["storage"] = {
        "local": {"token": "aaa", "device_id": "dev-1"},
        "session": {},
    }
    second = _capture("https://example.com/api?a=1")
    second["hook"]["requests"][0]["storage"] = {
        "local": {"token": "bbb", "device_id": "dev-1"},
        "session": {},
    }
    rows = storage_diff([first, second])
    token_row = next(item for item in rows if item.key == "token")
    device_row = next(item for item in rows if item.key == "device_id")
    assert token_row.changed is True
    assert device_row.changed is False


def test_js_replay_finds_signature_function() -> None:
    if not node_available():
        pytest.skip("node is not available")
    js = (
        'function sign(params){const crypto=require("crypto");'
        'return crypto.createHash("md5").update(String(params.a)+String(params.b)).digest("hex");}'
    )
    expected = hashlib.md5(b"12").hexdigest()
    capture = _capture(f"https://example.com/api?sign={expected}&a=1&b=2")
    rows = verify_js_against_captures(js, [capture], max_functions=5)
    assert any(
        row.kind == "signature" and row.matched and row.function_name == "sign" for row in rows
    )


def test_js_replay_finds_device_function() -> None:
    if not node_available():
        pytest.skip("node is not available")
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 Chrome/124 Safari/537.36"
    expected = hashlib.sha256(ua.encode()).hexdigest()
    js = (
        'function deviceId(){const crypto=require("crypto");'
        'return crypto.createHash("sha256").update(navigator.userAgent).digest("hex");}'
    )
    capture = _capture(f"https://example.com/api?device_id={expected}")
    rows = verify_js_against_captures(js, [capture], max_functions=5)
    assert any(
        row.kind == "device" and row.matched and row.function_name == "deviceId" for row in rows
    )


def test_js_replay_timestamp_tolerance() -> None:
    if not node_available():
        pytest.skip("node is not available")
    js = "function genTs(){return Math.floor(Date.now()/1000)}"
    expected = str(int(time.time()))
    capture = _capture(f"https://example.com/api?ts={expected}")
    rows = verify_js_against_captures(js, [capture], max_functions=5)
    assert any(
        row.kind == "timestamp" and row.matched and row.function_name == "genTs" for row in rows
    )


def test_signature_coverage_lists_signed_and_unsigned_params() -> None:
    secret = "coverage-secret"
    signed_payload = "a=1&b=2"
    expected = hashlib.md5((signed_payload + secret).encode()).hexdigest()
    capture = _capture(f"https://example.com/api?sign={expected}&ts=1786000000&a=1&b=2")
    verifications = verify_signature_candidates(
        [capture],
        secrets=[secret],
        algorithms=["md5"],
        exclude_params=["ts"],
    )
    rows = signature_coverage([capture], verifications)
    assert rows
    row = rows[0]
    assert set(row.signed_params) >= {"a", "b"}
    assert "ts" in row.unsigned_params


def test_response_error_oracle_hints_signature() -> None:
    capture = {
        "url": "https://example.com/api",
        "hook": {"requests": []},
        "network": [
            {
                "method": "POST",
                "url": "https://example.com/api",
                "status": 403,
                "body": '{"message":"signature expired"}',
            }
        ],
    }
    rows = response_error_signals([capture])
    assert rows
    row = rows[0]
    assert row.status == 403
    assert row.hint == "signature"


def test_signature_verification_semicolon_serialization() -> None:
    secret = "semi-secret"
    payload = "a=1;b=2"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    capture = _capture(f"https://example.com/api?sign={expected}&a=1&b=2")
    rows = verify_signature_candidates([capture], secrets=[secret], algorithms=["md5"])
    assert any(row.verified and ";" in row.payload for row in rows)


def test_server_synced_timestamp_flag() -> None:
    ts = 1_786_000_000
    captured_at = ts * 1000 + 500
    url = f"https://example.com/api?ts={ts}"
    capture = {
        "url": url,
        "hook": {"requests": [{"method": "GET", "url": url, "captured_at_ms": captured_at}]},
        "network": [
            {
                "method": "GET",
                "url": url,
                "response_headers": {"date": email.utils.formatdate(ts + 1, usegmt=True)},
            }
        ],
    }
    report = analyze_capture_set([capture])
    assert report.timestamp_correlations
    assert report.timestamp_correlations[0].server_synced is True


def test_signature_verification_uses_raw_json_body() -> None:
    secret = "raw-secret"
    raw = '{"a":1,"b":2}'
    expected = hashlib.md5((raw + secret).encode()).hexdigest()
    url = f"https://example.com/api?sign={expected}"
    capture = {
        "url": url,
        "hook": {
            "requests": [
                {
                    "method": "POST",
                    "url": url,
                    "body": {"a": 1, "b": 2},
                }
            ]
        },
        "network": [],
    }
    rows = verify_signature_candidates([capture], secrets=[secret], algorithms=["md5"])
    assert any(row.verified and row.payload == raw for row in rows)


def test_header_timestamp_correlation() -> None:
    ts = 1_786_000_000
    url = "https://example.com/api?a=1"
    capture = {
        "url": url,
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": url,
                    "captured_at_ms": ts * 1000 + 500,
                    "headers": {"X-Timestamp": str(ts)},
                }
            ]
        },
        "network": [],
    }
    rows = correlate_timestamps([capture])
    assert any(row.param == "X-Timestamp" and row.unit == "seconds" for row in rows)


def test_js_bundle_secret_hints_auto_verify() -> None:
    secret = "bundleSecret123"
    expected = hashlib.md5(("a=1" + secret).encode()).hexdigest()
    js = f'var appKey="{secret}";'
    capture = _capture(f"https://example.com/api?sign={expected}&a=1")
    report = analyze_capture_set([capture], js_bundle=js, algorithms=["md5"])
    assert report.summary["verified_signatures"] >= 1
