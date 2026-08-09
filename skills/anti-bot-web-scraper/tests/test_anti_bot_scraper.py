"""Network-free and local tests for the anti-bot web scraper skill."""

from __future__ import annotations

import http.server
import json
import sys
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from adaptive_policy import AdaptivePolicyStore  # noqa: E402
from api_client import ApiClient, ApiSpec  # noqa: E402
from autonomous_crawler import AutonomousCrawler, AutonomousCrawlerConfig  # noqa: E402
from block_diagnoser import diagnose_response  # noqa: E402
from browser_flags import ANTI_DETECT_ARGS, BrowserLaunchProfile  # noqa: E402
from bypass_engine import choose_engine_order, run_bypass  # noqa: E402
from captcha_queue import CaptchaTaskQueue  # noqa: E402
from captcha_solver import (  # noqa: E402
    CapSolverSolver,
    CaptchaError,
    CaptchaResult,
    MultiCaptchaSolver,
    detect_captchas,
)
from challenge_click import click_managed_challenge, click_shadow_dom, human_click  # noqa: E402
from challenge_evolution import fingerprint_challenge, marker_diff  # noqa: E402
from challenge_replay import (  # noqa: E402
    diagnose_snapshot,
    find_snapshots,
    load_challenge_snapshot,
    save_challenge_snapshot,
)
from cloudflare_challenge import (  # noqa: E402
    CloudflareChallengeConfig,
    CloudflareChallengeHandler,
    CloudflareChallengeResult,
    extract_cloudflare_state,
)
from daemon import DaemonRunner  # noqa: E402
from data_extractor import AutoDataExtractor, infer_schema, structure_signature  # noqa: E402
from deep_crawler import CrawlConfig, DeepCrawler  # noqa: E402
from ensure_browser_binaries import chunked_download  # noqa: E402
from ensure_browser_binaries import status as browser_binaries_status  # noqa: E402
from ensure_web_fetch_dependencies import (  # noqa: E402
    check_status as ensure_status,
)
from ensure_web_fetch_dependencies import (  # noqa: E402
    ensure as ensure_dependencies,
)
from ensure_web_fetch_dependencies import (  # noqa: E402
    missing_packages,
)
from fingerprint_bank import BrowserFingerprint, FingerprintBank, HeaderFingerprint  # noqa: E402
from fingerprint_binding import (  # noqa: E402
    apply_binding_to_fetch_config,
    available_bindings,
    resolve_binding,
)
from fingerprint_manager import FingerprintManager  # noqa: E402
from flaresolverr import FlaresolverrClient  # noqa: E402
from hls_client import HLSClient  # noqa: E402
from human_behavior import HumanBehavior  # noqa: E402
from login_detector import detect_login  # noqa: E402
from media_crawler import (  # noqa: E402
    MediaAsset,
    MediaCrawlConfig,
    MediaCrawler,
    MediaCrawlResult,
    MediaPage,
    _asset_filename,
)
from media_session import MediaSession  # noqa: E402
from metrics import AlertManager, MetricsRegistry, default_alert_rules  # noqa: E402
from page_data_parser import analyze_page  # noqa: E402
from proxy_pool import (  # noqa: E402
    CURRENT_IP_PROXY,
    ProxyManager,
    ProxyPool,
    create_proxy_pool,
    normalize_proxy,
)
from resource_downloader import ResourceDownloader, _content_type_suffix  # noqa: E402
from resource_store import ResourceStore  # noqa: E402
from run_summary import jsonl_report, media_result_report, resource_status  # noqa: E402
from security_detector import detect_security_mechanisms  # noqa: E402
from slider_solver import (  # noqa: E402
    detect_slider_challenges,
)
from smart_fetch import (  # noqa: E402
    BackendResponse,
    SmartFetchSession,
    available_backends,
    create_fetch_session,
)
from stealth_browser import (  # noqa: E402
    StealthBrowserError,
    StealthBrowserResult,
    _challenge_pending,
    _looks_solved,
    _wait_for_browser_ready,
    available_stealth_engines,
    preflight_stealth_engines,
    solve_cloudflare_with_stealth_browser,
)
from stealth_patch_bank import compose_patches  # noqa: E402
from stealth_patches import STEALTH_JS, apply_playwright_stealth  # noqa: E402
from turnstile_solver import (  # noqa: E402
    TurnstileSolver,
    TurnstileWidget,
    detect_turnstile_widgets,
)
from url_store import UrlDeduplicator  # noqa: E402
from vendor_solver import (  # noqa: E402
    extract_vendor_public_key,
    has_valid_vendor_cookie,
    inject_captcha_token,
    solve_vendor_with_provider,
)


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    payloads: dict[str, bytes] = {}

    def do_GET(self) -> None:
        data = self.payloads.get(self.path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _BlockingHandler(http.server.BaseHTTPRequestHandler):
    payloads: dict[str, bytes] = {}
    blocked_paths: set[str] = set()

    def do_GET(self) -> None:
        if self.path in type(self).blocked_paths:
            body = b"<html><body>Access Denied</body></html>"
            self.send_response(403)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        data = self.payloads.get(self.path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _FlaresolverrHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        if payload.get("cmd") == "request.get":
            body = {
                "status": "ok",
                "solution": {
                    "url": payload.get("url", "https://example.com/"),
                    "status": 200,
                    "headers": {"content-type": "text/html"},
                    "response": "<html><body>solved</body></html>",
                    "cookies": [
                        {
                            "name": "cf_clearance",
                            "value": "abc",
                            "domain": ".example.com",
                            "path": "/",
                            "secure": True,
                        }
                    ],
                    "userAgent": "Mozilla/5.0 solved",
                },
            }
        else:
            body = {"status": "ok", "sessions": ["s1"]}
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _CookieEchoHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"cookie": self.headers.get("Cookie", "")}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _RangeResourceHandler(http.server.BaseHTTPRequestHandler):
    payloads: dict[str, bytes] = {}

    def _headers(self, status: int, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()

    def do_HEAD(self) -> None:
        data = self.payloads.get(self.path)
        if data is None:
            self._headers(404)
            return
        self._headers(200, {"Content-Length": str(len(data))})

    def do_GET(self) -> None:
        data = self.payloads.get(self.path)
        if data is None:
            self._headers(404)
            return
        range_header = self.headers.get("Range")
        if range_header:
            start_text = range_header.replace("bytes=", "").split("-", 1)[0]
            end_text = range_header.replace("bytes=", "").split("-", 1)[1]
            start = int(start_text or 0)
            end = int(end_text) if end_text else len(data) - 1
            body = data[start : end + 1]
            self._headers(
                206,
                {
                    "Content-Length": str(len(body)),
                    "Content-Range": f"bytes {start}-{start + len(body) - 1}/{len(data)}",
                },
            )
            self.wfile.write(body)
            return
        self._headers(200, {"Content-Length": str(len(data))})
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _FakePage:
    def __init__(self, html: str = "") -> None:
        self._html = html

    def content(self) -> str:
        return self._html

    def title(self) -> str:
        return "Just a moment..."


class _FakeContext:
    def __init__(self, clearance: bool = False) -> None:
        self.clearance = clearance

    def cookies(self) -> list[dict]:
        if self.clearance:
            return [
                {
                    "name": "cf_clearance",
                    "value": "abc123",
                    "domain": "example.com",
                    "path": "/",
                }
            ]
        return []


def _start_server(payloads: dict[str, bytes], handler=_RangeHandler):
    if hasattr(handler, "payloads"):
        handler.payloads.update(payloads)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}", server


def test_smart_fetch_factory_and_status() -> None:
    assert isinstance(create_fetch_session({"backend": "standard"}), MediaSession)
    assert isinstance(create_fetch_session({"backend": "auto"}), SmartFetchSession)
    assert "urllib" in available_backends()


def test_smart_fetch_local_fallback() -> None:
    base, server = _start_server({"/page.html": b"<html><body>ok</body></html>"})
    try:
        session = SmartFetchSession(min_interval=0.0, max_retries=0)
        body, status, _ = session.get_bytes_with_meta(f"{base}/page.html")
        assert status == 200
        assert b"<html><body>ok</body></html>" in body
        assert session.stats["last_backend"] in {
            "curl_cffi",
            "cloudscraper",
            "httpx",
            "urllib",
        }
    finally:
        server.shutdown()


def test_bypass_engine_http_pass() -> None:
    base, server = _start_server({"/": b"<html><body>bypass-ok</body></html>"})
    try:
        result = run_bypass(f"{base}/", {"fetch": {"backend": "standard"}})
        assert result.passed is True
        assert result.strategy == "http"
        assert "bypass-ok" in result.body
    finally:
        server.shutdown()


def test_bypass_engine_engine_order_for_turnstile() -> None:
    order = choose_engine_order(
        None,
        "turnstile_captcha",
        available=["patchright", "nodriver", "camoufox"],
    )
    assert order[0] == "patchright"
    firefox_order = choose_engine_order(
        resolve_binding("firefox127"),
        "turnstile_captcha",
        available=["camoufox", "scrapling", "patchright"],
    )
    assert firefox_order[0] == "camoufox"


def test_smart_fetch_switches_backend() -> None:
    session = SmartFetchSession(min_interval=0.0, max_retries=0)
    calls: list[str] = []

    def fake_try_backend(
        name: str,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ) -> BackendResponse:
        calls.append(name)
        if name == "curl_cffi":
            return BackendResponse(
                url=url,
                status=403,
                headers={"Content-Type": "text/html"},
                body=b"Access Denied",
                backend="curl_cffi",
            )
        return BackendResponse(
            url=url,
            status=200,
            headers={"Content-Type": "text/plain"},
            body=b"ok",
            backend="urllib",
        )

    with (
        mock.patch("smart_fetch.available_backends", return_value=["curl_cffi", "urllib"]),
        mock.patch.object(session, "_try_backend", side_effect=fake_try_backend),
    ):
        body, status, _ = session.get_bytes_with_meta("http://example.com/page")
    assert status == 200
    assert body == b"ok"
    assert calls == ["curl_cffi", "urllib"]


def test_smart_fetch_blocked_metadata() -> None:
    base, server = _start_server({"/blocked": b"ignored"}, _BlockingHandler)
    _BlockingHandler.blocked_paths = {"/blocked"}
    try:
        session = SmartFetchSession(min_interval=0.0, max_retries=0)
        _, status, _ = session.get_bytes_with_meta(f"{base}/blocked")
        assert status == 403
        assert session.stats["last_security_kind"] == "waf_blocked"
    finally:
        _BlockingHandler.blocked_paths = set()
        server.shutdown()


def test_smart_fetch_preserves_clearance_cookie() -> None:
    session = SmartFetchSession(min_interval=0.0, max_retries=0)
    session.load_cookies(
        [
            {
                "name": "cf_clearance",
                "value": "abc123",
                "domain": "example.com",
                "path": "/",
                "secure": True,
            }
        ]
    )
    assert "cf_clearance=abc123" in session._cookie_header("https://example.com/")


def test_smart_fetch_browser_fallback_merges_cookies() -> None:
    session = SmartFetchSession(
        backend="browser",
        browser_config={"engine": "patchright", "auto_install": False},
        min_interval=0.0,
        max_retries=0,
        auto_install_dependencies=False,
    )
    fake_result = StealthBrowserResult(
        url="https://example.com/",
        final_url="https://example.com/page",
        html="<html><body>solved</body></html>",
        cookies=[
            {
                "name": "cf_clearance",
                "value": "abc",
                "domain": "example.com",
                "path": "/",
                "secure": True,
            }
        ],
        engine="patchright",
    )
    with mock.patch(
        "stealth_browser.solve_cloudflare_with_stealth_browser",
        return_value=fake_result,
    ):
        body, status, _ = session.get_bytes_with_meta("https://example.com/page")
    assert status == 200
    assert b"solved" in body
    assert session.stats["last_backend"] == "browser:patchright"
    assert "cf_clearance=abc" in session._cookie_header("https://example.com/page")


def test_stealth_browser_auto_cycle_engines() -> None:
    calls: list[str] = []

    def fake_solve(
        engine: str,
        url: str,
        **kwargs: object,
    ) -> StealthBrowserResult:
        calls.append(engine)
        if engine == "patchright":
            return StealthBrowserResult(
                url=url,
                html="<html><title>Just a moment...</title></html>",
                engine=engine,
            )
        return StealthBrowserResult(
            url=url,
            html="<html><body>ok</body></html>",
            cookies=[
                {
                    "name": "cf_clearance",
                    "value": "xyz",
                    "domain": "example.com",
                    "path": "/",
                }
            ],
            engine=engine,
        )

    with (
        mock.patch(
            "stealth_browser.available_stealth_engines",
            return_value=["patchright", "nodriver"],
        ),
        mock.patch("stealth_browser._solve_engine", side_effect=fake_solve),
    ):
        result = solve_cloudflare_with_stealth_browser(
            "https://example.com/",
            engine="auto",
            auto_install=False,
            max_attempts=1,
        )
    assert result.engine == "nodriver"
    assert calls == ["patchright", "patchright", "nodriver"]
    assert result.attempts[0]["solved"] is False
    assert result.attempts[0]["headless"] is True
    assert result.attempts[1]["headless"] is False
    assert result.attempts[2]["solved"] is True


def test_stealth_browser_headless_fallback() -> None:
    calls: list[bool] = []

    def fake_solve(
        engine: str,
        url: str,
        **kwargs: object,
    ) -> StealthBrowserResult:
        headless = bool(kwargs.get("headless"))
        calls.append(headless)
        if headless:
            return StealthBrowserResult(
                url=url,
                html="<html><title>Just a moment...</title></html>",
                engine=engine,
            )
        return StealthBrowserResult(
            url=url,
            html="<html><body>ok</body></html>",
            cookies=[
                {
                    "name": "cf_clearance",
                    "value": "xyz",
                    "domain": "example.com",
                    "path": "/",
                }
            ],
            engine=engine,
        )

    with (
        mock.patch(
            "stealth_browser.available_stealth_engines",
            return_value=["patchright"],
        ),
        mock.patch("stealth_browser._solve_engine", side_effect=fake_solve),
    ):
        result = solve_cloudflare_with_stealth_browser(
            "https://example.com/",
            engine="patchright",
            auto_install=False,
            max_attempts=1,
            retry_delay=0,
        )
    assert result.engine == "patchright"
    assert calls == [True, False]
    assert result.attempts[0]["headless"] is True
    assert result.attempts[1]["headless"] is False


def test_stealth_browser_headless_fallback_disabled() -> None:
    calls: list[bool] = []

    def fake_solve(
        engine: str,
        url: str,
        **kwargs: object,
    ) -> StealthBrowserResult:
        headless = bool(kwargs.get("headless"))
        calls.append(headless)
        return StealthBrowserResult(
            url=url,
            html="<html><title>Just a moment...</title></html>",
            engine=engine,
        )

    with (
        mock.patch(
            "stealth_browser.available_stealth_engines",
            return_value=["patchright"],
        ),
        mock.patch("stealth_browser._solve_engine", side_effect=fake_solve),
    ):
        result = solve_cloudflare_with_stealth_browser(
            "https://example.com/",
            engine="patchright",
            auto_install=False,
            headless_fallback=False,
            max_attempts=1,
            retry_delay=0,
        )
    assert result.error == "cloudflare challenge did not clear"
    assert calls == [True]


def test_stealth_browser_looks_solved_with_clearance_cookie() -> None:
    result = StealthBrowserResult(
        url="https://example.com/",
        html="<html><title>Just a moment...</title></html>",
        vendor="cloudflare",
        cookies=[
            {
                "name": "cf_clearance",
                "value": "abc",
                "domain": "example.com",
                "path": "/",
            }
        ],
    )
    assert _looks_solved(result) is False
    result.cookies = []
    assert _looks_solved(result) is False


def test_stealth_challenge_markers_no_turnstile_false_positive() -> None:
    html = """
    <html><body>
      <script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
      <div class="cf-turnstile" data-sitekey="0xAAAA"></div>
      <input type="hidden" name="cf-turnstile-response" id="cf-chl-widget-test_response">
    </body></html>
    """
    assert _challenge_pending(html) is False
    result = StealthBrowserResult(url="https://example.com/", html=html)
    assert _looks_solved(result) is True


def test_stealth_browser_storage_state_propagates() -> None:
    seen: list[str | None] = []

    def fake_solve(
        engine: str,
        url: str,
        **kwargs: object,
    ) -> StealthBrowserResult:
        seen.append(kwargs.get("storage_state"))
        return StealthBrowserResult(
            url=url,
            html="<html><body>ok</body></html>",
            engine=engine,
        )

    with (
        mock.patch(
            "stealth_browser.available_stealth_engines",
            return_value=["patchright"],
        ),
        mock.patch("stealth_browser._solve_engine", side_effect=fake_solve),
    ):
        result = solve_cloudflare_with_stealth_browser(
            "https://example.com/",
            engine="patchright",
            auto_install=False,
            headless=False,
            headless_fallback=False,
            storage_state="state/account.json",
            max_attempts=1,
            retry_delay=0,
        )
    assert result.engine == "patchright"
    assert _looks_solved(result) is True
    assert seen == ["state/account.json"]


def test_stealth_browser_wait_clicks_challenge_once() -> None:
    clicks: list[int] = []

    def html_getter() -> str:
        return "<html><title>Just a moment...</title></html>"

    def cookie_getter() -> list[dict[str, str]]:
        return []

    def click_callback() -> None:
        clicks.append(1)

    ready = _wait_for_browser_ready(
        html_getter,
        cookie_getter,
        900,
        click_callback=click_callback,
    )
    assert ready is False
    assert len(clicks) == 1


def test_challenge_click_human_click() -> None:
    class FakeElement:
        def bounding_box(self) -> dict[str, float]:
            return {"x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0}

        def scroll_into_view_if_needed(self, timeout: float = 0) -> None:
            return None

    class FakeMouse:
        def __init__(self) -> None:
            self.clicks: list[tuple[float, float]] = []

        def move(self, x: float, y: float) -> None:
            return None

        def click(self, x: float, y: float) -> None:
            self.clicks.append((x, y))

    class FakePage:
        mouse = FakeMouse()

    assert human_click(FakeElement(), FakePage()) is True
    assert len(FakePage.mouse.clicks) == 1


def test_challenge_click_shadow_and_managed_fallback() -> None:
    class FakePage:
        def evaluate(self, script: str) -> bool:
            return True

    assert click_shadow_dom(FakePage()) is True
    assert click_managed_challenge(FakePage()) is True


def test_cloudflare_state_and_handler() -> None:
    state = extract_cloudflare_state(
        "<html><body>ok</body></html>",
        "https://example.com/",
        cookies=[{"name": "cf_clearance", "value": "x", "domain": "example.com", "path": "/"}],
    )
    assert state.stage == "passed"
    handler = CloudflareChallengeHandler(
        CloudflareChallengeConfig(
            max_attempts=1,
            wait_timeout=100,
            clearance_timeout=100,
            poll_interval=0.01,
            auto_click=False,
            solve_turnstile=False,
            reload_before_retry=False,
        )
    )
    result = handler.run(
        _FakePage("<html>challenge</html>"), _FakeContext(clearance=True), "https://example.com/"
    )
    assert isinstance(result, CloudflareChallengeResult)
    assert result.passed


def test_ensure_dependencies_status() -> None:
    status = ensure_status()
    names = {item["name"] for item in status["packages"]}
    assert {
        "curl_cffi",
        "tls_client",
        "cloudscraper",
        "httpx",
        "h2",
        "patchright",
        "nodriver",
        "DrissionPage",
        "selenium",
        "seleniumbase",
        "undetected_chromedriver",
        "webdriver_manager",
        "selenium_stealth",
        "camoufox",
        "scrapling",
        "cryptography",
    }.issubset(names)
    assert set(missing_packages()).issubset(names)
    assert ensure_dependencies(install=False)["ready"] == status["ready"]


def test_flaresolverr_client() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FlaresolverrHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        client = FlaresolverrClient(base_url=base, timeout=5)
        result = client.request_get("https://example.com/")
        assert result.status == 200
        assert "solved" in result.body
        assert any(item["name"] == "cf_clearance" for item in result.cookies)
    finally:
        server.shutdown()


def test_stealth_browser_engine_availability() -> None:
    engines = set(available_stealth_engines())
    assert engines.issubset(
        {
            "patchright",
            "camoufox",
            "scrapling",
            "nodriver",
            "seleniumbase",
            "undetected_chromedriver",
            "drission_page",
            "selenium",
        }
    )
    try:
        solve_cloudflare_with_stealth_browser("https://example.com/", engine="unsupported")
        raise AssertionError("unsupported engine must raise")
    except StealthBrowserError:
        pass


def test_login_detector_auto_form_and_login_url() -> None:
    html = """
    <html><body>
      <a href="/login">登录</a>
      <form action="/api/login" method="post">
        <input name="email" placeholder="邮箱">
        <input type="password" name="password">
        <button type="submit">立即登录</button>
      </form>
    </body></html>
    """
    detection = detect_login(html, "https://example.com/")
    assert detection.form is not None
    assert detection.form.complete
    assert "input[name='email']" in detection.form.username_selector
    assert detection.form.password_selector == "input[name='password']"
    assert any(url.endswith("/login") for url in detection.login_urls)
    analysis = analyze_page(html, base_url="https://example.com/")
    assert analysis.login is not None and analysis.login.form is not None


def test_hls_client_resolve_and_download_local() -> None:
    master = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=1280x720\n"
        "media.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360\n"
        "media_360.m3u8\n"
    )
    media = (
        "#EXTM3U\n"
        "#EXT-X-TARGETDURATION:4\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n"
        "#EXTINF:4.0,\n"
        "seg1.ts\n"
        "#EXTINF:4.0,\n"
        "seg2.ts\n"
        "#EXT-X-ENDLIST\n"
    )
    base, server = _start_server(
        {
            "/master.m3u8": master.encode("utf-8"),
            "/media.m3u8": media.encode("utf-8"),
            "/media_360.m3u8": media.encode("utf-8"),
            "/seg1.ts": b"segment-one",
            "/seg2.ts": b"segment-two",
        }
    )
    try:
        client = HLSClient(
            session=MediaSession(min_interval=0.0, max_retries=0)
        )
        resolution = client.resolve(
            f"{base}/master.m3u8",
            preferred_height=720,
        )
        assert resolution.is_master
        assert resolution.variant is not None
        assert resolution.variant.resolution == "1280x720"
        with tempfile.TemporaryDirectory() as tmp:
            result = client.download(
                f"{base}/master.m3u8",
                Path(tmp),
                preferred_height=720,
                include_segments=True,
                combine=True,
            )
            assert result.downloaded_segments == 2
            assert result.combined_path is not None
            assert Path(result.combined_path).read_bytes() == b"segment-onesegment-two"
    finally:
        server.shutdown()


def test_block_diagnoser_cloudflare_retry() -> None:
    report = diagnose_response(
        "https://example.com/",
        403,
        {
            "cf-ray": "abc123",
            "server": "cloudflare",
            "retry-after": "5",
        },
        "<html>Just a moment... Enable JavaScript</html>",
    )
    assert report.challenge_retry is True
    assert report.proxy_recommended is True
    assert report.browser_recommended is True
    assert report.cloudflare.present is True
    assert report.retry_after == 5.0


def test_stealth_patch_helpers() -> None:
    assert STEALTH_JS

    class FakeContext:
        def __init__(self) -> None:
            self.scripts: list[str] = []

        def add_init_script(self, script: str) -> None:
            self.scripts.append(script)

    context = FakeContext()
    apply_playwright_stealth(context)
    assert len(context.scripts) == 1
    assert "webdriver" in context.scripts[0]


def test_media_crawler_local_jsonl_and_downloads() -> None:
    master = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=1280x720\n"
        "media.m3u8\n"
    )
    media = (
        "#EXTM3U\n"
        "#EXT-X-TARGETDURATION:4\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n"
        "#EXTINF:4.0,\n"
        "seg1.ts\n"
        "#EXT-X-ENDLIST\n"
    )
    base, server = _start_server(
        {
            "/index.html": (
                b'<html><body><a href="/a.html">A</a>'
                b'<img src="/img.jpg"><video src="/v.mp4"></video>'
                b'<audio src="/a.mp3"></audio><a href="/master.m3u8">HLS</a>'
                b"</body></html>"
            ),
            "/a.html": b"<html><body>leaf</body></html>",
            "/robots.txt": b"User-agent: *\nDisallow:\n",
            "/img.jpg": b"image-bytes",
            "/v.mp4": b"video-bytes",
            "/a.mp3": b"audio-bytes",
            "/master.m3u8": master.encode("utf-8"),
            "/media.m3u8": media.encode("utf-8"),
            "/seg1.ts": b"hls-segment",
        }
    )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = MediaCrawlConfig(
                seeds=[f"{base}/index.html"],
                max_depth=1,
                max_pages=10,
                same_host=True,
                respect_robots=True,
                sitemap=False,
                max_workers=2,
                min_interval=0.0,
                jitter=0.0,
                max_retries=0,
                fetch_backend="standard",
                fetch_auto_install=False,
                download_media=True,
                output_dir=str(root / "media"),
                jsonl_path=str(root / "crawl.jsonl"),
                resume=False,
                max_media_workers=2,
                min_media_interval=0.0,
            )
            result = MediaCrawler(config).run()
            urls = {page.url for page in result.pages}
            assert any(url.endswith("/a.html") for url in urls)
            assert result.summary()["media_discovered"] >= 4
            assert result.summary()["media_downloaded"] >= 4
            media_root = root / "media"
            assert (media_root / "image").exists()
            assert (media_root / "video").exists()
            assert (media_root / "audio").exists()
            assert (media_root / "hls" / "combined.ts").exists()
            jsonl = (root / "crawl.jsonl").read_text(encoding="utf-8")
            assert '"kind": "page"' in jsonl
            assert '"kind": "hls"' in jsonl
            resume_config = MediaCrawlConfig(
                seeds=[f"{base}/index.html"],
                max_depth=1,
                max_pages=10,
                same_host=True,
                respect_robots=True,
                sitemap=False,
                max_workers=2,
                min_interval=0.0,
                max_retries=0,
                fetch_backend="standard",
                fetch_auto_install=False,
                download_media=True,
                output_dir=str(media_root),
                jsonl_path=str(root / "crawl.jsonl"),
                resume=True,
                max_media_workers=2,
                min_media_interval=0.0,
            )
            resumed = MediaCrawler(resume_config).run()
            assert resumed.summary()["pages"] == 0
            assert resumed.summary()["media_downloaded"] == 0
    finally:
        server.shutdown()


