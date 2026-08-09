"""Direct tests for modules without prior direct unit coverage."""

from __future__ import annotations

import http.server
import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from acceptance_suite import (  # noqa: E402
    AcceptanceTarget,
    _LocalHandler,
    _skip_reason,
    run_acceptance,
)
from api_analyzer import analyze_captures, save_manifest  # noqa: E402
from browser_session import FingerprintOptions, NetworkEntry, PageCapture  # noqa: E402
from current_ip import collect  # noqa: E402
from data_processor import get_path, load_records, process_records, save_records  # noqa: E402
from media_parser import choose_best_variant, extract_media_urls, parse_m3u8  # noqa: E402
from nopecha_probe import _has_clearance, _public_ipv4, extract_page_ip  # noqa: E402
from scrape_guard import (  # noqa: E402
    AdaptiveThrottle,
    RequestPacer,
    RetryPolicy,
    RobotsDenied,
    RobotsPolicy,
    parse_retry_after,
)
from web_data_pipeline import (  # noqa: E402
    WebDataPipeline,
    _build_captcha_solver,
    _read_config,
    _SelfTestHandler,
    _unwrap_data,
)


def test_api_analyzer_manifest_and_save() -> None:
    capture = {
        "url": "https://example.com/list",
        "network": [
            {
                "method": "GET",
                "url": "https://example.com/api/items?page=1",
                "resource_type": "fetch",
                "status": 200,
                "request_headers": {"Authorization": "Bearer secret", "X-Token": "abc"},
                "json_data": {"items": [{"id": 1}], "total": 3, "hasMore": True},
            }
        ],
        "analysis": {
            "api_endpoints": [
                {"method": "GET", "url": "https://example.com/api/config", "source": "script"}
            ],
            "pagination": {},
        },
    }
    manifest = analyze_captures([capture])
    assert manifest.summary["endpoints"] >= 1
    assert manifest.pagination is not None
    assert manifest.pagination["type"] == "page"
    assert "items" in manifest.data_paths
    assert manifest.auth_headers["authorization"] == "<redacted>"

    with tempfile.TemporaryDirectory() as tmp:
        path = save_manifest(manifest, Path(tmp) / "manifest.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["sources"] == ["https://example.com/list"]


def test_browser_session_data_models() -> None:
    options = FingerprintOptions.from_dict(
        {
            "user_agent": "Mozilla/5.0 Test",
            "locale": "en-US",
            "timezone_id": "UTC",
            "languages": ["en-US", "en"],
            "hardware_concurrency": 4,
        }
    )
    kwargs = options.to_context_kwargs()
    assert kwargs["user_agent"] == "Mozilla/5.0 Test"
    assert kwargs["locale"] == "en-US"
    assert "hardwareConcurrency" in options.init_script()

    with tempfile.TemporaryDirectory() as tmp:
        path = options.save(Path(tmp) / "fingerprint.json")
        assert FingerprintOptions.load(path) == options

    entry = NetworkEntry(
        method="GET",
        url="https://example.com/master.m3u8",
        resource_type="media",
    )
    capture = PageCapture(
        url="https://example.com/",
        html="",
        network=[entry],
    )
    assert entry.is_api is False
    assert capture.hls_urls() == ["https://example.com/master.m3u8"]


def test_current_ip_collect_uses_proxy_pool() -> None:
    with mock.patch("current_ip.ProxyPool") as pool_cls:
        pool = pool_cls.return_value
        pool.current_ip.return_value = "203.0.113.10"
        pool._http_egress_ip.return_value = "203.0.113.10"
        pool._current_ip_source = "stun"
        pool.use_current_ip = True
        result = collect()
    assert result["current_ip"] == "203.0.113.10"
    assert result["egress_matches_real"] is True


def test_data_processor_pipeline_and_io() -> None:
    records = [
        {"id": 1, "name": "Alpha", "price": 10, "meta": {"ok": True}},
        {"id": 2, "name": "Beta", "price": 20, "meta": {"ok": False}},
        {"id": 3, "name": "Alpha", "price": 30, "meta": {"ok": True}},
    ]
    config = {
        "steps": [
            {"op": "filter", "params": {"conditions": [{"field": "price", "op": "gte", "value": 10}]}},
            {"op": "select", "params": {"fields": ["id", "name"]}},
            {"op": "sort", "params": {"keys": [{"field": "id", "desc": False}]}},
        ]
    }
    processed = process_records(records, config)
    assert processed == [
        {"id": 1, "name": "Alpha"},
        {"id": 2, "name": "Beta"},
        {"id": 3, "name": "Alpha"},
    ]
    assert get_path({"a": {"b": [{"c": 1}]}}, "a.b.0.c") == 1

    with tempfile.TemporaryDirectory() as tmp:
        path = save_records(processed, Path(tmp) / "out.json")
        assert load_records(path) == processed
        csv_path = save_records(processed, Path(tmp) / "out.csv")
        assert load_records(csv_path)[0]["id"] == "1"


def test_media_parser_html_and_hls() -> None:
    html = """
    <html><body>
      <img src="/a.jpg" srcset="/b.jpg 1x, /c.jpg 2x">
      <video src="/v.mp4"></video>
      <a href="/d.m3u8">stream</a>
    </body></html>
    """
    extraction = extract_media_urls(html, "https://example.com/page")
    assert "https://example.com/a.jpg" in extraction.images
    assert "https://example.com/b.jpg" in extraction.images
    assert extraction.videos == ["https://example.com/v.mp4"]
    assert extraction.hls == ["https://example.com/d.m3u8"]

    master = """
    #EXTM3U
    #EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=720x404
    https://example.com/720.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=2560000,RESOLUTION=1080x606
    https://example.com/1080.m3u8
    """
    playlist = parse_m3u8(master)
    assert playlist.is_master is True
    assert choose_best_variant(playlist).bandwidth == 2560000

    media = parse_m3u8(
        "#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\nseg1.ts\n#EXT-X-ENDLIST\n",
        "https://example.com/video/",
    )
    assert media.segments[0].uri == "https://example.com/video/seg1.ts"
    assert media.endlist is True


def test_scrape_guard_policies() -> None:
    retry = RetryPolicy(max_retries=2)
    assert retry.should_retry(429, 0) is True
    assert retry.should_retry(429, 2) is False
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after(None) is None

    throttle = AdaptiveThrottle(base_delay=1.0, max_delay=8.0, factor=2.0)
    throttle.on_block(403)
    assert throttle.delay == 2.0
    throttle.on_success()
    assert throttle.delay == 1.0

    robots = RobotsPolicy(user_agent="TestBot/1.0")
    robots.load_text(
        "User-agent: *\nDisallow: /private\n"
        "Sitemap: https://example.com/sitemap.xml\nCrawl-delay: 2\n"
    )
    assert robots.can_fetch("https://example.com/public") is True
    assert robots.can_fetch("https://example.com/private") is False
    assert robots.sitemap_urls() == ["https://example.com/sitemap.xml"]
    assert robots.crawl_delay() == 2.0

    pacer = RequestPacer(robots=robots)
    try:
        pacer.wait("https://example.com/private")
    except RobotsDenied as exc:
        assert exc.url == "https://example.com/private"
    else:
        raise AssertionError("RobotsDenied was not raised")


def test_nopecha_probe_helpers() -> None:
    assert _public_ipv4("8.8.8.8") is True
    assert _public_ipv4("192.168.1.1") is False
    assert _public_ipv4("not-an-ip") is False
    html = '<p>Your public IP is 8.8.8.8</p><script>{"ip":"1.1.1.1"}</script>'
    assert extract_page_ip(html) == "8.8.8.8"
    assert extract_page_ip('<script>{"ip":"1.1.1.1"}</script>') == "1.1.1.1"
    assert _has_clearance([{"name": "cf_clearance", "value": "x"}]) is True
    assert _has_clearance([{"name": "cf_clearance", "value": ""}]) is False


def test_web_data_pipeline_helpers_and_local_run() -> None:
    assert _unwrap_data({"items": [{"id": 1}]}) == [{"id": 1}]
    assert _unwrap_data({"data": {"records": [{"id": 2}]}}) == [{"id": 2}]
    assert _build_captcha_solver({"captcha": {"enabled": False}}) is None
    assert _build_captcha_solver({"captcha": {"enabled": True, "api_key": "key"}}) is not None

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SelfTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "pages": [f"{base}/list"],
                        "api": {
                            "min_interval": 0.0,
                            "max_retries": 0,
                            "include_static": True,
                            "include_captured": False,
                        },
                        "processing": {
                            "steps": [
                                {
                                    "op": "select",
                                    "params": {"fields": ["id", "name"]},
                                },
                                {
                                    "op": "filter",
                                    "params": {
                                        "conditions": [{"field": "id", "op": "exists"}]
                                    },
                                },
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            output = Path(tmp) / "result.json"
            pipeline = WebDataPipeline(_read_config(config_path), output=output)
            summary = pipeline.run()
            assert summary["processed_records"] == 2, summary
            assert load_records(output)[0]["id"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_acceptance_suite_local_targets() -> None:
    target = AcceptanceTarget.from_dict(
        {
            "name": "local-page",
            "url": "http://127.0.0.1:1/",
            "expected_status": [200, 404],
            "checks": ["http"],
            "skip_without": ["network"],
            "max_attempts": 1,
        }
    )
    assert target.expected_status == (200, 404)
    assert target.max_attempts == 1

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _LocalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        report = run_acceptance(
            {
                "fetch": {"backend": "standard", "auto_install": False},
                "targets": [
                    {
                        "name": "local-page",
                        "url": f"{base}/",
                        "expected_status": 200,
                        "expected_marker": "acceptance-ok",
                    },
                    {
                        "name": "local-api",
                        "url": f"{base}/api",
                        "kind": "api",
                        "expected_status": 200,
                        "expected_marker": "items",
                    },
                ],
            }
        )
        assert report["counts"]["pass"] == 2, report
    finally:
        server.shutdown()
        server.server_close()


def test_acceptance_skip_without_proxy_pool() -> None:
    target = AcceptanceTarget.from_dict(
        {
            "name": "ip-sensitive",
            "url": "https://example.com/",
            "skip_without": ["proxy_pool"],
        }
    )
    reason = _skip_reason(target, {"proxy_pool": None, "stealth_engines": ["patchright"]})
    assert reason == "proxy pool not configured or empty"
