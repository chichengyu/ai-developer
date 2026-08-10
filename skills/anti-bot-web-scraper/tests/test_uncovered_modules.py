"""Direct tests for modules without prior direct unit coverage."""

from __future__ import annotations

import http.server
import json
import os
import struct
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

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
from captcha_solver import (  # noqa: E402
    AutoCaptchaSolver,
    CaptchaChallenge,
    CaptchaError,
    CaptchaResult,
    OcrCaptchaSolver,
)
from current_ip import collect  # noqa: E402
from dash_client import DASHClient  # noqa: E402
from data_processor import get_path, load_records, process_records, save_records  # noqa: E402
from media_metadata import probe_media_file, sniff_media_type  # noqa: E402
from media_parser import (  # noqa: E402
    MediaExtraction,
    build_mpd_segment_urls,
    choose_best_variant,
    extract_media_urls,
    mpd_initialization_range,
    mpd_initialization_url,
    parse_css_assets,
    parse_js_assets,
    parse_m3u8,
    parse_mpd,
    parse_smooth_manifest,
    select_mpd_representation,
)
from nopecha_probe import _has_clearance, _public_ipv4, extract_page_ip  # noqa: E402
from page_data_parser import analyze_page  # noqa: E402
from scrape_guard import (  # noqa: E402
    AdaptiveThrottle,
    RequestPacer,
    RetryPolicy,
    RobotsDenied,
    RobotsPolicy,
    parse_retry_after,
)
from stealth_browser import _load_playwright_cookies  # noqa: E402
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
      <a href="/d.mpd">dash</a>
      <a href="/d.ism/Manifest">smooth</a>
    </body></html>
    """
    extraction = extract_media_urls(html, "https://example.com/page")
    assert "https://example.com/a.jpg" in extraction.images
    assert "https://example.com/b.jpg" in extraction.images
    assert extraction.videos == ["https://example.com/v.mp4"]
    assert extraction.hls == ["https://example.com/d.m3u8"]
    assert extraction.dash == ["https://example.com/d.mpd"]
    assert extraction.smooth == ["https://example.com/d.ism/Manifest"]

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


def test_page_capture_dash_urls() -> None:
    capture = PageCapture(
        url="https://example.com/video",
        html="",
        network=[],
        analysis=SimpleNamespace(
            media=MediaExtraction(dash=["https://example.com/video/manifest.mpd"]),
            json_media=MediaExtraction(),
        ),
    )
    assert capture.dash_urls() == ["https://example.com/video/manifest.mpd"]


def test_page_assets_css_js_fonts_and_images() -> None:
    html = """
    <html>
      <link rel="stylesheet" href="/app.css">
      <link rel="icon" href="/favicon.png">
      <link rel="preload" as="font" href="/font.woff2">
      <script src="/app.js"></script>
    </html>
    """
    analysis = analyze_page(html, "https://example.com/page")
    assert "https://example.com/app.css" in analysis.assets["css"]
    assert "https://example.com/app.js" in analysis.assets["js"]
    assert "https://example.com/favicon.png" in analysis.assets["images"]
    assert "https://example.com/font.woff2" in analysis.assets["fonts"]


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


def test_build_captcha_solver_provider_selection() -> None:
    capsolver = _build_captcha_solver(
        {"captcha": {"provider": "capsolver", "api_key": "cap-key"}}
    )
    assert capsolver is not None
    assert type(capsolver.solver).__name__ == "CapSolverSolver"
    assert capsolver.solver.base_url == "https://api.capsolver.com"

    anticaptcha = _build_captcha_solver(
        {"captcha": {"provider": "anti-captcha", "api_key": "ac-key"}}
    )
    assert anticaptcha is not None
    assert type(anticaptcha.solver).__name__ == "AntiCaptchaSolver"
    assert anticaptcha.solver.base_url == "https://api.anti-captcha.com"

    two_captcha = _build_captcha_solver(
        {
            "captcha": {
                "provider": "2captcha",
                "api_key": "2c-key",
                "base_url": "https://custom-captcha.example",
            }
        }
    )
    assert two_captcha is not None
    assert type(two_captcha.solver).__name__ == "CaptchaSolver"
    assert two_captcha.solver.base_url == "https://custom-captcha.example"

    with mock.patch.dict(os.environ, {"REVIEW_CAPTCHA_KEY": "env-key"}, clear=False):
        from_env = _build_captcha_solver(
            {"captcha": {"provider": "capsolver", "api_key_env": "REVIEW_CAPTCHA_KEY"}}
        )
    assert from_env is not None
    assert from_env.solver.api_key == "env-key"

    assert _build_captcha_solver({"captcha": {"enabled": False, "api_key": "key"}}) is None
    no_key = _build_captcha_solver({"captcha": {"api_key_env": "REVIEW_CAPTCHA_KEY"}})
    assert no_key is not None
    assert no_key.has_service is False


def test_captcha_no_key_modes_and_cloudflare_provider() -> None:
    auto_pipeline = WebDataPipeline({"pages": []})
    assert auto_pipeline.mode == "auto"
    assert auto_pipeline.config["fetch"]["backend"] == "auto"
    assert auto_pipeline.config["fetch"]["fingerprint_binding"] == "chrome124"
    assert auto_pipeline.captcha_mode == "ocr"

    explicit_pipeline = WebDataPipeline({"pages": [], "mode": "explicit"})
    assert explicit_pipeline.mode == "explicit"
    assert explicit_pipeline.captcha_mode == "off"
    assert (explicit_pipeline.config.get("fetch") or {}).get("backend", "standard") == "standard"

    ocr_pipeline = WebDataPipeline({"pages": [], "captcha": {"ocr": True}})
    assert ocr_pipeline.captcha_solver is not None
    assert ocr_pipeline.captcha_mode == "ocr"
    assert ocr_pipeline._cloudflare_captcha_solver() is None
    assert ocr_pipeline.captcha_solver.ocr_solver.auto_install is True
    priority_pipeline = WebDataPipeline(
        {"pages": [], "captcha": {"ocr_priority": ["pytesseract"]}}
    )
    assert priority_pipeline.captcha_solver.ocr_solver.priority == ("pytesseract",)

    no_install = _build_captcha_solver({"captcha": {"auto_install_ocr": False}})
    assert no_install is not None
    assert no_install.ocr_solver.auto_install is False

    manual_pipeline = WebDataPipeline(
        {"pages": [], "captcha": {"allow_manual_fallback": True}}
    )
    assert manual_pipeline.captcha_solver is not None
    assert manual_pipeline.captcha_mode == "manual"
    assert manual_pipeline._cloudflare_captcha_solver() is None

    provider_pipeline = WebDataPipeline(
        {"pages": [], "captcha": {"provider": "capsolver", "api_key": "key"}}
    )
    assert provider_pipeline.captcha_mode == "provider"
    assert provider_pipeline._cloudflare_captcha_solver() is not None

    disabled_pipeline = WebDataPipeline({"pages": [], "captcha": {"enabled": False}})
    assert disabled_pipeline.captcha_mode == "off"
    assert _build_captcha_solver({"captcha": {"ocr": False}}) is None


def test_auto_captcha_solver_continues_on_error() -> None:
    class MixedSolver:
        api_key = "key"

        def solve_image(self, image_path: str) -> CaptchaResult:
            raise CaptchaError("local OCR failed")

        def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
            return CaptchaResult(success=True, task_id="ok", answer="token")

    solver = AutoCaptchaSolver(MixedSolver())
    challenges = [
        CaptchaChallenge(kind="image", image_url="https://example.com/captcha.png"),
        CaptchaChallenge(
            kind="turnstile",
            site_key="sitekey",
            page_url="https://example.com/",
        ),
    ]
    solved = solver.solve_detected(
        challenges,
        image_paths=["/tmp/missing-captcha.png"],
        continue_on_error=True,
    )
    assert len(solved) == 1
    assert solved[0][0].kind == "turnstile"
    assert solver.last_errors
    assert solver.has_service is True

    no_key_solver = AutoCaptchaSolver(type("EmptySolver", (), {"api_key": ""})())
    skipped = no_key_solver.solve_detected(
        [CaptchaChallenge(kind="turnstile", site_key="sitekey")],
        continue_on_error=True,
    )
    assert skipped == []
    assert no_key_solver.has_service is False


def test_ocr_auto_install_on_demand() -> None:
    assert OcrCaptchaSolver(backend="rapidocr")._selected_backend() == "rapidocr_onnxruntime"
    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "captcha.png"
        image.write_bytes(b"not-a-real-image")
        ocr = OcrCaptchaSolver(auto_install=True)
        with (
            mock.patch("ensure_web_fetch_dependencies.ensure") as ensure_mock,
            mock.patch.object(ocr, "_backend", return_value=None),
            pytest.raises(CaptchaError),
        ):
            ocr.solve_image(image)
        ensure_mock.assert_called_once()

        disabled = OcrCaptchaSolver(auto_install=False)
        with (
            mock.patch("ensure_web_fetch_dependencies.ensure") as ensure_mock,
            mock.patch.object(disabled, "_backend", return_value=None),
            pytest.raises(CaptchaError),
        ):
            disabled.solve_image(image)
        ensure_mock.assert_not_called()


def test_http_captcha_detection_marks_auto_escalation() -> None:
    class CaptchaHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = (
                b'<html><body><div class="g-recaptcha" '
                b'data-sitekey="6Lc_test"></div></body></html>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), CaptchaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        pipeline = WebDataPipeline({"pages": [], "mode": "auto"})
        capture = pipeline._capture_http_page(f"http://127.0.0.1:{server.server_port}/")
        assert capture.security is not None
        assert capture.security.get("auto_captcha") is True
        assert "recaptcha_v2" in capture.security.get("captcha_kinds", [])
    finally:
        server.shutdown()
        server.server_close()


def test_pipeline_downloads_media_assets() -> None:
    class AssetHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/a.png":
                body = b"image-bytes"
            elif self.path == "/app.css":
                body = b"body{}"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), AssetHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            base = f"http://127.0.0.1:{server.server_port}"
            pipeline = WebDataPipeline(
                {
                    "pages": [],
                    "media": {
                        "enabled": True,
                        "output_dir": str(Path(tmp) / "media"),
                        "download_assets": True,
                    },
                }
            )
            pipeline.captures = [
                PageCapture(
                    url=f"{base}/page",
                    html="",
                    network=[],
                    analysis=SimpleNamespace(
                        media=MediaExtraction(
                            images=[f"{base}/a.png"],
                            links=[f"{base}/app.css"],
                        ),
                        json_media=MediaExtraction(),
                        assets={"css": [f"{base}/app.css"]},
                    ),
                )
            ]
            pipeline._download_media_assets()
            assert len(pipeline.media_assets) >= 2
            assert any(item.get("kind") == "image" for item in pipeline.media_assets)
            assert any(item.get("kind") == "css" for item in pipeline.media_assets)
    finally:
        server.shutdown()
        server.server_close()


def test_playwright_cookie_reuse_loader() -> None:
    class FakeContext:
        def __init__(self) -> None:
            self.added: list[dict[str, object]] = []

        def add_cookies(self, cookies: list[dict[str, object]]) -> None:
            self.added.extend(cookies)

    context = FakeContext()
    _load_playwright_cookies(
        context,
        [
            {
                "name": "cf_clearance",
                "value": "token",
                "domain": ".zoopla.co.uk",
                "path": "/",
                "sameSite": "None",
                "expires": 0,
            }
        ],
    )
    assert context.added[0]["name"] == "cf_clearance"
    assert context.added[0]["sameSite"] == "None"
    assert "expires" not in context.added[0]


def test_dash_mpd_parsing_and_segment_building() -> None:
    mpd = """<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT6S">
  <Period>
    <AdaptationSet mimeType="video/mp4">
      <Representation id="v1" bandwidth="500000" width="640" height="360" codecs="avc1">
        <SegmentTemplate timescale="1" duration="2" startNumber="1"
          initialization="init-$RepresentationID$.mp4" media="seg-$Number%02d$.m4s"/>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>"""
    playlist = parse_mpd(mpd, "https://example.com/video/manifest.mpd")
    rep = select_mpd_representation(playlist, preferred_height=360)
    assert rep is not None
    assert rep.id == "v1"
    assert rep.height == 360
    assert mpd_initialization_url(rep) == "https://example.com/video/init-v1.mp4"
    urls = build_mpd_segment_urls(rep, max_segments=3)
    assert urls == [
        "https://example.com/video/seg-01.m4s",
        "https://example.com/video/seg-02.m4s",
        "https://example.com/video/seg-03.m4s",
    ]

    segment_base_mpd = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
  <Period><AdaptationSet mimeType="video/mp4">
    <Representation id="s1" bandwidth="1000" width="640" height="360">
      <BaseURL>video.mp4</BaseURL>
      <SegmentBase indexRange="0-100">
        <Initialization range="0-99"/>
      </SegmentBase>
    </Representation>
  </AdaptationSet></Period>
</MPD>"""
    base_playlist = parse_mpd(segment_base_mpd, "https://example.com/video/manifest.mpd")
    base_rep = select_mpd_representation(base_playlist)
    assert base_rep is not None
    assert base_rep.segment_base == {
        "index_range": "0-100",
        "init_range": "0-99",
    }
    assert build_mpd_segment_urls(base_rep) == ["https://example.com/video/video.mp4"]
    assert mpd_initialization_range(base_rep) == (
        "https://example.com/video/video.mp4",
        "0-99",
    )