def test_url_deduplicator_sqlite() -> None:
    with UrlDeduplicator(":memory:") as store:
        assert store.add("https://example.com/a")
        assert not store.add("https://example.com/a")
        assert store.add("https://example.com/b")
        assert store.count() == 2
        assert store.checkpoint()["seen_urls"] == 2


def test_auto_data_extractor_tables_and_validation() -> None:
    html = """
    <html><body>
      <table><tr><th>name</th><th>price</th></tr>
      <tr><td>Apple</td><td>10</td></tr>
      <tr><td>Banana</td><td>20</td></tr></table>
      <script type="application/ld+json">
        {"items":[{"id":1,"title":"A"},{"id":2,"title":"B"}]}
      </script>
    </body></html>
    """
    result = AutoDataExtractor().analyze(html, "https://example.com/")
    assert len(result.records) >= 4
    assert "price" in result.schema
    assert result.validation.valid_count == len(result.records)
    assert structure_signature(html) == structure_signature(html)
    assert infer_schema(result.records)["title"].type == "string"


def test_human_behavior_rotation_and_delay() -> None:
    behavior = HumanBehavior(seed=1, min_delay=0.0, max_delay=0.0, jitter=0.0)
    first = behavior.next_user_agent()
    second = behavior.next_user_agent()
    assert first != second
    assert behavior.delay() == 0.0


