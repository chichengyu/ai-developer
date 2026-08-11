"""Tests for the mandatory deep-reverse chain in the web data pipeline."""

from __future__ import annotations

import hashlib
import http.server
import json
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from browser_session import BrowserSession, PageCapture  # noqa: E402
from deep_reverse import analyze_capture  # noqa: E402
from reverse_lab import build_reverse_retry_requests  # noqa: E402
from web_data_pipeline import WebDataPipeline  # noqa: E402


def test_browser_session_deep_hook_is_opt_in_for_stealth() -> None:
    class FakeContext:
        def __init__(self) -> None:
            self.scripts: list[str] = []

        def add_init_script(self, script: str) -> None:
            self.scripts.append(script)

    session = BrowserSession(headless=True)
    session.context = FakeContext()
    session._install_deep_hook_if_enabled()
    assert session.context.scripts == []

    enabled = BrowserSession(headless=True, deep_hook=True)
    enabled.context = FakeContext()
    enabled._install_deep_hook_if_enabled()
    assert any("__deep_reverse_hook" in script for script in enabled.context.scripts)
    assert enabled.deep_hook_global in enabled.context.scripts[0]
    assert session.deep_hook_global != enabled.deep_hook_global


def test_web_pipeline_reverse_hook_is_adaptive_by_default() -> None:
    pipeline = WebDataPipeline({"pages": []})
    assert pipeline._reverse_hook_mode() == "adaptive"
    assert pipeline._reverse_hook_enabled() is True
    assert (
        WebDataPipeline({"pages": [], "reverse": {"hook": False}})._reverse_hook_mode()
        == "disabled"
    )
    assert (
        WebDataPipeline(
            {"pages": [], "reverse": {"stealth": "ultimate"}}
        )._reverse_hook_mode()
        == "disabled"
    )
    assert (
        WebDataPipeline({"pages": [], "reverse": {"hook": True}})._reverse_hook_mode()
        == "always"
    )


def test_browser_session_captures_deep_hook_provenance() -> None:
    class FakePage:
        def evaluate(self, script: str) -> dict[str, object]:
            assert session.deep_hook_global in script
            return {
                "requests": [
                    {
                        "url": "https://example.com/api?sign=x",
                        "stack": ["at build (bundle.js:1:1)"],
                    }
                ]
            }

    session = BrowserSession(headless=True)
    session.page = FakePage()
    hook = session.capture_deep_hook()
    assert hook["requests"][0]["url"].endswith("/api?sign=x")


def test_page_capture_to_dict_includes_reverse_data() -> None:
    capture = PageCapture(
        url="https://example.com/",
        html="<script>function genSign(a,b){return md5(a+b);}</script>",
        network=[],
        storage={"local": {"token": "abc"}},
        hook={"requests": [{"url": "https://example.com/api?sign=x"}]},
    )
    data = capture.to_dict(include_html=True)
    assert data["html"].startswith("<script>")
    assert data["storage"] == {"local": {"token": "abc"}}
    assert data["hook"]["requests"][0]["url"].endswith("/api?sign=x")


def test_reverse_chain_feeds_deep_hook_into_lab() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pipeline = WebDataPipeline(
            {"pages": [], "reverse_output": str(root / "reverse.json")},
            output=root / "records.json",
        )
        pipeline.captures = [
            PageCapture(
                url="https://example.com/",
                html=(
                    '<html><script>function genSign(a,b){return md5(a+b);}'
                    'fetch("/api?sign="+genSign("x","y"));</script></html>'
                ),
                network=[],
                hook={
                    "requests": [
                        {
                            "method": "GET",
                            "url": "https://example.com/api?sign=x&ts=1786000000",
                            "captured_at_ms": 1786000000500,
                            "device": {
                                "navigator": {
                                    "userAgent": "Mozilla/5.0",
                                    "platform": "Win32",
                                },
                                "screen": {"width": 1920, "height": 1080},
                            },
                        }
                    ]
                },
                storage={"local": {"token": "abc"}},
            )
        ]
        summary = pipeline._run_reverse_chain()
        assert summary["pages"] == 1
        assert summary["signature_candidates"] >= 1
        assert summary["signature_recipes"] >= 1
        assert summary["hook_requests"] == 1
        assert pipeline.reverse_lab_report is not None
        assert pipeline.reverse_lab_report["summary"]["captures"] == 1
        assert pipeline.reverse_lab_report["summary"]["fingerprint_tokens"] >= 1
        assert (root / "reverse.json").exists()


