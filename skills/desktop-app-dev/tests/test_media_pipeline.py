"""Local, network-free tests for the media acquisition templates."""

from __future__ import annotations

import contextlib
import http.server
import io
import json
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from account_manager import AccountManager  # noqa: E402
from api_analyzer import analyze_captures  # noqa: E402
from api_client import ApiClient, ApiSpec, build_api_specs  # noqa: E402
from browser_session import BrowserSession, FingerprintOptions, NetworkCaptureOptions  # noqa: E402
from captcha_solver import (  # noqa: E402
    AutoCaptchaSolver,
    CaptchaChallenge,
    CaptchaError,
    CaptchaResult,
    ManualCaptchaSolver,
    OcrCaptchaSolver,
    detect_captchas,
)
from cloudflare_challenge import (  # noqa: E402
    CloudflareChallengeConfig,
    CloudflareChallengeHandler,
    CloudflareChallengeResult,
    extract_cloudflare_state,
)
from data_processor import load_records, process_records, save_records  # noqa: E402
from deep_crawler import CrawlConfig, DeepCrawler  # noqa: E402
from hls_downloader import download_hls  # noqa: E402
from media_dependencies import _zip_member_is_safe, check_status  # noqa: E402
from media_downloader import download_file, safe_output_name  # noqa: E402
from media_parser import extract_media_urls, parse_m3u8  # noqa: E402
from media_pipeline_service import (  # noqa: E402
    MediaPipelineService,
    _filename_from_url,
    _make_handler,
    _read_json,
)
from media_session import MediaSession  # noqa: E402
from notifier import Notifier  # noqa: E402
from page_data_parser import analyze_page  # noqa: E402
from page_data_parser import main as analyze_page_main  # noqa: E402
from proxy_pool import ProxyPool, ProxyPoolStore  # noqa: E402
from scrape_guard import (  # noqa: E402
    AdaptiveThrottle,
    RateLimiter,
    RetryPolicy,
    RobotsPolicy,
)
from security_detector import SecurityReport, detect_security_mechanisms  # noqa: E402
from task_queue import TaskQueue  # noqa: E402
from task_scheduler import TaskScheduler, next_run_after  # noqa: E402
from web_data_pipeline import (  # noqa: E402
    WebDataPipeline,
)
from web_data_pipeline import (  # noqa: E402
    _SelfTestHandler as WebSelfTestHandler,
)

DEEP_PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <title>Episode 12</title>
  <meta name="description" content="Episode page">
  <meta property="og:image" content="/og.jpg">
  <meta name="twitter:image" content="/twitter.jpg">
  <link rel="canonical" href="https://example.com/e/12">
  <link rel="preload" href="/api/bootstrap.js">
  <base href="https://example.com/e/">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"VideoObject","name":"E12","contentUrl":"https://cdn.example.com/v/12.mp4","thumbnailUrl":"/thumb.jpg"}</script>
  <script id="__NEXT_DATA__" type="application/json">{"buildId":"abc123","page":"/watch/12","props":{"pageProps":{"apiBase":"https://api.example.com/v1","total":120,"hasMore":true,"nextCursor":"abc","playUrl":"/stream/12.m3u8","video":{"src":"https://cdn.example.com/v/12.mp4","poster":"/poster.jpg"}}}}</script>
</head>
<body>
  <video src="/v/12.mp4" poster="/p.jpg"></video>
  <form method="post" action="/api/login">
    <input name="token">
  </form>
  <script src="/assets/app.js"></script>
  <script>
    fetch("/api/items?page=2", {method: "POST"});
    axios.get("/api/detail/12");
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/config");
  </script>
</body>
</html>
"""

DEEP_CAPTCHA_HTML = """<!doctype html>
<html><head>
  <script src="https://www.google.com/recaptcha/api.js" async defer></script>
  <script src="https://hcaptcha.com/1/api.js" async defer></script>
  <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
  <script src="https://static.geetest.com/static/js/geetest.js"></script>
</head><body>
  <div class="g-recaptcha" data-sitekey="6Lc_test_key"></div>
  <div class="h-captcha" data-sitekey="10000000-aaaa-bbbb-cccc-000000000001"></div>
  <div class="cf-turnstile" data-sitekey="0x4AAAAAAA-test"></div>
  <div id="geetest_holder"></div>
  <img src="/captcha.png" alt="captcha">
  <input name="verify_code">
  <script>
    window.gt = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4";
    window.challenge = "challenge123";
  </script>