def test_autonomous_crawler_local_async() -> None:
    index = """
    <html><body>
      <a href="/a.html">A</a>
      <script type="application/ld+json">
        {"items":[{"id":1,"title":"A"},{"id":2,"title":"B"}]}
      </script>
      <img src="/img.jpg">
    </body></html>
    """
    base, server = _start_server(
        {
            "/index.html": index.encode("utf-8"),
            "/a.html": b"<html><body>leaf</body></html>",
            "/img.jpg": b"image",
        }
    )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AutonomousCrawlerConfig(
                seeds=[f"{base}/index.html"],
                max_urls=10,
                max_depth=1,
                same_host=True,
                max_concurrency=2,
                min_delay=0.0,
                max_delay=0.0,
                jitter=0.0,
                max_retries=0,
                respect_robots=False,
                sitemap=False,
                dynamic_render=False,
                url_db_path=str(root / "urls.sqlite3"),
                jsonl_path=str(root / "crawl.jsonl"),
                output_media=True,
                checkpoint_interval=2,
            )
            summary = AutonomousCrawler(config).run()
            assert summary["stats"]["seen"] >= 2
            assert summary["stats"]["records"] >= 2
            assert summary["stats"]["media"] >= 1
            jsonl = (root / "crawl.jsonl").read_text(encoding="utf-8")
            assert '"kind": "record"' in jsonl
    finally:
        server.shutdown()