def test_reverse_retry_requests_built_from_signature_recipe() -> None:
    html = (
        '<html><script>function genSign(a,b){var secretKey="s3cret";'
        'return md5(a+b+secretKey);}'
        'fetch("/api?sign="+genSign("x","y")+"&ts=123");</script></html>'
    )
    capture = {
        "url": "https://example.com/",
        "html": html,
        "network": [],
        "hook": {},
    }
    report = analyze_capture(capture)
    capture["analysis"] = report.to_dict()["analysis"]
    requests = build_reverse_retry_requests([capture], max_requests=4)
    assert requests
    assert all(item["signature_param"] == "sign" for item in requests)
    assert all(item["signature_source"] == "recipe" for item in requests)
    assert all(item["url"].startswith("https://example.com/api") for item in requests)


def test_reverse_retry_requests_brute_force_short_secret() -> None:
    secret = "ab"
    ts = 1786000000
    payload = "a=1&b=2&ts=1786000000"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    capture = {
        "url": "https://example.com/",
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": (
                        f"https://example.com/api?a=1&b=2&ts={ts}&sign={expected}"
                    ),
                    "captured_at_ms": ts * 1000,
                }
            ]
        },
        "network": [],
        "analysis": {"request_sites": [], "signature_recipes": []},
    }
    requests = build_reverse_retry_requests(
        [capture],
        max_requests=8,
        brute_force=True,
        brute_max_length=2,
    )
    assert requests
    assert any(item["signature_source"] == "brute_force" for item in requests)


def test_adaptive_hook_allowed_is_per_page_not_run_level() -> None:
    pipeline = WebDataPipeline({"pages": []})
    assert pipeline._adaptive_hook_allowed(None) is True
    assert (
        pipeline._adaptive_hook_allowed(
            {"blocked": False, "primary_kind": None, "findings": []}
        )
        is True
    )
    assert (
        pipeline._adaptive_hook_allowed(
            {
                "blocked": False,
                "primary_kind": None,
                "findings": [{"kind": "cookie_consent_wall"}],
            }
        )
        is False
    )
    pipeline.adaptive_stealth_switched = True
    assert (
        pipeline._adaptive_hook_allowed(
            {"blocked": False, "primary_kind": None, "findings": []}
        )
        is True
    )
    assert (
        pipeline._adaptive_hook_allowed(
            {"blocked": True, "primary_kind": None, "findings": []}
        )
        is False
    )