def test_dash_client_downloads_local_manifest() -> None:
    class DashHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/manifest.mpd":
                body = b"""<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
<Period><AdaptationSet mimeType="video/mp4"><Representation id="v1" bandwidth="1000">
<SegmentList><SegmentURL media="seg-1.m4s"/><SegmentURL media="seg-2.m4s"/></SegmentList>
</Representation></AdaptationSet></Period></MPD>"""
            elif self.path == "/seg-1.m4s":
                body = b"segment-one"
            elif self.path == "/seg-2.m4s":
                body = b"segment-two"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/dash+xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), DashHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            client = DASHClient()
            try:
                result = client.download(
                    f"http://127.0.0.1:{server.server_port}/manifest.mpd",
                    Path(tmp) / "dash",
                )
            finally:
                client.close()
            assert result.downloaded_segments == 2
            assert result.failed_segments == 0
            assert result.combined_path is not None
            assert Path(result.combined_path).read_bytes() == b"segment-onesegment-two"
            resumed = client.download(
                f"http://127.0.0.1:{server.server_port}/manifest.mpd",
                Path(tmp) / "dash",
            )
            assert resumed.resumed_segments == resumed.downloaded_segments == 2
    finally:
        server.shutdown()
        server.server_close()


def test_media_metadata_probing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        mvhd_payload = (
            b"\x00"
            + b"\x00\x00\x00"
            + b"\x00" * 8
            + struct.pack(">II", 1000, 5000)
            + b"\x00" * 80
        )
        mvhd = struct.pack(">I", 8 + len(mvhd_payload)) + b"mvhd" + mvhd_payload
        moov_payload = mvhd
        moov = struct.pack(">I", 8 + len(moov_payload)) + b"moov" + moov_payload
        ftyp = struct.pack(">I", 16) + b"ftyp" + b"isom" + b"\x00\x00\x00\x00"
        media_path = Path(tmp) / "video.mp4"
        media_path.write_bytes(ftyp + moov)
        assert sniff_media_type(media_path) == "mp4"
        metadata = probe_media_file(media_path)
        assert metadata["media_type"] == "mp4"
        assert metadata["duration_seconds"] == 5.0

        subtitle_path = Path(tmp) / "subs.vtt"
        subtitle_path.write_text(
            "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n",
            encoding="utf-8",
        )
        subtitle_meta = probe_media_file(subtitle_path)
        assert subtitle_meta["format"] == "webvtt"
        assert subtitle_meta["cues"] == 1

        png_path = Path(tmp) / "image.png"
        png_path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", 640, 480)
            + b"\x08\x06\x00\x00\x00"
        )
        image_meta = probe_media_file(png_path)
        assert image_meta["dimensions"] == {"width": 640, "height": 480}