def test_stealth_patch_bank_compose() -> None:
    payload = compose_patches(["webdriver", "canvas", "webgl"])
    assert "webdriver" in payload
    assert "CanvasRenderingContext2D" in payload
    assert "WebGLRenderingContext" in payload
    assert "CanvasRenderingContext2D" in STEALTH_JS
    assert "WebGL2RenderingContext" in STEALTH_JS
    assert "userAgentData" in STEALTH_JS


def test_stealth_patch_bank_fingerprint_values() -> None:
    payload = compose_patches(
        ["navigator", "user_agent_data", "languages_timezone"],
        values={
            "user_agent": "UA-X",
            "timezone_id": "America/New_York",
            "languages": ["en-US"],
            "ua_data_platform": "macOS",
        },
    )
    assert "UA-X" in payload
    assert "America/New_York" in payload
    assert '"en-US"' in payload
    assert '"macOS"' in payload


def test_stealth_patch_bank_deep_camouflage() -> None:
    payload = compose_patches(
        [
            "automation_markers",
            "webgl_deep",
            "audio_deep",
            "speech_synthesis",
            "date_timezone",
        ],
        values={
            "timezone_offset": 240,
            "webgl_vendor": "AMD",
            "webgl_renderer": "AMD Radeon",
        },
    )
    assert "automationMarkers" in payload
    assert "getFloatFrequencyData" in payload
    assert "speechSynthesis" in payload
    assert "__TIMEZONE_OFFSET__" not in payload
    assert "240" in payload
    assert "AMD" in payload


def test_browser_flags_anti_detect_args() -> None:
    profile = BrowserLaunchProfile(headless=True)
    args = profile.args()
    assert "--disable-background-networking" in args
    assert "--use-mock-keychain" in args
    assert "--disable-client-side-phishing-detection" in args
    assert "--disable-blink-features=AutomationControlled" in ANTI_DETECT_ARGS


def test_cloudflare_header_signals_and_recommended_action() -> None:
    state = extract_cloudflare_state(
        "",
        headers={"cf-mitigated": "challenge", "cf-ray": "abc1234567890def"},
    )
    assert state.present is True
    handler = CloudflareChallengeHandler()
    assert handler.recommended_action(state) == "click"

    turnstile_state = extract_cloudflare_state(
        '<div class="cf-turnstile" data-sitekey="0xAAAA"></div>',
        headers={"cf-mitigated": "challenge"},
    )
    assert turnstile_state.stage == "turnstile_captcha"

    class FakeSolver:
        def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
            return CaptchaResult(success=True, task_id="t", answer="token")

    solver_handler = CloudflareChallengeHandler(captcha_solver=FakeSolver())
    assert solver_handler.recommended_action(turnstile_state) == "solve"


def test_security_report_strategy() -> None:
    report = detect_security_mechanisms(
        200,
        "https://example.com/",
        {},
        "Checking your browser before accessing...",
        html="<html>Just a moment...</html>",
    )
    assert report.strategy == "browser"
    assert "browser" in report.actions


def test_security_report_normal_200_with_marketing_copy_not_blocked() -> None:
    html = """
    <html><head><title>Cloudflare Turnstile - Easy CAPTCHA alternative</title></head>
    <body>
      <p>Integrate Turnstile with Cloudflare WAF rules to improve user experiences
         while blocking bots. Read the docs about rate limits and challenge flows.</p>
      <script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
      <div class="cf-turnstile" data-sitekey="0xAAAA"></div>
    </body></html>
    """
    report = detect_security_mechanisms(
        200,
        "https://www.cloudflare.com/products/turnstile/",
        {"cf-ray": "abc123", "server": "cloudflare"},
        html,
        html=html,
    )
    assert report.is_blocked is False
    assert report.primary_kind is None


def test_security_report_200_with_vendor_headers_not_blocked() -> None:
    html = """
    <html><head><script src="/assets/_abck.js"></script></head>
    <body>Product page content served by Akamai.</body></html>
    """
    report = detect_security_mechanisms(
        200,
        "https://www.farfetch.com/",
        {"server": "AkamaiGHost", "x-akamai-transformed": "9 - 0 0, text/html"},
        html,
        html=html,
    )
    assert report.is_blocked is False
    assert report.primary_kind is None


def test_security_report_200_captcha_widget_not_blocked() -> None:
    html = """
    <html><body>
      <form><div class="cf-turnstile" data-sitekey="0xAAAA"></div></form>
    </body></html>
    """
    report = detect_security_mechanisms(
        200,
        "https://example.com/contact",
        {},
        html,
        html=html,
    )
    assert report.is_blocked is False
    assert report.primary_kind is None


def test_security_report_large_200_with_waf_and_login_wording_not_blocked() -> None:
    html = (
        "<html><head><title>Farfetch China</title></head><body>"
        "<p>access denied</p><p>sign in to continue</p>"
        + "<div>real product content</div>" * 3000
        + "</body></html>"
    )
    report = detect_security_mechanisms(
        200,
        "https://www.farfetch.com/",
        {"server": "AkamaiGHost"},
        html,
        html=html,
    )
    assert len(html) >= 20000
    assert report.is_blocked is False
    assert report.primary_kind is None


def test_security_report_detects_ip_reputation_block() -> None:
    html = (
        "<html><body><h1>Humans only</h1>"
        "<p>Cloudflare Location: CN</p>"
        "<p>Your IP address: 203.0.113.10</p></body></html>"
    )
    report = detect_security_mechanisms(
        403,
        "https://www.glassdoor.com/",
        {"cf-ray": "abc123"},
        html,
        html=html,
    )
    assert report.primary_kind == "ip_reputation_blocked"
    assert report.needs_proxy is True
    assert report.strategy == "proxy"