</body></html>
"""


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    payloads: dict[str, bytes] = {}

    def do_HEAD(self) -> None:
        self._serve(head_only=True)

    def do_GET(self) -> None:
        self._serve(head_only=False)

    def _serve(self, head_only: bool) -> None:
        data = self.payloads.get(self.path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        start = 0
        end = len(data) - 1
        range_header = self.headers.get("Range")
        if range_header:
            match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if match:
                start = int(match.group(1))
                if match.group(2):
                    end = min(int(match.group(2)), end)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
        else:
            self.send_response(200)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        if not head_only:
            self.wfile.write(data[start : end + 1])

    def log_message(self, format: str, *args: object) -> None:
        pass


class _NoLengthHandler(http.server.BaseHTTPRequestHandler):
    """HEAD/GET handler that omits Content-Length and Accept-Ranges."""

    protocol_version = "HTTP/1.0"
    payloads: dict[str, bytes] = {}

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()

    def do_GET(self) -> None:
        data = self.payloads.get(self.path, b"")
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _RetryOnceHandler(http.server.BaseHTTPRequestHandler):
    attempts = 0

    def do_GET(self) -> None:
        type(self).attempts += 1
        if type(self).attempts == 1:
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _BlockingHandler(http.server.BaseHTTPRequestHandler):
    payloads: dict[str, bytes] = {}
    blocked_paths: set[str] = set()

    def do_GET(self) -> None:
        if self.path in type(self).blocked_paths:
            body = (
                b"<html><head><title>Access Denied</title></head><body>Access Denied</body></html>"
            )
            self.send_response(403)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        data = type(self).payloads.get(self.path)
        if data is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        pass


class _PaginationHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        page = int(query.get("page", ["1"])[0])
        body = json.dumps(
            {
                "items": [{"id": page, "name": f"item-{page}"}],
                "total": 3,
                "hasMore": page < 3,
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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


class _FakeRequest:
    def __init__(
        self,
        method: str,
        url: str,
        resource_type: str,
        headers: dict[str, str],
        post_data: str | None = None,
    ) -> None:
        self.method = method
        self.url = url
        self.resource_type = resource_type
        self.headers = headers
        self.post_data = post_data


class _FakeResponse:
    def __init__(
        self,
        request: _FakeRequest,
        status: int,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        self.request = request
        self.status = status
        self.headers = headers
        self.body = body

    def json(self) -> dict:
        return json.loads(self.body.decode("utf-8"))

    def body(self) -> bytes:
        return self.body


class _FakePage:
    def __init__(
        self,
        html: str,
        network: list[tuple[str, str, str, int, dict[str, str], bytes]],
    ) -> None:
        self.html = html
        self.network = network
        self.listeners: dict[str, list[object]] = {}
        self.evaluated: list[tuple[str, tuple[object, ...]]] = []

    def on(self, event: str, callback: object) -> None:
        self.listeners.setdefault(event, []).append(callback)

    def _emit(self, event: str, value: object) -> None:
        for callback in self.listeners.get(event, []):
            callback(value)

    def goto(self, url: str, **kwargs: object) -> None:
        for item in self.network:
            method, request_url, resource_type, status, headers, body = item[:6]
            post_data = item[6] if len(item) > 6 else None
            request = _FakeRequest(
                method,
                request_url,
                resource_type,
                headers,
                post_data=post_data,
            )
            self._emit("request", request)
            self._emit("response", _FakeResponse(request, status, headers, body))

    def wait_for_load_state(self, state: str, timeout: object = None) -> None:
        pass

    def content(self) -> str:
        return self.html

    def evaluate(self, script: str, *args: object) -> bool:
        self.evaluated.append((script, args))
        return True


class _FakeCloudflarePage:
    def __init__(
        self,
        challenge_html: str,
        cleared_html: str = "<html><body>ok</body></html>",
        cleared: bool = False,
    ) -> None:
        self.challenge_html = challenge_html
        self.cleared_html = cleared_html
        self.cleared = cleared
        self.goto_count = 0
        self.evaluated: list[tuple[str, tuple[object, ...]]] = []
        self.url = "https://example.com/"

    def title(self) -> str:
        return "ok" if self.cleared else "Just a moment..."

    def content(self) -> str:
        return self.cleared_html if self.cleared else self.challenge_html

    def goto(self, url: str, **kwargs: object) -> None:
        self.goto_count += 1
        self.cleared = True
        self.url = str(url)

    def evaluate(self, script: str, *args: object) -> object:
        self.evaluated.append((script, args))
        return args[0] if args else None


class _FakeCloudflareContext:
    def __init__(self, clearance: bool = False) -> None:
        self.clearance = clearance

    def cookies(self) -> list[dict[str, object]]:
        if not self.clearance:
            return []
        return [
            {
                "name": "cf_clearance",
                "value": "abc123",
                "domain": "example.com",
                "path": "/",
                "expires": 1999999999,
            }
        ]


class _FakeCaptchaSolver:
    def solve_image(self, image_path: Path) -> CaptchaResult:
        return CaptchaResult(True, "image", answer="ABCD")

    def solve_recaptcha_v2(self, site_key: str, page_url: str) -> CaptchaResult:
        return CaptchaResult(True, "recaptcha_v2", answer="recaptcha-token")

    def solve_recaptcha_v3(
        self,
        site_key: str,
        page_url: str,
        action: str | None = None,
        min_score: float = 0.3,
    ) -> CaptchaResult:
        return CaptchaResult(True, "recaptcha_v3", answer="recaptcha-v3-token")

    def solve_hcaptcha(self, site_key: str, page_url: str) -> CaptchaResult:
        return CaptchaResult(True, "hcaptcha", answer="hcaptcha-token")

    def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
        return CaptchaResult(True, "turnstile", answer="turnstile-token")

    def solve_geetest(
        self,
        gt: str,
        challenge: str,
        page_url: str,
    ) -> CaptchaResult:
        return CaptchaResult(True, "geetest", answer="geetest-token")


class _FailingOcrSolver:
    def solve_image(self, image_path: Path) -> CaptchaResult:
        raise CaptchaError("local OCR unavailable")


class _WebhookHandler(http.server.BaseHTTPRequestHandler):
    received: dict = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        _WebhookHandler.received = json.loads(self.rfile.read(length).decode("utf-8"))
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _start_server(
    payloads: dict[str, bytes],
    handler_cls: type[http.server.BaseHTTPRequestHandler] = _RangeHandler,
) -> tuple[str, http.server.HTTPServer]:
    handler_cls.payloads = payloads
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}", server


def test_task_queue() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "tasks.sqlite"
        queue = TaskQueue(db, max_attempts=2)
        result = queue.self_test()
        assert all(result.values()), result
        assert queue.count() >= 2
        queue.close()

        reopened = TaskQueue(db)
        assert reopened.count() >= 2, "tasks must persist after reopen"
        reopened.close()


def test_task_queue_delayed_retry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        queue = TaskQueue(Path(tmp) / "tasks.sqlite", max_attempts=2)
        queue.enqueue("download", {"url": "x", "dest": "y"})
        claimed = queue.claim_next()
        assert claimed is not None
        queue.fail(claimed.id, "temporary", retry=True, delay_seconds=0.2)
        assert queue.claim_next() is None, "delayed task must not be claimable yet"
        time.sleep(0.35)
        retried = queue.claim_next()
        assert retried is not None and retried.attempts == 2
        queue.close()


def test_media_parser() -> None:
    html = """
    <html><body>
      <video src="/v/1.mp4" poster="/img/poster.jpg"></video>
      <audio src="https://cdn.example.com/a/1.mp3"></audio>
      <source src="/hls/master.m3u8">
      <img data-src="/img/2.jpg">
      <a href="https://example.com/next">next</a>
    </body></html>
    """
    extraction = extract_media_urls(html, base_url="https://example.com/page")
    assert extraction.videos[0].endswith("/v/1.mp4")
    assert "https://cdn.example.com/a/1.mp3" in extraction.audios
    assert extraction.images[0].endswith("/img/2.jpg")
    assert extraction.hls[0].endswith("/hls/master.m3u8")

    master = """
    #EXTM3U
    #EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=1280x720
    /v/720/index.m3u8
    #EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1920x1080
    /v/1080/index.m3u8
    """
    media = """
    #EXTM3U
    #EXT-X-TARGETDURATION:6
    #EXT-X-KEY:METHOD=AES-128,URI="/keys/key.bin"
    #EXTINF:6.0,
    /seg/1.ts
    #EXTINF:6.0,
    /seg/2.ts
    """
    master_playlist = parse_m3u8(master, base_url="https://example.com")
    assert master_playlist.is_master
    assert len(master_playlist.variants) == 2
    media_playlist = parse_m3u8(media, base_url="https://example.com")
    assert len(media_playlist.segments) == 2
    assert media_playlist.keys[0].uri == "https://example.com/keys/key.bin"


def test_deep_page_parser() -> None:
    analysis = analyze_page(DEEP_PAGE_HTML, base_url="https://example.com/watch/12")
    assert analysis.metadata.title == "Episode 12"
    assert analysis.metadata.language == "zh-CN"
    assert analysis.metadata.canonical == "https://example.com/e/12"
    assert analysis.metadata.og_image == "https://example.com/og.jpg"
    assert analysis.media.videos[0] == "https://example.com/v/12.mp4"
    assert analysis.links

    kinds = {block.kind for block in analysis.embedded_json}
    assert {"json-ld", "application-json"}.issubset(kinds)
    next_block = next(block for block in analysis.embedded_json if block.kind == "application-json")
    assert next_block.data["buildId"] == "abc123"

    methods = {(endpoint.method, endpoint.url) for endpoint in analysis.api_endpoints}
    assert ("POST", "https://example.com/api/items?page=2") in methods
    assert ("GET", "https://example.com/api/detail/12") in methods
    assert ("GET", "https://example.com/api/config") in methods
    assert ("POST", "https://example.com/api/login") in methods
    assert ("GET", "https://example.com/assets/app.js") in methods
    assert ("GET", "https://example.com/api/bootstrap.js") in methods
    assert any(url.endswith("/_next/data/abc123/watch/12.json") for _, url in methods)

    assert any(url.endswith("/stream/12.m3u8") for url in analysis.json_media.hls)
    assert any(url.endswith("/v/12.mp4") for url in analysis.json_media.videos)
    assert any(url.endswith("/thumb.jpg") for url in analysis.json_media.images)
    assert "total" in analysis.pagination
    assert "hasmore" in analysis.pagination
    assert any(field.key == "apiBase" for field in analysis.json_api_fields)


def test_browser_network_capture() -> None:
    network = [
        (
            "POST",
            "https://example.com/api/items?page=2",
            "fetch",
            200,
            {"Content-Type": "application/json", "Content-Length": "16"},
            b'{"ok":true,"total":2}',
            '{"page":2}',
        ),
        (
            "GET",
            "https://example.com/assets/app.js",
            "script",
            200,
            {"Content-Type": "application/javascript", "Content-Length": "13"},
            b"console.log(1)",
        ),
    ]
    session = BrowserSession()
    session.page = _FakePage(DEEP_PAGE_HTML, network)
    capture = session.capture_page_data(
        "https://example.com/watch/12",
        network_idle=False,
        capture_options=NetworkCaptureOptions(include_bodies=True),
    )
    assert len(capture.network) == 1, "script resources must be filtered by default"
    entry = capture.network[0]
    assert entry.method == "POST"
    assert entry.status == 200
    assert entry.post_data == '{"page":2}'
    assert entry.request_content_type == "application/json"
    assert entry.json_data == {"ok": True, "total": 2}
    assert len(capture.api_calls()) == 1
    assert capture.analysis is not None
    assert capture.analysis.metadata.title == "Episode 12"

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "capture.json"
        capture.save(out)
        saved = json.loads(out.read_text(encoding="utf-8"))
        assert saved["network"][0]["json"]["total"] == 2


def test_safe_output_name() -> None:
    assert safe_output_name("video.mp4") == "video.mp4"
    assert safe_output_name("../evil.mp4") == "evil.mp4"
    assert safe_output_name("..\\evil.ts") == "evil.ts"
    assert safe_output_name("a/../../b.mp4") == "b.mp4"
    assert safe_output_name("..") == "output.mp4"
    assert safe_output_name("") == "output.mp4"
    assert safe_output_name("CON.mp4") == "_CON.mp4"
    assert ".." not in safe_output_name("..\\..\\evil.mp4")


def test_filename_from_url() -> None:
    assert _filename_from_url("https://cdn.example.com/video.mp4?x=1", ".mp4") == "video.mp4"
    assert (
        _filename_from_url("https://cdn.example.com/%2e%2e/%2e%2e/evil.mp4", ".mp4") == "evil.mp4"
    )
    assert _filename_from_url("https://cdn.example.com/..%2F..%2Fevil.mp4", ".mp4") == "evil.mp4"
    fallback = _filename_from_url("https://cdn.example.com/..", ".mp4")
    assert fallback.endswith(".mp4") and ".." not in fallback
    no_ext = _filename_from_url("https://cdn.example.com/video", ".mp4")
    assert no_ext.endswith(".mp4") and ".." not in no_ext


def test_zip_member_safety() -> None:
    assert _zip_member_is_safe("ffmpeg-7.0/ffmpeg.exe") is True
    assert _zip_member_is_safe("../evil.exe") is False
    assert _zip_member_is_safe("/abs/evil.exe") is False
    assert _zip_member_is_safe("a/../../evil.exe") is False
    assert _zip_member_is_safe("a\\..\\evil.exe") is False


def test_manual_captcha() -> None:
    solver = ManualCaptchaSolver()
    solver.request_captcha()

    def answer_later() -> None:
        solver.submit_answer("ABCD")

    threading.Thread(target=answer_later, daemon=True).start()
    assert solver.wait_for_answer(timeout=5) == "ABCD"


def test_detect_captchas() -> None:
    challenges = detect_captchas(
        DEEP_CAPTCHA_HTML,
        page_url="https://example.com/login",
    )
    recaptcha = next(item for item in challenges if item.kind == "recaptcha_v2" and item.site_key)
    hcaptcha = next(item for item in challenges if item.kind == "hcaptcha" and item.site_key)
    turnstile = next(item for item in challenges if item.kind == "turnstile" and item.site_key)
    geetest = next(item for item in challenges if item.kind == "geetest" and item.site_key)
    image = next(item for item in challenges if item.kind == "image")
    assert recaptcha.site_key == "6Lc_test_key"
    assert hcaptcha.site_key.startswith("10000000")
    assert turnstile.site_key.startswith("0x4")
    assert geetest.site_key == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    assert image.image_url is not None and image.image_url.endswith("/captcha.png")
    assert image.selector == "input[name=verify_code]"


def test_auto_captcha_solver() -> None:
    solver = AutoCaptchaSolver(_FakeCaptchaSolver())
    challenges = detect_captchas(
        DEEP_CAPTCHA_HTML,
        page_url="https://example.com/login",
    )
    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / "captcha.png"
        image_path.write_bytes(b"fake-image")
        solved = solver.solve_detected(challenges, image_paths=[image_path])
    answers = {challenge.kind: answer for challenge, answer in solved}
    assert answers["recaptcha_v2"] == "recaptcha-token"
    assert answers["hcaptcha"] == "hcaptcha-token"
    assert answers["turnstile"] == "turnstile-token"
    assert answers["geetest"] == "geetest-token"
    assert answers["image"] == "ABCD"


def test_browser_auto_captcha() -> None:
    session = BrowserSession()
    session.page = _FakePage(DEEP_CAPTCHA_HTML, [])
    solver = AutoCaptchaSolver(_FakeCaptchaSolver())
    solved = session.solve_captchas_auto(
        solver,
        page_url="https://example.com/login",
        max_challenges=2,
    )
    assert len(solved) == 2
    assert all(answer for _, answer in solved)
    assert len(session.page.evaluated) == 2
    script, args = session.page.evaluated[0]
    assert "document.querySelector" in script
    assert args[1]


def test_browser_action_pacing() -> None:
    session = BrowserSession(action_interval=0.05, action_jitter=0.0)
    session.page = _FakePage(DEEP_PAGE_HTML, [])
    start = time.monotonic()
    session.goto("https://example.com")
    session.goto("https://example.com")
    assert time.monotonic() - start >= 0.04


def test_analyze_captchas() -> None:
    analysis = analyze_page(
        DEEP_CAPTCHA_HTML,
        base_url="https://example.com/login",
    )
    kinds = {challenge.kind for challenge in analysis.captchas}
    assert {"recaptcha_v2", "hcaptcha", "turnstile", "geetest", "image"}.issubset(kinds)


def test_scrape_guard_policies() -> None:
    policy = RetryPolicy(max_retries=2, base_delay=0.001, max_delay=0.01)
    assert policy.should_retry(429, 0)
    assert not policy.should_retry(429, 2)
    assert not policy.should_retry(404, 0)

    throttle = AdaptiveThrottle(base_delay=0.1, max_delay=0.4, factor=2.0)
    assert throttle.delay == 0.1
    throttle.on_block(429)
    assert throttle.delay == 0.2
    throttle.on_block(403)
    assert throttle.delay == 0.4
    throttle.on_success()
    assert throttle.delay == 0.2

    robots = RobotsPolicy(user_agent="test")
    robots.load_text("User-agent: test\nDisallow: /private\nCrawl-delay: 0.1\n")
    assert robots.can_fetch("https://example.com/public")
    assert not robots.can_fetch("https://example.com/private")
    assert robots.crawl_delay() == 0.1


def test_rate_limiter_waits() -> None:
    limiter = RateLimiter(min_interval=0.05, jitter=0.0)
    start = time.monotonic()
    limiter.wait()
    limiter.wait()
    assert time.monotonic() - start >= 0.04


def test_media_session_retry() -> None:
    _RetryOnceHandler.attempts = 0
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RetryOnceHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        session = MediaSession(
            max_retries=2,
            backoff_base=0.01,
            backoff_max=0.05,
        )
        body, _ = session.get_bytes(f"{base}/x")
        assert body == b"ok"
        assert _RetryOnceHandler.attempts == 2
    finally:
        server.shutdown()
        server.server_close()


def test_pipeline_session_guard_options() -> None:
    session = MediaPipelineService._build_session(
        {
            "headers": {"X-Test": "1"},
            "min_interval": 0.1,
            "jitter": 0.0,
            "max_retries": 3,
            "robots_text": "User-agent: *\nDisallow: /private\n",
            "adaptive_throttle": True,
        }
    )
    assert session.retry_policy is not None
    assert session.retry_policy.max_retries == 3
    assert session.pacer.rate_limiter is not None
    assert session.pacer.rate_limiter.min_interval == 0.1
    assert session.pacer.robots is not None
    assert session.pacer.robots.loaded
    assert session.adaptive_throttle is not None


def test_fingerprint_options() -> None:
    fingerprint = FingerprintOptions()
    kwargs = fingerprint.to_context_kwargs()
    assert kwargs["color_scheme"] == "light"
    assert kwargs["extra_http_headers"]["Accept-Language"].startswith("zh-CN")
    script = fingerprint.init_script()
    assert "hardwareConcurrency" in script
    assert "deviceMemory" in script
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fingerprint.json"
        fingerprint.save(path)
        loaded = FingerprintOptions.load(path)
        assert loaded.to_dict() == fingerprint.to_dict()


def test_fingerprint_generate_stable() -> None:
    first = FingerprintOptions.generate(seed=42)
    second = FingerprintOptions.generate(seed=42)
    assert first.to_dict() == second.to_dict()
    assert first.viewport is not None and first.viewport["width"] >= 1000


def test_page_analyzer_cli() -> None:
    base, server = _start_server({"/deep.html": DEEP_PAGE_HTML.encode("utf-8")})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "analysis.json"
            code = analyze_page_main(["--url", f"{base}/deep.html", "--output", str(out)])
            assert code == 0
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data["metadata"]["title"] == "Episode 12"
            assert len(data["api_endpoints"]) >= 3
    finally:
        server.shutdown()


def test_chunked_download() -> None:
    payload = bytes(range(256)) * 4
    base, server = _start_server({"/video.bin": payload})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "video.bin"
            session = MediaSession()
            result = download_file(
                f"{base}/video.bin",
                dest,
                session=session,
                chunk_size=37,
                concurrency=3,
            )
            assert result.path.read_bytes() == payload
            assert result.total_size == len(payload)
    finally:
        server.shutdown()


def test_download_without_content_length() -> None:
    payload = b"stream-without-length"
    base, server = _start_server({"/video.bin": payload}, _NoLengthHandler)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "video.bin"
            result = download_file(
                f"{base}/video.bin",
                dest,
                session=MediaSession(),
                concurrency=3,
            )
            assert result.path.read_bytes() == payload
            assert result.resumed is False
            assert result.total_size == len(payload)
    finally:
        server.shutdown()


def test_hls_download() -> None:
    seg1 = b"segment-one"
    seg2 = b"segment-two"
    playlist = (
        "#EXTM3U\n"
        "#EXT-X-TARGETDURATION:6\n"
        "#EXTINF:6.0,\n"
        "/seg/1.ts\n"
        "#EXTINF:6.0,\n"
        "/seg/2.ts\n"
    )
    base, server = _start_server(
        {
            "/playlist.m3u8": playlist.encode("utf-8"),
            "/seg/1.ts": seg1,
            "/seg/2.ts": seg2,
        }
    )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            result = download_hls(
                f"{base}/playlist.m3u8",
                tmp,
                ffmpeg_path=None,
                concurrency=2,
            )
            assert result.total_segments == 2
            assert (Path(tmp) / "segments" / "seg_000000.ts").read_bytes() == seg1
            assert (Path(tmp) / "segments" / "seg_000001.ts").read_bytes() == seg2
            assert (Path(tmp) / "concat.txt").exists()
    finally:
        server.shutdown()


def test_hls_quality_selection() -> None:
    master = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1000\n"
        "/low/index.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2000\n"
        "/high/index.m3u8\n"
    )
    low = "#EXTM3U\n#EXTINF:6.0,\n/low/1.ts\n"
    high = "#EXTM3U\n#EXTINF:6.0,\n/high/1.ts\n"
    base, server = _start_server(
        {
            "/master.m3u8": master.encode("utf-8"),
            "/low/index.m3u8": low.encode("utf-8"),
            "/high/index.m3u8": high.encode("utf-8"),
            "/low/1.ts": b"LOW",
            "/high/1.ts": b"HIGH",
        }
    )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            download_hls(
                f"{base}/master.m3u8",
                tmp,
                ffmpeg_path=None,
                quality=0,
            )
            assert (Path(tmp) / "segments" / "seg_000000.ts").read_bytes() == b"LOW"
    finally:
        server.shutdown()


def test_dependencies_status() -> None:
    status = check_status()
    for key in (
        "playwright",
        "pycryptodome",
        "ocr",
        "chromium",
        "ffmpeg",
        "ffprobe",
        "runtime_dir",
        "ready",
    ):
        assert key in status, f"check_status missing {key}"


def test_pipeline_service() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = MediaPipelineService(Path(tmp) / "tasks.sqlite", token="test-token")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(f"{base}/health") as response:
                health = json.loads(response.read().decode("utf-8"))
            assert health["ok"] is True
            try:
                urllib.request.urlopen(f"{base}/deps/progress")
                raise AssertionError("unauthenticated request must fail")
            except urllib.error.HTTPError as exc:
                assert exc.code == 401
            try:
                request = urllib.request.Request(
                    f"{base}/tasks",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(request)
                raise AssertionError("unauthenticated POST must fail")
            except urllib.error.HTTPError as exc:
                assert exc.code == 401

            def auth_request(path: str, data: bytes | None = None) -> urllib.request.Request:
                headers = {"Authorization": "Bearer test-token"}
                if data is not None:
                    headers["Content-Type"] = "application/json"
                return urllib.request.Request(f"{base}{path}", data=data, headers=headers)

            with urllib.request.urlopen(auth_request("/deps/progress")) as response:
                install_progress = json.loads(response.read().decode("utf-8"))
            assert "stage" in install_progress
            assert "percent" in install_progress

            payload = json.dumps(
                {
                    "kind": "download",
                    "payload": {
                        "url": "https://example.com/video.mp4",
                        "dest": "out/video.mp4",
                    },
                    "dedupe_key": "sha256:url",
                    "max_attempts": 5,
                    "resume_token": {"chunk": 1},
                }
            ).encode("utf-8")
            with urllib.request.urlopen(auth_request("/tasks", payload)) as response:
                task = json.loads(response.read().decode("utf-8"))
            assert task["kind"] == "download"
            assert task["max_attempts"] == 5
            assert task["resume_token"] == {"chunk": 1}
            with urllib.request.urlopen(auth_request(f"/tasks/{task['id']}")) as response:
                fetched = json.loads(response.read().decode("utf-8"))
            assert fetched["id"] == task["id"]
            with urllib.request.urlopen(auth_request("/tasks?search=video")) as response:
                search_result = json.loads(response.read().decode("utf-8"))
            assert search_result["total"] >= 1
            with urllib.request.urlopen(auth_request("/tasks?search=missing-xyz")) as response:
                empty_result = json.loads(response.read().decode("utf-8"))
            assert empty_result["total"] == 0
        finally:
            server.shutdown()
            server.server_close()
            service.close()


def test_pipeline_bad_requests() -> None:
    try:
        _read_json(b"[]")
        raise AssertionError("JSON array must be rejected")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as tmp:
        service = MediaPipelineService(Path(tmp) / "tasks.sqlite", token="test-token")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:

            def auth_request(path: str, data: bytes) -> urllib.request.Request:
                headers = {
                    "Authorization": "Bearer test-token",
                    "Content-Type": "application/json",
                }
                return urllib.request.Request(f"{base}{path}", data=data, headers=headers)

            invalid_payloads = [
                {
                    "kind": "download",
                    "payload": {"url": "x", "dest": "y"},
                    "priority": "abc",
                },
                {
                    "kind": "download",
                    "payload": {"url": "x", "dest": "y"},
                    "max_attempts": 0,
                },
                {"kind": "download", "payload": []},
                {
                    "kind": "download",
                    "payload": {"url": "x", "dest": "y"},
                    "resume_token": "bad",
                },
            ]
            for payload in invalid_payloads:
                request = auth_request("/tasks", json.dumps(payload).encode("utf-8"))
                try:
                    urllib.request.urlopen(request)
                    raise AssertionError(f"invalid payload must return 400: {payload}")
                except urllib.error.HTTPError as exc:
                    assert exc.code == 400
        finally:
            server.shutdown()
            server.server_close()
            service.close()


def test_security_detector_classifications() -> None:
    cf_html = (
        "<html><head><title>Just a moment...</title></head><body>"
        "Checking your browser before accessing... "
        '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>'
        "</body></html>"
    )
    report = detect_security_mechanisms(
        503,
        "https://example.com/",
        {"Server": "cloudflare"},
        cf_html,
        html=cf_html,
    )
    assert isinstance(report, SecurityReport)
    assert report.is_blocked
    assert report.primary_kind == "cloudflare_challenge"
    assert "browser" in report.actions
    cf_finding = next(item for item in report.findings if item.kind == "cloudflare_challenge")
    assert cf_finding.details.get("stage") in {
        "js_challenge",
        "managed_non_interactive",
        "turnstile_captcha",
    }

    report = detect_security_mechanisms(
        403,
        "https://example.com/",
        {"Server": "AkamaiGHost"},
        "<html>Access Denied</html>",
    )
    assert report.is_blocked
    assert report.primary_kind == "waf_blocked"
    assert "proxy" in report.actions

    report = detect_security_mechanisms(
        429,
        "https://example.com/",
        {"Retry-After": "5"},
        "Too many requests",
    )
    assert report.is_blocked
    assert report.primary_kind == "rate_limited"
    assert "retry" in report.actions

    report = detect_security_mechanisms(
        401,
        "https://example.com/private",
        {},
        "Please sign in to continue",
    )
    assert report.primary_kind == "login_required"
    assert "login" in report.actions

    captcha_html = '<div class="g-recaptcha" data-sitekey="test-key"></div>'
    report = detect_security_mechanisms(
        200,
        "https://example.com/",
        {},
        captcha_html,
        html=captcha_html,
    )
    assert report.is_blocked
    assert any(item.kind == "captcha_required" for item in report.findings)
    assert "captcha" in report.actions

    report = detect_security_mechanisms(
        200,
        "https://example.com/",
        {},
        "<div>Accept all cookies</div>",
    )
    assert any(item.kind == "cookie_consent_wall" for item in report.findings)
    assert "browser" in report.actions

    report = detect_security_mechanisms(
        200,
        "https://example.com/app",
        {},
        '<div id="root"></div>',
    )
    assert any(item.kind == "dynamic_page" for item in report.findings)
    assert not report.is_blocked


def test_cloudflare_state_extraction() -> None:
    js_html = (
        "<html><head><title>Just a moment...</title></head><body>"
        "Checking your browser before accessing... "
        '<iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/g/orchestrate/jsch/v1?ray=abc"></iframe>'
        "</body></html>"
    )
    state = extract_cloudflare_state(js_html, "https://example.com/")
    assert state.present
    assert state.stage in {"js_challenge", "managed_non_interactive"}
    assert state.frame_url and "challenges.cloudflare.com" in state.frame_url

    turnstile_html = (
        '<html><body><div class="cf-turnstile" data-sitekey="0x4AAAAAAAAAAA"></div>'
        '<iframe src="https://challenges.cloudflare.com/turnstile/v0/g/demo?k=0x4AAAAAAAAAAA"></iframe>'
        "</body></html>"
    )
    state = extract_cloudflare_state(turnstile_html, "https://example.com/")
    assert state.sitekey == "0x4AAAAAAAAAAA"
    assert state.stage == "turnstile_captcha"

    state = extract_cloudflare_state(
        "<html><body>ok</body></html>",
        "https://example.com/",
        cookies=[{"name": "cf_clearance", "value": "x", "domain": "example.com", "path": "/"}],
    )
    assert state.clearance_cookie == "x"
    assert state.stage == "passed"
    assert not state.present

    blocked_html = (
        "<html><head><title>Attention Required! | Cloudflare</title></head>"
        "<body>error code 1020</body></html>"
    )
    state = extract_cloudflare_state(blocked_html, "https://example.com/")
    assert state.stage == "blocked"


def test_cloudflare_challenge_handler() -> None:
    challenge_html = (
        "<html><body>"
        '<iframe src="https://challenges.cloudflare.com/turnstile/v0/g/demo"></iframe>'
        "</body></html>"
    )
    page = _FakeCloudflarePage(challenge_html)
    context = _FakeCloudflareContext(clearance=False)
    handler = CloudflareChallengeHandler(
        CloudflareChallengeConfig(
            max_attempts=2,
            wait_timeout=200,
            clearance_timeout=200,
            poll_interval=0.01,
            auto_click=False,
            solve_turnstile=False,
            reload_before_retry=False,
            rotate_proxy_on_fail=True,
        )
    )
    result = handler.run(page, context, "https://example.com/")
    assert isinstance(result, CloudflareChallengeResult)
    assert not result.passed
    assert result.needs_new_session
    assert result.attempts == 2

    context.clearance = True
    result = handler.run(page, context, "https://example.com/")
    assert result.passed
    assert result.strategy == "clearance"
    assert result.cf_clearance == "abc123"
    assert result.clearance_cookie is not None


def test_deep_crawler_links_sitemap_robots() -> None:
    base, server = _start_server(
        {
            "/index.html": (
                b"<html><body>"
                b'<a href="/a.html">A</a>'
                b'<a href="/b.html">B</a>'
                b'<a href="https://external.example/x">X</a>'
                b'<a href="/secret.html">secret</a>'
                b"</body></html>"
            ),
            "/a.html": b'<html><body><a href="/c.html">C</a></body></html>',
            "/b.html": b'<html><body><a href="/index.html">home</a></body></html>',
            "/c.html": b"<html><body>leaf</body></html>",
            "/d.html": b"<html><body>sitemap leaf</body></html>",
            "/secret.html": b"<html><body>secret</body></html>",
            "/robots.txt": b"User-agent: *\nDisallow: /secret\nSitemap: /sitemap.xml\n",
        }
    )
    _RangeHandler.payloads["/sitemap.xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{base}/d.html</loc></url></urlset>"
    ).encode()
    try:
        result = DeepCrawler(
            CrawlConfig(
                seeds=[f"{base}/index.html"],
                max_depth=2,
                max_pages=20,
                same_host=True,
                sitemap=True,
                respect_robots=True,
                min_interval=0.0,
                max_retries=0,
            )
        ).crawl()
        urls = {page.url for page in result.pages}
        assert any(url.endswith("/a.html") for url in urls)
        assert any(url.endswith("/c.html") for url in urls)
        assert any(url.endswith("/d.html") for url in urls)
        assert not any(url.startswith("https://external.example") for url in urls)
        secret = next(
            (page for page in result.pages if page.url.endswith("/secret.html")),
            None,
        )
        assert secret is not None and secret.skipped_reason == "robots"
        assert any(url.endswith("/d.html") for url in result.sitemap_urls)
    finally:
        server.shutdown()


def test_deep_crawler_blocked_skip() -> None:
    base, server = _start_server(
        {
            "/index.html": (
                b'<html><body><a href="/blocked.html">blocked</a>'
                b'<a href="/ok.html">ok</a></body></html>'
            ),
            "/ok.html": b"<html><body>ok</body></html>",
        },
        _BlockingHandler,
    )
    _BlockingHandler.blocked_paths = {"/blocked.html"}
    try:
        result = DeepCrawler(
            CrawlConfig(
                seeds=[f"{base}/index.html"],
                max_depth=1,
                max_pages=10,
                min_interval=0.0,
                max_retries=0,
            )
        ).crawl()
        blocked = next(
            (page for page in result.pages if page.url.endswith("/blocked.html")),
            None,
        )
        assert blocked is not None and blocked.blocked
        assert blocked.security is not None and blocked.security.is_blocked
        ok = next((page for page in result.pages if page.url.endswith("/ok.html")), None)
        assert ok is not None and not ok.blocked
    finally:
        server.shutdown()
        _BlockingHandler.blocked_paths = set()


def test_media_session_error_metadata() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _BlockingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    _BlockingHandler.blocked_paths = {"/blocked"}
    try:
        body, status, headers = MediaSession(max_retries=0).get_bytes_with_meta(f"{base}/blocked")
        assert status == 403
        assert b"Access Denied" in body
        assert headers.get("Content-Type", "").startswith("text/html")
        data, status, _ = MediaSession(max_retries=0).request_json_with_meta(
            "GET",
            f"{base}/blocked",
        )
        assert status == 403
        assert "Access Denied" in (data or "")
    finally:
        server.shutdown()
        _BlockingHandler.blocked_paths = set()


def test_api_client_blocked_metadata() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _BlockingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    _BlockingHandler.blocked_paths = {"/api"}
    try:
        client = ApiClient(min_interval=0.0, max_retries=0)
        results = client.fetch_all([ApiSpec(method="GET", url=f"{base}/api")])
        result = results[0]
        assert result.status == 403
        assert result.error == "blocked by waf_blocked"
        assert result.security is not None and result.security["blocked"] is True
    finally:
        server.shutdown()
        _BlockingHandler.blocked_paths = set()


def test_web_data_pipeline_deep_crawl() -> None:
    base, server = _start_server(
        {
            "/index.html": (
                b'<html><body><a href="/list.html">list</a>'
                b'<a href="/blocked.html">blocked</a></body></html>'
            ),
            "/list.html": (
                b'<html><body><script>fetch("/api/items?page=1");</script></body></html>'
            ),
            "/sitemap.html": b"<html><body>sitemap</body></html>",
            "/robots.txt": b"User-agent: *\nDisallow:\n",
        },
        _BlockingHandler,
    )
    _BlockingHandler.payloads["/sitemap.xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{base}/sitemap.html</loc></url></urlset>"
    ).encode()
    _BlockingHandler.blocked_paths = {"/blocked.html"}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.json"
            with contextlib.redirect_stderr(io.StringIO()):
                summary = WebDataPipeline(
                    {
                        "pages": [f"{base}/index.html"],
                        "crawl": {
                            "enabled": True,
                            "max_depth": 2,
                            "max_pages": 10,
                            "same_host": True,
                            "sitemap": True,
                            "respect_robots": True,
                            "skip_blocked": True,
                        },
                        "security": {"enabled": True, "escalate_to_browser": False},
                        "api": {
                            "min_interval": 0.0,
                            "max_retries": 0,
                            "include_captured": False,
                            "include_static": True,
                            "max_specs": 50,
                        },
                        "processing": {"steps": [{"op": "select", "params": {"fields": ["id"]}}]},
                        "output": str(output),
                    }
                ).run()
            assert summary["crawl_pages"] >= 3
            assert summary["security_findings"] >= 1
            assert output.exists()
    finally:
        server.shutdown()
        _BlockingHandler.blocked_paths = set()


def test_crawl_task() -> None:
    html = (
        "<html><body>"
        '<video src="/v/1.mp4"></video>'
        '<source src="/hls/master.m3u8">'
        "</body></html>"
    )
    base, server = _start_server({"/page.html": html.encode("utf-8")})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            service = MediaPipelineService(Path(tmp) / "tasks.sqlite")
            task = service.queue.enqueue(
                "crawl",
                {"url": f"{base}/page.html", "dest_dir": tmp, "download": True},
            )
            summary = service._run_task(task)
            assert summary is not None
            kinds = {item.kind for item in service.queue.list_tasks()}
            assert {"download", "hls"}.issubset(kinds)
            service.close()
    finally:
        server.shutdown()


def test_crawl_deep() -> None:
    base, server = _start_server({"/deep.html": DEEP_PAGE_HTML.encode("utf-8")})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            service = MediaPipelineService(Path(tmp) / "tasks.sqlite")
            task = service.queue.enqueue(
                "crawl",
                {
                    "url": f"{base}/deep.html",
                    "download": False,
                    "deep": True,
                },
            )
            summary_text = service._run_task(task)
            assert summary_text is not None
            summary = json.loads(summary_text)
            page_data = summary["page_data"]
            assert page_data["metadata"]["title"] == "Episode 12"
            assert any(
                endpoint["url"].endswith("/api/detail/12")
                for endpoint in page_data["api_endpoints"]
            )
            assert page_data["json_media"]["hls"] == 1
            service.close()
    finally:
        server.shutdown()


def test_analyze_task() -> None:
    base, server = _start_server({"/deep.html": DEEP_PAGE_HTML.encode("utf-8")})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            service = MediaPipelineService(Path(tmp) / "tasks.sqlite")
            task = service.queue.enqueue("analyze", {"url": f"{base}/deep.html"})
            result_text = service._run_task(task)
            assert result_text is not None
            result = json.loads(result_text)
            assert result["metadata"]["title"] == "Episode 12"
            assert result["embedded_json"][0]["kind"] == "json-ld"
            assert len(result["api_endpoints"]) >= 3
            service.close()
    finally:
        server.shutdown()


def test_api_client_specs_and_fetch() -> None:
    from api_client import _SelfTestHandler as ApiSelfTestHandler

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ApiSelfTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        capture = {
            "network": [
                {
                    "method": "POST",
                    "url": f"{base}/api/items?page=2",
                    "resource_type": "fetch",
                    "request_headers": {"X-Token": "abc"},
                    "post_data": '{"page":2}',
                    "request_content_type": "application/json",
                }
            ],
            "analysis": {
                "api_endpoints": [
                    {"method": "GET", "url": f"{base}/api/config", "source": "script"}
                ],
                "pagination": {},
            },
        }
        specs = build_api_specs(capture)
        assert len(specs) == 2
        post_spec = next(spec for spec in specs if spec.method == "POST")
        assert post_spec.params == {"page": "2"}
        assert post_spec.body == {"page": 2}
        assert post_spec.headers == {"X-Token": "abc"}
        client = ApiClient(min_interval=0.0, max_retries=0)
        results = client.fetch_all(specs)
        assert all(result.error is None for result in results), [result.error for result in results]
        assert results[0].data["items"][0]["id"] == 1
        assert results[1].data["enabled"] is True
    finally:
        server.shutdown()


def test_api_client_pagination() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _PaginationHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        spec = ApiSpec(
            method="GET",
            url=f"{base}/items",
            pagination={
                "type": "page",
                "param": "page",
                "start": 1,
                "max_pages": 10,
                "items_path": "items",
                "total_path": "total",
                "has_more_path": "hasMore",
            },
        )
        client = ApiClient(min_interval=0.0, max_retries=0)
        data = client.fetch_spec(spec)
        assert [item["id"] for item in data] == [1, 2, 3], data
        results = client.fetch_all([spec])
        assert results[0].pages == 3
    finally:
        server.shutdown()


def test_api_client_cookies() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CookieEchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        client = ApiClient(
            cookies=[{"name": "sid", "value": "abc", "domain": "127.0.0.1", "path": "/"}],
            min_interval=0.0,
            max_retries=0,
        )
        data = client.fetch_spec(ApiSpec(method="GET", url=f"{base}/echo"))
        assert "sid=abc" in data["cookie"], data
    finally:
        server.shutdown()


def test_api_client_result_metadata() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CookieEchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        client = ApiClient(min_interval=0.0, max_retries=0)
        results = client.fetch_all([ApiSpec(method="GET", url=f"{base}/echo")])
        assert results[0].error is None, results[0].error
        assert results[0].status == 200
        assert "application/json" in (results[0].headers or {}).get("Content-Type", "")
        assert results[0].duration_ms is not None and results[0].duration_ms >= 0
    finally:
        server.shutdown()


def test_api_analyzer_manifest() -> None:
    capture = {
        "url": "https://example.com/list",
        "network": [
            {
                "method": "GET",
                "url": "https://example.com/api/items?page=1&page_size=20",
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
    assert manifest.auth_headers.get("authorization") == "<redacted>"
    assert manifest.pagination is not None
    assert manifest.pagination["type"] == "page"
    assert "items" in manifest.data_paths
    assert any(item["api_like"] for item in manifest.endpoints)
    assert manifest.summary["endpoints"] >= 2


def test_data_processor_pipeline() -> None:
    records = [
        {"id": 1, "name": "Alpha", "price": 10, "meta": {"ok": True}},
        {"id": 2, "name": "Beta", "price": 20, "meta": {"ok": False}},
        {"id": 3, "name": "Alpha", "price": 30, "meta": {"ok": True}},
    ]
    config = {
        "steps": [
            {
                "op": "filter",
                "params": {
                    "conditions": [
                        {"field": "meta.ok", "op": "eq", "value": True},
                        {"field": "price", "op": "gte", "value": 10},
                    ]
                },
            },
            {"op": "select", "params": {"fields": ["name", "price"]}},
            {
                "op": "aggregate",
                "params": {
                    "by": ["name"],
                    "ops": [{"field": "price", "method": "sum", "output": "total"}],
                },
            },
            {"op": "sort", "params": {"keys": [{"field": "total", "desc": True}]}},
        ]
    }
    processed = process_records(records, config)
    assert processed == [{"name": "Alpha", "total": 40}], processed
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "in.json"
        source.write_text(json.dumps(records), encoding="utf-8")
        out = Path(tmp) / "out.jsonl"
        save_records(records[:2], out)
        loaded = load_records(out)
        assert len(loaded) == 2


def test_data_processor_extended_ops() -> None:
    records = [
        {"name": " Alpha ", "price": "10", "tags": None},
        {"name": "beta", "price": "20", "tags": "x"},
    ]
    config = {
        "steps": [
            {"op": "default", "params": {"mapping": {"tags": "none"}}},
            {"op": "convert", "params": {"fields": [{"field": "price", "type": "int"}]}},
            {
                "op": "map",
                "params": {
                    "fields": [
                        {"output": "slug", "field": "name", "transform": "strip"},
                        {"output": "label", "template": "Item-{name}-{price}"},
                    ]
                },
            },
            {
                "op": "replace",
                "params": {"fields": [{"field": "slug", "pattern": " ", "replacement": "_"}]},
            },
            {"op": "drop", "params": {"fields": ["tags"]}},
        ]
    }
    processed = process_records(records, config)
    assert processed[0]["slug"] == "Alpha", processed
    assert processed[0]["price"] == 10, processed
    assert processed[0]["label"] == "Item- Alpha -10", processed
    assert "tags" not in processed[0], processed


def test_data_processor_join() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        other = Path(tmp) / "other.json"
        other.write_text(
            json.dumps(
                [
                    {"id": 1, "city": "Beijing"},
                    {"id": 2, "city": "Shanghai"},
                ]
            ),
            encoding="utf-8",
        )
        records = [{"id": 1, "name": "A"}, {"id": 3, "name": "C"}]
        config = {
            "steps": [
                {
                    "op": "join",
                    "params": {
                        "path": str(other),
                        "on": ["id"],
                        "type": "left",
                        "prefix": "other_",
                        "fields": ["city"],
                    },
                }
            ]
        }
        processed = process_records(records, config)
        assert processed == [
            {"id": 1, "name": "A", "other_city": "Beijing"},
            {"id": 3, "name": "C"},
        ], processed


def test_web_data_pipeline_self_test() -> None:
    from web_data_pipeline import main as web_data_main

    assert web_data_main(["--self-test"]) == 0


def test_sidecar_webdata_task() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), WebSelfTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            service = MediaPipelineService(Path(tmp) / "tasks.sqlite")
            out = Path(tmp) / "result.json"
            task = service.queue.enqueue(
                "webdata",
                {
                    "config": {
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
                                    "op": "filter",
                                    "params": {
                                        "conditions": [{"field": "price", "op": "gte", "value": 10}]
                                    },
                                },
                                {"op": "select", "params": {"fields": ["id", "name"]}},
                            ]
                        },
                        "output": str(out),
                    },
                    "output": str(out),
                },
            )
            summary_text = service._run_task(task)
            assert summary_text is not None
            summary = json.loads(summary_text)
            assert summary["api_specs"] == 2, summary
            assert summary["raw_records"] == 3, summary
            assert summary["processed_records"] == 2, summary
            records = load_records(out)
            assert records == [{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}], records
            task_after = service.queue.get(task.id)
            assert task_after is not None and task_after.progress >= 1.0
            events = service.task_events(task.id)
            assert events and events[-1]["stage"] == "done", events
            service.close()
    finally:
        server.shutdown()


def test_captcha_ocr_fallback() -> None:
    solver = AutoCaptchaSolver(_FakeCaptchaSolver(), ocr_solver=_FailingOcrSolver())
    challenge = CaptchaChallenge(kind="image", image_url=None)
    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / "captcha.png"
        image_path.write_bytes(b"fake-image")
        assert solver.solve_challenge(challenge, image_path=image_path) == "ABCD"
    assert isinstance(OcrCaptchaSolver().available, bool)


def test_task_queue_run_after() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        queue = TaskQueue(Path(tmp) / "tasks.sqlite")
        run_at = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
        queue.enqueue("download", {"url": "x"}, run_after=run_at)
        assert queue.claim_next() is None, "future run_after task must not be claimable"
        queue.close()


def test_proxy_pool_rotation_and_cooldown() -> None:
    pool = ProxyPool(
        ["http://p1:8080", "http://p2:8080"],
        max_failures=1,
        cooldown_seconds=60,
    )
    first = pool.get_proxy()
    second = pool.get_proxy()
    assert first != second
    assert pool.get_proxy() == first, "round robin must cycle after two calls"
    pool.report_failure(first)
    assert pool.get_proxy() != first, "failed proxy must enter cooldown"
    pool.report_success(second)
    with tempfile.TemporaryDirectory() as tmp:
        store = ProxyPoolStore(Path(tmp) / "pools.json")
        store.upsert(
            "main",
            {"proxies": ["http://p3:8080"], "strategy": "round_robin"},
        )
        assert store.get("main") is not None
        status = store.get_status("main")
        assert status["proxies"][0]["proxy"] == "http://p3:8080"
        assert store.list()
        assert store.remove("main")
        store.close()


def test_account_manager_rotation_and_cooldown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        manager = AccountManager(Path(tmp) / "accounts.json")
        manager.upsert({"name": "a", "cooldown_seconds": 60})
        manager.upsert({"name": "b", "cooldown_seconds": 60})
        first = manager.acquire()
        second = manager.acquire()
        assert first is not None and second is not None
        assert first["name"] != second["name"]
        assert manager.acquire() is None, "all accounts are leased"
        manager.release(first["name"], success=True)
        assert manager.acquire(second["name"]) is None, "leased account stays leased"
        assert manager.acquire(first["name"]) is not None
        manager.release(first["name"], success=False, error="blocked")
        assert manager.acquire(first["name"]) is None, "failed account must cool down"
        manager.close()
        reloaded = AccountManager(Path(tmp) / "accounts.json")
        assert len(reloaded.list()) == 2
        reloaded.close()


def test_scheduler_next_run_and_enqueue_due() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        queue = TaskQueue(Path(tmp) / "tasks.sqlite")
        scheduler = TaskScheduler(queue)
        record = scheduler.add(
            "webdata",
            {"config": {"pages": []}},
            {"type": "interval", "seconds": 60},
            start_after_seconds=0,
        )
        assert record.next_run_at is not None
        due_now = datetime.fromisoformat(record.next_run_at) + timedelta(seconds=1)
        assert scheduler.enqueue_due(now=due_now) == 1
        assert queue.count() == 1
        updated = queue.get_schedule(record.id)
        assert updated is not None and updated.last_run_at is not None
        assert datetime.fromisoformat(updated.next_run_at) > datetime.fromisoformat(
            record.next_run_at
        )
        daily = next_run_after(
            {"type": "daily", "time": "10:00"},
            now=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
        )
        assert daily.hour == 10 and daily.day == 8
        cron = next_run_after(
            {"type": "cron", "minute": "0", "hour": "*"},
            now=datetime(2026, 8, 8, 10, 30, tzinfo=timezone.utc),
        )
        assert cron.hour == 11 and cron.minute == 0
        queue.close()


def test_notifier_webhook() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _WebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        _WebhookHandler.received = {}
        notifier = Notifier({"webhook": {"url": f"{base}/hook"}})
        result = notifier.send(
            "Task 1 succeeded",
            "done",
            task={"id": 1, "status": "succeeded"},
        )
        assert result.get("webhook") is True
        assert _WebhookHandler.received["title"] == "Task 1 succeeded"
        result2 = notifier.notify_task(
            {"id": 2, "kind": "webdata", "status": "failed", "error": "boom"}
        )
        assert result2.get("webhook") is True
        assert _WebhookHandler.received["task"]["error"] == "boom"
    finally:
        server.shutdown()
        server.server_close()


def test_sidecar_advanced_endpoints() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = MediaPipelineService(Path(tmp) / "tasks.sqlite", token="test-token")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def request(
            path: str,
            data: dict | None = None,
            method: str = "GET",
        ) -> dict:
            headers = {"Authorization": "Bearer test-token"}
            payload = None
            if data is not None:
                payload = json.dumps(data).encode("utf-8")
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(
                f"{base}{path}",
                data=payload,
                headers=headers,
                method=method,
            )
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode("utf-8"))

        try:
            pool = request(
                "/proxy-pools",
                {"name": "main", "config": {"proxies": ["http://p1:8080"]}},
                method="POST",
            )
            assert pool["proxies"][0]["proxy"] == "http://p1:8080"
            account = request(
                "/accounts",
                {"name": "acc", "proxy": "http://p2:8080"},
                method="POST",
            )
            assert account["name"] == "acc"
            acquired = request("/accounts/acc/acquire", {}, method="POST")
            assert acquired["in_use"] is True
            request("/accounts/acc/release", {"success": True}, method="POST")
            schedule = request(
                "/schedules",
                {
                    "kind": "webdata",
                    "payload": {"config": {"pages": []}},
                    "schedule": {"type": "interval", "seconds": 60},
                    "start_after_seconds": 60,
                },
                method="POST",
            )
            assert schedule["id"] > 0
            assert len(request("/schedules")["items"]) == 1
            assert "channels" in request("/notifications/status")
            assert request("/proxy-pools/main")["name"] == "main"
            assert request("/accounts/acc", method="DELETE")["ok"] is True
            assert request(f"/schedules/{schedule['id']}", method="DELETE")["ok"] is True
            assert request("/proxy-pools/main", method="DELETE")["ok"] is True
        finally:
            server.shutdown()
            server.server_close()
            service.close()


def run() -> int:
    tests = [
        test_task_queue,
        test_task_queue_delayed_retry,
        test_media_parser,
        test_deep_page_parser,
        test_browser_network_capture,
        test_safe_output_name,
        test_browser_action_pacing,
        test_filename_from_url,
        test_zip_member_safety,
        test_manual_captcha,
        test_detect_captchas,
        test_auto_captcha_solver,
        test_browser_auto_captcha,
        test_analyze_captchas,
        test_scrape_guard_policies,
        test_rate_limiter_waits,
        test_media_session_retry,
        test_pipeline_session_guard_options,
        test_fingerprint_options,
        test_fingerprint_generate_stable,
        test_page_analyzer_cli,
        test_chunked_download,
        test_download_without_content_length,
        test_hls_download,
        test_hls_quality_selection,
        test_dependencies_status,
        test_pipeline_service,
        test_pipeline_bad_requests,
        test_crawl_task,
        test_crawl_deep,
        test_analyze_task,
        test_security_detector_classifications,
        test_cloudflare_state_extraction,
        test_cloudflare_challenge_handler,
        test_deep_crawler_links_sitemap_robots,
        test_deep_crawler_blocked_skip,
        test_media_session_error_metadata,
        test_api_client_blocked_metadata,
        test_web_data_pipeline_deep_crawl,
        test_api_client_specs_and_fetch,
        test_api_client_pagination,
        test_api_client_cookies,
        test_api_client_result_metadata,
        test_api_analyzer_manifest,
        test_data_processor_pipeline,
        test_data_processor_extended_ops,
        test_data_processor_join,
        test_web_data_pipeline_self_test,
        test_sidecar_webdata_task,
        test_captcha_ocr_fallback,
        test_task_queue_run_after,
        test_proxy_pool_rotation_and_cooldown,
        test_account_manager_rotation_and_cooldown,
        test_scheduler_next_run_and_enqueue_due,
        test_notifier_webhook,
        test_sidecar_advanced_endpoints,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  [OK]   {test.__name__}")
        except Exception as exc:
            failures += 1
            print(f"  [FAIL] {test.__name__}: {exc}")
    print(f"  Media pipeline: {len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run())