def test_css_js_asset_parsing() -> None:
    css = 'body{background:url("/bg.png")} @import "theme.css";'
    assert parse_css_assets(css, "https://example.com/app.css") == [
        "https://example.com/bg.png",
        "https://example.com/theme.css",
    ]
    js = 'import "/chunk.js"; new URL("/data.json", location);'
    assert parse_js_assets(js, "https://example.com/app.js") == [
        "https://example.com/chunk.js",
        "https://example.com/data.json",
    ]


def test_smooth_streaming_manifest_parsing() -> None:
    xml = """<SmoothStreamingMedia Duration="20000000" IsLive="false">
  <StreamIndex Type="video" Url="QualityLevels({bitrate})/Fragments(video={start time})" Name="video">
    <QualityLevel Index="0" Bitrate="1000000" FourCC="H264" MaxWidth="1280" MaxHeight="720"/>
    <c t="0" d="2000000"/>
    <c t="2000000" d="2000000"/>
  </StreamIndex>
</SmoothStreamingMedia>"""
    playlist = parse_smooth_manifest(xml, "https://example.com/video.ism/Manifest")
    assert playlist.duration_seconds == 2.0
    assert playlist.is_live is False
    assert playlist.streams[0].media_type == "video"
    assert playlist.streams[0].qualities[0].height == 720
    assert len(playlist.streams[0].chunks) == 2


