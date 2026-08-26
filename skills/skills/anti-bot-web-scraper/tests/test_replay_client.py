"""Tests for replaying reverse-lab signatures through ApiClient."""

from __future__ import annotations

import hashlib
import http.server
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from api_client import ApiClient  # noqa: E402
from replay_client import build_replay_spec, build_replay_specs  # noqa: E402
from web_data_pipeline import WebDataPipeline  # noqa: E402


class _Handler(http.server.BaseHTTPRequestHandler):
    last_query = ""

    def do_GET(self) -> None:
        _Handler.last_query = self.path
        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        pass


def _report(url: str, secret: str, payload: str) -> dict:
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    full_url = f"{url}?sign={expected}&a=1&b=2"
    return {
        "url": full_url,
        "capture": {
            "url": full_url,
            "hook": {"requests": [{"method": "GET", "url": full_url}]},
            "network": [],
        },
        "reverse_lab": {
            "signature_verifications": [
                {
                    "url": full_url,
                    "signature_param": "sign",
                    "pattern": "payload+secret",
                    "secret": secret,
                    "algorithm": "md5",
                    "payload": payload,
                    "verified": True,
                }
            ]
        },
    }


def test_build_replay_spec_computes_signature() -> None:
    secret = "replay-secret"
    payload = "a=1&b=2"
    report = _report("http://example.com/api", secret, payload)
    spec = build_replay_spec(report)
    context = spec.prepare_request(
        {
            "url": spec.url,
            "params": dict(spec.params or {}),
            "headers": dict(spec.headers or {}),
            "body": spec.body,
        }
    )
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    assert context["params"]["sign"] == expected


def test_replay_spec_fetches_through_api_client() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        secret = "session-secret"
        payload = "a=1&b=2"
        base = f"http://127.0.0.1:{server.server_port}/api"
        report = _report(base, secret, payload)
        spec = build_replay_spec(report)
        client = ApiClient(backend="standard", min_interval=0)
        try:
            data = client.fetch_spec(spec)
        finally:
            client.close()
        assert data == {"ok": True}
        expected = hashlib.md5((payload + secret).encode()).hexdigest()
        assert f"sign={expected}" in _Handler.last_query
    finally:
        server.shutdown()
        server.server_close()


def test_build_replay_specs_returns_all_verified() -> None:
    secret = "multi-secret"
    payload = "a=1&b=2"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    url = f"https://example.com/api?sign={expected}&a=1&b=2"
    report = {
        "url": url,
        "capture": {
            "url": url,
            "hook": {"requests": [{"method": "GET", "url": url}]},
            "network": [],
        },
        "reverse_lab": {
            "signature_verifications": [
                {
                    "url": url,
                    "signature_param": "sign",
                    "pattern": "payload+secret",
                    "secret": secret,
                    "algorithm": "md5",
                    "payload": payload,
                    "verified": True,
                },
                {
                    "url": url,
                    "signature_param": "sign",
                    "pattern": "secret+payload",
                    "secret": secret,
                    "algorithm": "md5",
                    "payload": payload,
                    "verified": True,
                },
            ]
        },
    }
    specs = build_replay_specs(report, [report["capture"]])
    assert len(specs) == 1
    assert specs[0].prepare_request is not None


def test_web_data_pipeline_discover_appends_replay_specs() -> None:
    secret = "pipeline-secret"
    payload = "a=1&b=2"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    url = f"https://example.com/api?sign={expected}&a=1&b=2"
    report = {
        "url": url,
        "capture": {
            "url": url,
            "hook": {"requests": [{"method": "GET", "url": url}]},
            "network": [],
        },
        "reverse_lab": {
            "signature_verifications": [
                {
                    "url": url,
                    "signature_param": "sign",
                    "pattern": "payload+secret",
                    "secret": secret,
                    "algorithm": "md5",
                    "payload": payload,
                    "verified": True,
                }
            ]
        },
    }
    pipeline = WebDataPipeline({"pages": [], "reverse": {"replay": True}})
    pipeline.replay_specs = build_replay_specs(report, [report["capture"]])
    specs = pipeline.discover()
    assert any(spec.source == "reverse-replay" for spec in specs)