def test_turnstile_iframe_sitekey_detection() -> None:
    html = (
        '<iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/'
        'h/g/orchestrate/jsch/v1?sitekey=0xBBBB"></iframe>'
    )
    widgets = detect_turnstile_widgets(html, "https://example.com/")
    assert any(widget.sitekey == "0xBBBB" for widget in widgets)


def test_turnstile_ready_variable_sitekey_and_dotted_callback() -> None:
    html = """
    <html><body>
      <script>
        const SITE_KEY = "0xCCCC";
        const ACTION = "checkout";
        turnstile.ready(function () {
          turnstile.render(document.getElementById("widget"), {
            sitekey: SITE_KEY,
            action: ACTION,
            callback: "app.captcha.onToken",
            execution: "execute",
            size: "compact",
          });
        });
      </script>
    </body></html>
    """
    widgets = detect_turnstile_widgets(html, "https://example.com/checkout")
    widget = next(item for item in widgets if item.sitekey == "0xCCCC")
    assert widget.action == "checkout"
    assert widget.callback == "app.captcha.onToken"
    assert widget.execution == "execute"
    assert widget.size == "compact"


def test_turnstile_dynamic_shadow_dom_detection() -> None:
    class FakePage:
        def content(self) -> str:
            return "<html><body></body></html>"

        def evaluate(self, script: str, *args: object) -> list[dict[str, str]]:
            return [
                {
                    "sitekey": "0xDDDD",
                    "action": "login",
                    "execution": "render",
                    "appearance": "always",
                }
            ]

    solver = TurnstileSolver()
    widgets = solver.detect(FakePage(), "https://example.com/")
    assert widgets and widgets[0].sitekey == "0xDDDD"
    assert widgets[0].action == "login"


def test_turnstile_inject_dotted_callback_and_reset() -> None:
    scripts: list[str] = []

    class FakePage:
        def evaluate(self, script: str, *args: object) -> bool:
            scripts.append(script)
            return True

    widget = TurnstileWidget(sitekey="0xAAAA", callback="app.captcha.onToken")
    solver = TurnstileSolver(config={"auto_click": False})
    assert solver._inject_token(FakePage(), widget, "token-xyz") is True
    assert any('"captcha"' in script and '"onToken"' in script for script in scripts)
    assert any("turnstile.reset" in script for script in scripts)


def test_turnstile_execute_passes_widget_and_action() -> None:
    calls: list[tuple[str, object]] = []

    class FakePage:
        def evaluate(self, script: str, *args: object) -> bool:
            calls.append((script, args[0] if args else None))
            return True

    widget = TurnstileWidget(
        sitekey="0xAAAA",
        widget_id="widget",
        action="login",
        execution="execute",
    )
    solver = TurnstileSolver(config={"auto_click": False})
    assert solver._execute_widget(FakePage(), widget) is True
    assert calls and calls[0][1] == {
        "widget_id": "widget",
        "sitekey": "0xAAAA",
        "action": "login",
    }


def test_smart_fetch_curl_impersonate_mapping() -> None:
    session = SmartFetchSession(impersonate="chrome_124")
    assert session._curl_impersonate() == "chrome124"
    firefox = SmartFetchSession(impersonate="firefox_127")
    assert firefox._curl_impersonate() == "firefox127"


def test_media_session_proxy_pinning() -> None:
    pool = ProxyPool(["http://p1:8080", "http://p2:8080"])
    session = MediaSession(proxy_pool=pool)
    session.pin_proxy("http://p1:8080")
    assert session._current_proxy() == "http://p1:8080"
    session._report_proxy_failure("http://p1:8080")
    assert session._pinned_proxy is None


def test_stealth_engine_preflight() -> None:
    report = preflight_stealth_engines()
    assert any(item["engine"] == "patchright" for item in report)
    assert all(item["installed"] in {True, False} for item in report)
    assert all(isinstance(item["browser_path"], str | None) for item in report)


def test_fingerprint_bank_and_header_profiles() -> None:
    chrome = HeaderFingerprint.chrome()
    headers = chrome.apply({"User-Agent": "custom"})
    assert headers["Sec-CH-UA"] == '"Chromium";v="126", "Google Chrome";v="126", "Not=A?Brand";v="99"'
    firefox = HeaderFingerprint.for_browser("firefox")
    assert firefox.name == "firefox"
    bank = FingerprintBank(
        profiles=[
            BrowserFingerprint(),
            BrowserFingerprint(user_agent="Mozilla/5.0 other"),
        ]
    )
    first = bank.next()
    second = bank.next()
    assert isinstance(first, BrowserFingerprint)
    assert first.user_agent != second.user_agent


def test_fingerprint_binding_full_chain() -> None:
    chrome = resolve_binding("chrome126")
    assert chrome is not None
    assert chrome.validate() == []
    assert chrome.tls_impersonate == "chrome_124"
    assert "Chrome/126" in chrome.user_agent
    headers = chrome.to_header_headers()
    assert headers["User-Agent"] == chrome.user_agent
    assert "Sec-CH-UA" in headers

    firefox = resolve_binding("firefox127")
    assert firefox is not None
    assert "Firefox/127" in firefox.user_agent
    assert "firefox" in firefox.tls_impersonate
    assert firefox.compatible_engines

    cfg = apply_binding_to_fetch_config({"browser": {"engine": "auto"}}, chrome)
    assert cfg["impersonate"] == "chrome_124"
    assert cfg["header_fingerprint"] == "chrome"
    assert cfg["browser"]["fingerprint_binding"] == "chrome126"
    assert "patchright" in cfg["browser"]["stealth_engine_order"]

    manager = FingerprintManager(fingerprint_binding="firefox127")
    session = manager.next()
    assert session.binding_name == "firefox127"
    assert session.headers["User-Agent"] == session.browser.user_agent
    assert session.tls_impersonate == "firefox_124"
    assert "chrome126" in available_bindings()


def test_fingerprint_manager_firefox_does_not_leak_chromium_apis() -> None:
    manager = FingerprintManager(fingerprint_binding="firefox127")
    session = manager.next()
    values = session.stealth_values
    assert values["browser_kind"] == "firefox"
    assert values["ua_data_brands"] == []
    assert "userAgentData" not in session.stealth_js
    assert "--timezone=Asia/Shanghai" in session.launch_profile.args()


def test_fingerprint_manager_edge_brands_and_canvas_seed() -> None:
    manager = FingerprintManager(fingerprint_binding="edge126")
    session = manager.next()
    values = session.stealth_values
    assert values["browser_kind"] == "edge"
    assert values["ua_data_brands"][1]["brand"] == "Microsoft Edge"
    assert "canvas_seed" in values
    assert values["timezone_offset"] == -480


def test_stealth_patch_bank_family_filter_and_seeded_canvas() -> None:
    firefox_payload = compose_patches(
        values={
            "browser_kind": "firefox",
            "user_agent": "Mozilla/5.0 Firefox/127.0",
        }
    )
    assert "userAgentData" not in firefox_payload
    assert "window.chrome" not in firefox_payload
    canvas_payload = compose_patches(["canvas"], values={"canvas_seed": 42})
    assert "42" in canvas_payload
    date_payload = compose_patches(["date_timezone"], values={"timezone_offset": 240})
    assert "const timezoneSuffix" in date_payload
    assert "240" in date_payload
    assert "toTimeString" in date_payload


def test_browser_flags_timezone_arg() -> None:
    profile = BrowserLaunchProfile(headless=True, timezone_id="Asia/Tokyo")
    assert "--timezone=Asia/Tokyo" in profile.args()


def test_browser_session_patch_values_consistent() -> None:
    from browser_session import FingerprintOptions

    options = FingerprintOptions.generate(seed=7)
    values = options.patch_values()
    assert values["browser_kind"] == "chrome"
    assert "canvas_seed" in values
    assert values["timezone_offset"] == -480
    assert values["ua_data_brands"][1]["brand"] == "Google Chrome"


def test_proxy_pool_socks_auth_region_and_source_refill() -> None:
    pool = ProxyPool.from_config(
        {
            "proxies": ["socks5://127.0.0.1:1080"],
            "default_auth": "user:pass",
            "min_pool_size": 2,
            "source": {
                "url": "https://provider.invalid/list",
                "format": "json",
                "json_path": "data",
            },
            "auto_remove_on_fail": True,
        }
    )
    pool.add("http://p1:8080", country="US", city="Dallas", provider="residential")
    assert pool.get_proxy_for(country="US") == "http://user:pass@p1:8080"
    assert pool.get_proxy_for(country="CN") is None
    assert pool.get_proxy_for(city="dallas") == "http://user:pass@p1:8080"

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def read(self) -> bytes:
            return self._body

    def fake_open(_request: object, timeout: float = 0.0) -> FakeResponse:
        payload = json.dumps(
            {
                "data": [
                    {"proxy": "http://p2:8080", "country": "JP"},
                    {"proxy": "http://p3:8080", "country": "DE"},
                ]
            }
        )
        return FakeResponse(payload.encode("utf-8"))

    with mock.patch("proxy_pool.urllib.request.urlopen", side_effect=fake_open):
        added = pool.refresh_from_source()
    assert added == 2
    assert pool.get_proxy_for(country="JP") == "http://user:pass@p2:8080"
    assert pool.get_proxy_for(country="DE") == "http://user:pass@p3:8080"

    pool.report_failure("http://user:pass@p2:8080")
    pool.report_failure("http://user:pass@p2:8080")
    pool.report_failure("http://user:pass@p2:8080")
    assert "http://user:pass@p2:8080" not in pool.healthy_proxies()