def test_reverse_retry_recovers_blocked_capture_automatically() -> None:
    blocked_html = (
        '<html><body>blocked</body><script>'
        'function genSign(a,b){var secretKey="s3cret";return md5(a+b+secretKey);}'
        'fetch("/api?sign="+genSign("x","y")+"&ts=123");'
        "</script></html>"
    )

    class ReverseRetryHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/":
                body = blocked_html.encode()
                self.send_response(403)
            elif self.path.startswith("/api"):
                query = urllib.parse.parse_qs(
                    urllib.parse.urlsplit(self.path).query
                )
                if query.get("sign"):
                    body = json.dumps({"ok": True, "items": [1]}).encode()
                    self.send_response(200)
                else:
                    body = b'{"error":"bad sign"}'
                    self.send_response(403)
            else:
                body = b"not found"
                self.send_response(404)
            self.send_header(
                "Content-Type",
                "application/json" if self.path.startswith("/api") else "text/html",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ReverseRetryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline = WebDataPipeline(
                {
                    "pages": [f"{base}/"],
                    "security": {"escalate_to_browser": False},
                    "api": {
                        "min_interval": 0.0,
                        "max_retries": 0,
                        "include_static": False,
                        "include_captured": True,
                    },
                    "processing": {},
                    "reverse_output": str(root / "reverse.json"),
                },
                output=root / "records.json",
            )
            summary = pipeline.run()
            assert summary["reverse_retry"]["blocked"] == 1
            assert summary["reverse_retry"]["requests"] >= 1
            assert summary["reverse_retry"]["succeeded"] == 1
            assert len(pipeline.captures) >= 2
            recovered = [
                capture
                for capture in pipeline.captures
                if capture.url.startswith(f"{base}/api")
            ]
            assert recovered
            assert recovered[0].network[0].json_data == {"ok": True, "items": [1]}
    finally:
        server.shutdown()
        server.server_close()


def test_reverse_retry_recovers_blocked_api_automatically() -> None:
    page_html = (
        '<html><script>'
        'function genSign(a,b){var secretKey="s3cret";return md5(a+b+secretKey);}'
        'fetch("/api?sign=old&ts=123");'
        "</script></html>"
    )

    class ApiReverseRetryHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/":
                body = page_html.encode()
                self.send_response(200)
            elif self.path.startswith("/api"):
                query = urllib.parse.parse_qs(
                    urllib.parse.urlsplit(self.path).query
                )
                ts_values = query.get("ts") or []
                fresh = bool(
                    ts_values
                    and ts_values[0].isdigit()
                    and int(ts_values[0]) > time.time() - 1000
                )
                if query.get("sign") and fresh:
                    body = json.dumps({"items": [{"id": 1, "name": "api"}]}).encode()
                    self.send_response(200)
                else:
                    body = b'{"error":"stale signature"}'
                    self.send_response(403)
            else:
                body = b"not found"
                self.send_response(404)
            self.send_header(
                "Content-Type",
                "application/json" if self.path.startswith("/api") else "text/html",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ApiReverseRetryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline = WebDataPipeline(
                {
                    "pages": [f"{base}/"],
                    "security": {"escalate_to_browser": False},
                    "api": {
                        "min_interval": 0.0,
                        "max_retries": 0,
                        "block_retries": 0,
                        "include_static": True,
                        "include_captured": False,
                    },
                    "processing": {
                        "steps": [
                            {"op": "select", "params": {"fields": ["id", "name"]}},
                        ]
                    },
                    "reverse_output": str(root / "reverse.json"),
                },
                output=root / "records.json",
            )
            summary = pipeline.run()
            assert summary["api_specs"] >= 1
            assert summary["reverse_retry"]["api_blocked"] >= 1
            assert summary["reverse_retry"]["api_succeeded"] == 1
            assert summary["processed_records"] >= 1
    finally:
        server.shutdown()
        server.server_close()


def test_web_data_pipeline_runs_reverse_chain_mandatorily() -> None:
    class ReverseHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = (
                b'<html><body><script>function genSign(a,b){return md5(a+b);}'
                b'fetch("/api?sign="+genSign("x","y"));</script></body></html>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ReverseHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline = WebDataPipeline(
                {
                    "pages": [f"http://127.0.0.1:{server.server_port}/"],
                    "api": {
                        "min_interval": 0.0,
                        "max_retries": 0,
                        "include_static": False,
                        "include_captured": False,
                    },
                    "processing": {},
                    "reverse_output": str(root / "reverse.json"),
                },
                output=root / "records.json",
            )
            summary = pipeline.run()
            assert summary["reverse_output"] == str(root / "reverse.json")
            assert summary["reverse"]["pages"] == 1
            assert summary["reverse"]["hook_mode"] == "adaptive"
            assert summary["reverse"]["hook_enabled"] is True
            assert summary["reverse"]["stealth_mode"] == "adaptive"
            assert summary["reverse"]["signature_candidates"] >= 1
            assert summary["reverse"]["reverse_lab"]["captures"] == 1

            report = json.loads((root / "reverse.json").read_text(encoding="utf-8"))
            assert report["mode"] == "mandatory"
            assert len(report["per_page"]) == 1
            assert report["reverse_lab"]["summary"]["captures"] == 1
    finally:
        server.shutdown()
        server.server_close()