def test_m3u8_subtitle_rendition_parsing() -> None:
    text = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English",LANGUAGE="en",URI="subs/en.vtt"\n'
        "#EXTINF:2.0,\nseg.ts\n"
    )
    playlist = parse_m3u8(text, "https://example.com/video/media.m3u8")
    assert playlist.renditions
    assert playlist.renditions[0].uri == "https://example.com/video/subs/en.vtt"
    assert playlist.renditions[0].media_type == "SUBTITLES"


def test_m3u8_low_latency_and_iframe_parsing() -> None:
    text = (
        "#EXTM3U\n"
        "#EXT-X-SERVER-CONTROL:CAN-BLOCK-RELOAD=YES,PART-HOLD-BACK=1.5\n"
        "#EXT-X-PART-INF:PART-TARGET=1.0\n"
        "#EXT-X-SKIP:SKIPPED-SEGMENTS=3\n"
        '#EXT-X-PART:DURATION=1.0,URI="part1.m4s",INDEPENDENT=YES\n'
        '#EXT-X-PRELOAD-HINT:TYPE=PART,URI="part2.m4s"\n'
        "#EXT-X-PROGRAM-DATE-TIME:2026-01-01T00:00:00Z\n"
        '#EXT-X-DATERANGE:ID="ad1",START-DATE="2026-01-01T00:00:00Z"\n'
        '#EXT-X-I-FRAME-STREAM-INF:BANDWIDTH=100000,URI="iframe.m3u8"\n'
        "#EXTINF:2.0,\nseg.ts\n"
    )
    playlist = parse_m3u8(text, "https://example.com/live/stream.m3u8")
    assert playlist.server_control.get("CAN-BLOCK-RELOAD") == "YES"
    assert playlist.part_inf.get("PART-TARGET") == "1.0"
    assert playlist.skip.get("SKIPPED-SEGMENTS") == "3"
    assert playlist.parts[0].uri == "https://example.com/live/part1.m4s"
    assert playlist.parts[0].independent is True
    assert playlist.preload_hint.get("URI") == "part2.m4s"
    assert playlist.program_date_time == "2026-01-01T00:00:00Z"
    assert playlist.date_ranges[0]["ID"] == "ad1"
    assert playlist.i_frames[0].url == "https://example.com/live/iframe.m3u8"


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