def test_multi_captcha_solver_fallback() -> None:
    class FailingProvider:
        def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
            raise CaptchaError("provider down")

    class WorkingProvider:
        def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
            return CaptchaResult(success=True, task_id="ok", answer="token")

    solver = MultiCaptchaSolver([FailingProvider(), WorkingProvider()])
    result = solver.solve_turnstile("sitekey", "https://example.com/")
    assert result.answer == "token"


def test_adaptive_policy_recommendation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "policy.jsonl"
        store = AdaptivePolicyStore(path)
        store.record(host="example.com", stage="turnstile_captcha", engine="patchright", success=True)
        store.record(host="example.com", stage="turnstile_captcha", engine="nodriver", success=False)
        recommended = store.recommend(
            "example.com",
            "turnstile_captcha",
            ["patchright", "nodriver"],
        )
        assert recommended[0] == "patchright"
        assert store.stats("example.com", "turnstile_captcha")["success_rate"] == 0.5


def test_adaptive_policy_variant_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "policy.jsonl"
        store = AdaptivePolicyStore(path)
        store.record_variant(
            host="example.com",
            vendor="akamai",
            signature="sig-a",
            stage="akamai_sensor",
            success=True,
            engine="patchright",
        )
        store.record_variant(
            host="example.com",
            vendor="akamai",
            signature="sig-b",
            stage="akamai_sensor",
            success=False,
            engine="patchright",
        )
        stats = store.variant_stats("example.com", vendor="akamai")
        assert stats["total_variants"] == 2
        assert "sig-a" in store.known_signatures("example.com", vendor="akamai")
        recommended = store.recommend(
            "example.com",
            "akamai_sensor",
            ["patchright", "nodriver"],
            vendor="akamai",
            signature="sig-a",
        )
        assert recommended[0] == "patchright"


def test_challenge_evolution_signature_stable_and_sensitive() -> None:
    first = fingerprint_challenge(
        vendor="datadome",
        stage="datadome_captcha",
        html='<iframe src="https://geo.captcha-delivery.com/captcha"></iframe>',
    )
    same = fingerprint_challenge(
        vendor="datadome",
        stage="datadome_captcha",
        html='<iframe src="https://geo.captcha-delivery.com/captcha"></iframe>',
    )
    changed = fingerprint_challenge(
        vendor="datadome",
        stage="datadome_captcha",
        html='<iframe src="https://geo.captcha-delivery.com/captcha?v=2"></iframe>',
    )
    assert first.signature
    assert first.signature == same.signature
    assert first.signature != changed.signature
    diff = marker_diff(first, changed)
    assert diff["iframe_urls"]


def test_adaptive_policy_should_skip_known_failing_combination() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = AdaptivePolicyStore(Path(tmp) / "policy.jsonl")
        for _ in range(2):
            store.record_variant(
                host="example.com",
                vendor="akamai",
                signature="sig-bad",
                stage="akamai_sensor",
                success=False,
                engine="patchright",
                proxy_region="US",
            )
        assert store.should_skip(
            "example.com",
            "akamai_sensor",
            "patchright",
            vendor="akamai",
            signature="sig-bad",
            proxy_region="US",
        ) is True
        store.record_variant(
            host="example.com",
            vendor="akamai",
            signature="sig-bad",
            stage="akamai_sensor",
            success=True,
            engine="patchright",
            proxy_region="US",
        )
        assert store.should_skip(
            "example.com",
            "akamai_sensor",
            "patchright",
            vendor="akamai",
            signature="sig-bad",
            proxy_region="US",
            max_success_rate=0.2,
        ) is False


def test_vendor_cookie_validation_and_token_injection() -> None:
    assert has_valid_vendor_cookie(
        [{"name": "_abck", "value": "-1~short"}],
        "akamai",
    ) is False
    assert has_valid_vendor_cookie(
        [{"name": "_abck", "value": "1234567890" * 4}],
        "akamai",
    ) is True
    assert has_valid_vendor_cookie(
        [{"name": "datadome", "value": "x"}],
        "datadome",
    ) is False
    assert has_valid_vendor_cookie(
        [{"name": "datadome", "value": "valid-long-token"}],
        "datadome",
    ) is True
    assert extract_vendor_public_key(
        '<div data-pkey="ABCDEFGH"></div>',
        "arkose",
    ) == "ABCDEFGH"

    calls: list[tuple[str, object]] = []

    class FakePage:
        def evaluate(self, script: str, *args: object) -> bool:
            calls.append((script, args[0] if args else None))
            return True

    assert inject_captcha_token(FakePage(), "aws_waf", "token-aws") is True
    assert calls and "aws-waf-token" in json.dumps(calls[0][1], ensure_ascii=False)

    class FakeSolver:
        def solve_awswaf(self, page_url: str):
            return type("Result", (), {"answer": "provider-token"})()

    assert solve_vendor_with_provider(FakeSolver(), "aws_waf", "https://example.com/") == "provider-token"


def test_challenge_replay_snapshot_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        variant = fingerprint_challenge(
            vendor="datadome",
            stage="datadome_captcha",
            html='<iframe src="https://geo.captcha-delivery.com/captcha"></iframe>',
        )
        meta_path = save_challenge_snapshot(
            "https://example.com/login",
            variant=variant,
            html="<html>challenge</html>",
            headers={"x-datadome": "1"},
            cookies=[{"name": "datadome", "value": "abc"}],
            status=403,
            snapshot_dir=Path(tmp),
        )
        assert meta_path is not None
        meta = load_challenge_snapshot(meta_path)
        assert meta["variant"]["signature"] == variant.signature
        assert find_snapshots(Path(tmp), host="example.com")
        diagnosis = diagnose_snapshot(meta, known_signatures={variant.signature})
        assert diagnosis.known is True
        assert diagnosis.vendor == "datadome"


def test_cloudflare_managed_variant_detection() -> None:
    html = (
        '<iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/'
        'h/g/orchestrate/managed/v1?sitekey=0xAAAA"></iframe>'
    )
    state = extract_cloudflare_state(
        html,
        page_url="https://example.com/",
        cookies=[{"name": "cf_chl_rc_ni", "value": "1"}],
    )
    assert state.variant == "managed"
    assert state.signature
    assert state.present is True


def test_slider_and_audio_captcha_detection() -> None:
    sliders = detect_slider_challenges(
        '<div class="geetest_slider" id="slider"><div class="geetest_slider_button"></div></div>'
    )
    assert sliders and sliders[0].selector == "#slider"
    audio = detect_captchas(
        '<audio src="https://example.com/audio.mp3" class="audio-captcha"></audio>',
        "https://example.com/",
    )
    assert any(challenge.kind == "audio" and challenge.audio_url for challenge in audio)


def test_captcha_task_queue() -> None:
    class FakeSolver:
        def __init__(self) -> None:
            self.calls = 0

        def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
            self.calls += 1
            return CaptchaResult(success=True, task_id=f"t-{self.calls}", answer="token")

    solver = FakeSolver()
    queue = CaptchaTaskQueue(solver, workers=2, max_retries=1)
    try:
        future1 = queue.submit("solve_turnstile", "k1", "https://example.com/")
        future2 = queue.submit("solve_turnstile", "k2", "https://example.com/")
        assert future1.result(timeout=10).answer == "token"
        assert future2.result(timeout=10).answer == "token"
        assert queue.status()["stats"]["succeeded"] == 2
    finally:
        queue.shutdown()


def test_metrics_and_alerts() -> None:
    registry = MetricsRegistry()
    registry.inc("task_total")
    registry.inc("task_failed")
    snapshot = registry.snapshot()
    manager = AlertManager(default_alert_rules(), registry=registry)
    fired = manager.evaluate(snapshot)
    assert any(rule.name == "high_failure_rate" for rule in fired)
    text = registry.prometheus_text()
    assert "task_total" in text


def test_metrics_new_challenge_variant_alert() -> None:
    registry = MetricsRegistry()
    registry.inc("variant_new", {"vendor": "akamai", "signature": "sig"})
    manager = AlertManager(default_alert_rules(), registry=registry)
    fired = manager.evaluate(registry.snapshot())
    assert any(rule.name == "new_challenge_variant" for rule in fired)


def test_daemon_runner_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runner = DaemonRunner(
            pid_file=Path(tmp) / "daemon.pid",
            log_file=Path(tmp) / "daemon.log",
            heartbeat_file=Path(tmp) / "daemon.heartbeat",
        )
        runner.stop()
        status = runner.status()
        assert status["running"] is False
        assert Path(tmp).exists()


def test_capsolver_provider_task_polling() -> None:
    provider = CapSolverSolver("key", timeout=5, poll_interval=0)
    with mock.patch.object(
        provider,
        "_request",
        side_effect=[
            {"taskId": "task-1"},
            {"status": "ready", "solution": {"token": "cf-token"}},
        ],
    ):
        result = provider.solve_turnstile("sitekey", "https://example.com/")
    assert result.answer == "cf-token"


def test_proxy_pool_sticky_session() -> None:
    pool = ProxyPool(["http://p1:8080", "http://p2:8080"])
    first = pool.get_sticky_proxy("account-a", ttl=60)
    second = pool.get_sticky_proxy("account-a", ttl=60)
    assert first == second
    assert first in {"http://p1:8080", "http://p2:8080"}
    pool.release_sticky_proxy("account-a")
    assert "account-a" not in pool.sticky_status()


def test_cloudflare_shadow_dom_click() -> None:
    class FakePage:
        def evaluate(self, script: str) -> bool:
            return True

    handler = CloudflareChallengeHandler()
    assert handler._try_click_shadow_dom(FakePage()) is True


def test_turnstile_detection_and_token_inject() -> None:
    html = """
    <html><body>
      <div class="cf-turnstile" data-sitekey="0xAAAA" data-action="login"
           data-callback="onToken" data-execution="execute"></div>
      <script>
        turnstile.render("widget", {sitekey: "0xBBBB", callback: "cb", size: "compact"});
      </script>
    </body></html>
    """
    widgets = detect_turnstile_widgets(html, "https://example.com/login")
    assert any(widget.sitekey == "0xAAAA" for widget in widgets)
    assert any(widget.sitekey == "0xBBBB" for widget in widgets)

    class FakeSolver:
        def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
            return CaptchaResult(success=True, task_id="task", answer="token-123")

    class FakePage:
        def content(self) -> str:
            return html

        def evaluate(self, script: str, *args: object) -> bool:
            return True

    solver = TurnstileSolver(captcha_solver=FakeSolver(), config={"auto_click": False})
    result = solver.solve_page(FakePage(), "https://example.com/login")
    assert result.passed is True
    assert result.token == "token-123"
    assert result.strategy == "token_inject"


def test_resource_downloader_range_resume() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RangeResourceHandler)
    _RangeResourceHandler.payloads = {"/big.bin": b"A" * 100}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            session = MediaSession(min_interval=0.0, max_retries=0)
            downloader = ResourceDownloader(session)
            first = downloader.download(f"{base}/big.bin", Path(tmp))
            assert first.error is None
            assert first.size == 100
            target = Path(first.path)
            target.write_bytes(b"A" * 50)
            resumed = downloader.download(f"{base}/big.bin", Path(tmp), resume=True)
            assert resumed.resumed is True
            assert resumed.size == 100
            assert target.read_bytes() == b"A" * 100
    finally:
        server.shutdown()


def test_resource_store_sqlite() -> None:
    with ResourceStore(":memory:") as store:
        store.mark_failed("https://example.com/a.mp4", "timeout", kind="video")
        assert store.status("https://example.com/a.mp4") == "failed"
        assert store.count("failed") == 1
        failed = store.failed()
        assert failed[0]["retries"] == 1
        store.mark_success(
            "https://example.com/a.mp4",
            path="media/video/a.mp4",
            size=100,
            sha256="abc",
            kind="video",
        )
        assert store.status("https://example.com/a.mp4") == "success"
        assert store.count("failed") == 0


def test_resource_store_cleanup_expiration() -> None:
    with ResourceStore(":memory:") as store:
        store.mark_failed("https://example.com/old.mp4", "timeout", kind="video")
        store.mark_failed("https://example.com/new.mp4", "timeout", kind="video")
        store._conn.execute(
            "UPDATE resources SET updated_at = ? WHERE url = ?",
            (time.time() - 7200, "https://example.com/old.mp4"),
        )
        store._conn.commit()
        result = store.cleanup(older_than_seconds=3600)
        assert result["removed"] == 1
        assert store.status("https://example.com/old.mp4") is None
        assert store.status("https://example.com/new.mp4") == "failed"


def test_run_summary_media_result() -> None:
    assets = [
        MediaAsset(
            url="https://example.com/a.jpg",
            kind="image",
            source_page="https://example.com/",
            downloaded=True,
            path="media/image/a.jpg",
            size=10,
            sha256="abc",
        ),
        MediaAsset(
            url="https://example.com/b.mp4",
            kind="video",
            source_page="https://example.com/",
            error="timeout",
        ),
    ]
    pages = [
        MediaPage(url="https://example.com/", depth=0, status=200),
        MediaPage(url="https://example.com/blocked", depth=1, blocked=True),
    ]
    result = MediaCrawlResult(
        pages=pages,
        media=assets,
        config={
            "output_dir": "media",
            "jsonl_path": "crawl.jsonl",
            "resource_db_path": "state.sqlite3",
        },
    )
    report = media_result_report(result)
    assert report["resource_counts"]["success"] == 2
    assert report["resource_counts"]["failed"] == 1
    assert report["resource_counts"]["blocked"] == 1
    assert any(item["role"] == "media_output" for item in report["save_paths"])


def test_run_summary_jsonl_report() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "crawl.jsonl"
        path.write_text(
            json.dumps(
                {
                    "kind": "image",
                    "url": "https://example.com/a.jpg",
                    "downloaded": True,
                    "path": "media/image/a.jpg",
                    "size": 10,
                    "sha256": "abc",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        report = jsonl_report(path)
        assert report["resources"][0]["status"] == "success"
        assert report["resources"][0]["path"] == "media/image/a.jpg"
        assert report["save_paths"][0]["exists"] is True


def test_resource_status_normalization() -> None:
    assert resource_status({"kind": "media", "url": "x"}) == "discovered"
    assert resource_status({"kind": "page", "url": "x", "blocked": True}) == "blocked"
    assert resource_status({"kind": "page", "url": "x", "status": 200}) == "success"


def test_proxy_pool_health_filtering() -> None:
    pool = ProxyPool(["http://p1:8080", "http://p2:8080"])
    pool.set_health("http://p1:8080", False)
    assert pool.healthy_proxies() == ["http://p2:8080"]
    assert pool.get_proxy() == "http://p2:8080"


def test_proxy_pool_weighted_and_manager() -> None:
    pool = ProxyPool(["http://p1:8080", "http://p2:8080"])
    pool.set_health("http://p2:8080", True, latency_ms=10)
    assert pool.get_weighted_proxy() in {"http://p1:8080", "http://p2:8080"}
    manager = ProxyManager({"main": pool})
    assert manager.get_proxy("main") in {"http://p1:8080", "http://p2:8080"}
    assert "main" in manager.status()


def test_browser_launch_profile_and_fingerprint_manager() -> None:
    class FakeOptions:
        def __init__(self) -> None:
            self.args: list[str] = []
            self.experiments: list[object] = []

        def add_argument(self, value: str) -> None:
            self.args.append(value)

        def add_experimental_option(self, *args: object) -> None:
            self.experiments.append(args)

    options = FakeOptions()
    BrowserLaunchProfile(headless=True).apply_chrome_options(options)
    assert "--headless=new" in options.args
    assert "--disable-blink-features=AutomationControlled" in options.args
    assert "--window-size=1920,1080" in options.args
    assert "--disable-breakpad" in options.args

    manager = FingerprintManager(seed=3)
    session = manager.next()
    assert session.browser.user_agent
    assert session.headers["User-Agent"] == session.browser.user_agent
    assert "Sec-CH-UA" in session.headers
    assert "--headless=new" in session.launch_profile.args()


def test_direct_media_seed_download() -> None:
    base, server = _start_server(
        {
            "/img.jpg": b"direct-image",
        }
    )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = MediaCrawlConfig(
                seeds=[f"{base}/img.jpg"],
                max_depth=1,
                max_pages=5,
                same_host=True,
                respect_robots=False,
                sitemap=False,
                max_workers=1,
                min_interval=0.0,
                max_retries=0,
                fetch_backend="standard",
                fetch_auto_install=False,
                download_media=True,
                output_dir=str(root / "media"),
                jsonl_path=str(root / "crawl.jsonl"),
                resume=False,
                max_media_workers=1,
                min_media_interval=0.0,
            )
            result = MediaCrawler(config).run()
            assert result.summary()["pages"] == 0
            assert result.summary()["media_downloaded"] == 1
    finally:
        server.shutdown()


def test_multi_captcha_provider_cooldown() -> None:
    class AlwaysFail:
        def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
            raise CaptchaError("down")

    solver = MultiCaptchaSolver([AlwaysFail()])
    with suppress(CaptchaError):
        solver.solve_turnstile("k", "https://example.com/")
    assert solver.status()[0]["available"] is False


def test_api_client_specs_and_cookies() -> None:
    base, server = _start_server({"/echo": b""}, _CookieEchoHandler)
    try:
        client = ApiClient(
            cookies=[{"name": "sid", "value": "abc", "domain": "127.0.0.1", "path": "/"}],
            min_interval=0.0,
            max_retries=0,
            backend="auto",
            auto_install=False,
        )
        data = client.fetch_spec(ApiSpec(method="GET", url=f"{base}/echo"))
        assert "sid=abc" in data["cookie"]
    finally:
        server.shutdown()


def test_deep_crawler_local() -> None:
    base, server = _start_server(
        {
            "/index.html": (
                b'<html><body><a href="/a.html">A</a>'
                b'<a href="https://external.example/x">X</a></body></html>'
            ),
            "/a.html": b"<html><body>leaf</body></html>",
            "/robots.txt": b"User-agent: *\nDisallow:\n",
        }
    )
    try:
        result = DeepCrawler(
            CrawlConfig(
                seeds=[f"{base}/index.html"],
                max_depth=1,
                max_pages=10,
                same_host=True,
                min_interval=0.0,
                max_retries=0,
            )
        ).crawl()
        urls = {page.url for page in result.pages}
        assert any(url.endswith("/a.html") for url in urls)
        assert not any("external.example" in url for url in urls)
    finally:
        server.shutdown()


def test_web_data_pipeline_self_test() -> None:
    from web_data_pipeline import main

    assert main(["--self-test"]) == 0


def test_media_crawler_auto_adjust_max_pages() -> None:
    payloads = {
        "/": (
            b'<html><body><a href="/d1">1</a>'
            b'<a href="/d2">2</a><a href="/d3">3</a></body></html>'
        ),
        "/d1": b'<html><body><a href="/p1">p</a></body></html>',
        "/d2": b'<html><body><a href="/p2">p</a></body></html>',
        "/d3": b'<html><body><a href="/p3">p</a></body></html>',
        "/p1": b"<html><body>player</body></html>",
        "/p2": b"<html><body>player</body></html>",
        "/p3": b"<html><body>player</body></html>",
    }
    base, server = _start_server(payloads)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            result = MediaCrawler(
                MediaCrawlConfig(
                    seeds=[f"{base}/"],
                    max_pages=1,
                    max_pages_cap=10,
                    auto_adjust_max_pages=True,
                    max_depth=2,
                    same_host=True,
                    respect_robots=False,
                    sitemap=False,
                    max_workers=1,
                    min_interval=0.0,
                    max_retries=0,
                    fetch_backend="standard",
                    fetch_auto_install=False,
                    download_media=False,
                    output_dir=str(Path(tmp) / "media"),
                    jsonl_path=str(Path(tmp) / "crawl.jsonl"),
                    resume=False,
                )
            ).run()
        urls = {page.url for page in result.pages}
        assert any(url.endswith("/d3") for url in urls)
        assert any(url.endswith("/p1") for url in urls)
    finally:
        server.shutdown()


def test_asset_filename_preserves_extension() -> None:
    mp4 = _asset_filename(
        MediaAsset(
            url="https://example.com/video/clip.mp4",
            kind="video",
            source_page="https://example.com/video/clip.mp4",
        ),
        {},
    )
    assert mp4.endswith(".mp4")
    noext = _asset_filename(
        MediaAsset(
            url="https://example.com/video/123?mime_type=video_mp4",
            kind="video",
            source_page="https://example.com/video/123?mime_type=video_mp4",
        ),
        {},
    )
    assert not noext.endswith(".bin")
    assert _content_type_suffix("video/mp4; charset=utf-8") == ".mp4"


def test_chunked_download_range() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RangeResourceHandler)
    payload = b"chunked-" * 200
    _RangeResourceHandler.payloads = {"/chunk.bin": payload}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with tempfile.TemporaryFile() as handle:
            chunked_download(f"{base}/chunk.bin", handle, chunk_size=256)
            handle.seek(0)
            assert handle.read() == payload
        assert browser_binaries_status()["range_resume"] is True
    finally:
        server.shutdown()


def test_proxy_pool_defaults_to_current_ip() -> None:
    pool = ProxyPool()
    assert pool.get_proxy() == CURRENT_IP_PROXY
    assert pool.healthy_proxies() == [CURRENT_IP_PROXY]
    assert normalize_proxy(CURRENT_IP_PROXY) is None
    assert create_proxy_pool(None) is not None
    session = MediaSession(proxy=CURRENT_IP_PROXY)
    assert session._current_proxy() is None


def test_current_ip_prefers_stun_over_http_egress() -> None:
    pool = ProxyPool()
    with (
        mock.patch("proxy_pool._stun_public_ip", return_value="203.0.113.10"),
        mock.patch.object(pool, "_http_egress_ip", return_value="198.51.100.20"),
    ):
        assert pool.current_ip() == "203.0.113.10"
        assert pool._current_ip_source == "stun"
        status = pool.pool_status()
    assert status["current_ip"] == "203.0.113.10"
    assert status["http_egress_ip"] == "198.51.100.20"


def run() -> int:
    tests = [
        test_smart_fetch_factory_and_status,
        test_smart_fetch_local_fallback,
        test_smart_fetch_switches_backend,
        test_smart_fetch_blocked_metadata,
        test_smart_fetch_preserves_clearance_cookie,
        test_smart_fetch_browser_fallback_merges_cookies,
        test_stealth_browser_auto_cycle_engines,
        test_stealth_browser_headless_fallback,
        test_stealth_browser_headless_fallback_disabled,
        test_stealth_browser_looks_solved_with_clearance_cookie,
        test_stealth_challenge_markers_no_turnstile_false_positive,
        test_stealth_browser_storage_state_propagates,
        test_stealth_browser_wait_clicks_challenge_once,
        test_challenge_click_human_click,
        test_challenge_click_shadow_and_managed_fallback,
        test_cloudflare_state_and_handler,
        test_ensure_dependencies_status,
        test_flaresolverr_client,
        test_stealth_browser_engine_availability,
        test_login_detector_auto_form_and_login_url,
        test_hls_client_resolve_and_download_local,
        test_block_diagnoser_cloudflare_retry,
        test_stealth_patch_helpers,
        test_media_crawler_local_jsonl_and_downloads,
        test_media_crawler_auto_adjust_max_pages,
        test_url_deduplicator_sqlite,
        test_auto_data_extractor_tables_and_validation,
        test_human_behavior_rotation_and_delay,
        test_adaptive_policy_variant_memory,
        test_adaptive_policy_should_skip_known_failing_combination,
        test_challenge_evolution_signature_stable_and_sensitive,
        test_challenge_replay_snapshot_roundtrip,
        test_vendor_cookie_validation_and_token_injection,
        test_cloudflare_managed_variant_detection,
        test_autonomous_crawler_local_async,
        test_stealth_patch_bank_compose,
        test_fingerprint_bank_and_header_profiles,
        test_fingerprint_manager_firefox_does_not_leak_chromium_apis,
        test_fingerprint_manager_edge_brands_and_canvas_seed,
        test_stealth_patch_bank_family_filter_and_seeded_canvas,
        test_browser_flags_timezone_arg,
        test_browser_session_patch_values_consistent,
        test_multi_captcha_solver_fallback,
        test_capsolver_provider_task_polling,
        test_multi_captcha_provider_cooldown,
        test_proxy_pool_sticky_session,
        test_proxy_pool_health_filtering,
        test_proxy_pool_weighted_and_manager,
        test_cloudflare_shadow_dom_click,
        test_turnstile_detection_and_token_inject,
        test_turnstile_ready_variable_sitekey_and_dotted_callback,
        test_turnstile_dynamic_shadow_dom_detection,
        test_turnstile_inject_dotted_callback_and_reset,
        test_turnstile_execute_passes_widget_and_action,
        test_resource_downloader_range_resume,
        test_asset_filename_preserves_extension,
        test_chunked_download_range,
        test_proxy_pool_defaults_to_current_ip,
        test_current_ip_prefers_stun_over_http_egress,
        test_resource_store_sqlite,
        test_metrics_and_alerts,
        test_metrics_new_challenge_variant_alert,
        test_browser_launch_profile_and_fingerprint_manager,
        test_direct_media_seed_download,
        test_api_client_specs_and_cookies,
        test_deep_crawler_local,
        test_web_data_pipeline_self_test,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  [OK]   {test.__name__}")
        except Exception as exc:
            failures += 1
            print(f"  [FAIL] {test.__name__}: {exc}")
    print(f"  Anti-bot scraper: {len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run())
