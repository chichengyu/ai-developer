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
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from account_manager import AccountManager  # noqa: E402
from api_analyzer import analyze_captures  # noqa: E402
from api_client import ApiClient, ApiSpec, build_api_specs  # noqa: E402
from browser_session import BrowserSession, FingerprintOptions, NetworkCaptureOptions  # noqa: E402
from builtin_dependency_manager import (  # noqa: E402
    BuiltinDependencyManager,
    DependencyError,
    DependencySpec,
)
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
from ensure_all_dependencies import (  # noqa: E402
    ensure as ensure_all_dependencies,
)
from ensure_all_dependencies import (  # noqa: E402
    status as ensure_all_status,
)
from ensure_web_fetch_dependencies import (  # noqa: E402
    DependencyInstallError,
    missing_packages,
)
from ensure_web_fetch_dependencies import (  # noqa: E402
    check_status as ensure_status,
)
from ensure_web_fetch_dependencies import (  # noqa: E402
    ensure as ensure_dependencies,
)
from ffmpeg_transcoder import (  # noqa: E402
    EXTENSION_PROFILE,
    TRANSCODE_PROFILES,
    MediaInfo,
    TranscodeOptions,
    build_ffmpeg_args,
    parse_encoder_list,
    select_hardware_encoder,
    transcode_file,
)
from ffmpeg_transcoder import (  # noqa: E402
    main as transcode_main,
)
from file_converter import (  # noqa: E402
    BatchConvertProgress,
    ConversionUnavailable,
    ConvertResult,
    convert_file,
    convert_many,
    extract_archive,
)
from flaresolverr import FlaresolverrClient  # noqa: E402
from hls_downloader import download_hls  # noqa: E402
from media_dependencies import (  # noqa: E402
    _zip_member_is_safe,
    check_status,
    install_dependencies,
)
from media_downloader import (  # noqa: E402
    BatchDownloadResult,
    DownloadHashError,
    SpeedLimiter,
    SpeedTracker,
    _build_chunk_map,
    _load_chunk_map,
    _tune_concurrency,
    download_batch,
    download_file,
    safe_output_name,
)
from media_formats import (  # noqa: E402
    FORMAT_CATALOG,
    catalog_payload,
    engine_targets,
    formats_by_category,
    lookup_format,
)
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
from smart_fetch import (  # noqa: E402
    BackendResponse,
    SmartFetchSession,
    available_backends,
    backend_status,
    create_fetch_session,
)
from stealth_browser import (  # noqa: E402
    StealthBrowserError,
    available_stealth_engines,
    solve_cloudflare_with_stealth_browser,
)
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
        self.send_header("ETag", f'"v1-{len(data)}"')
        self.send_header("Last-Modified", "Wed, 01 Jan 2025 00:00:00 GMT")
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


class _RangeFallbackHandler(http.server.BaseHTTPRequestHandler):
    """HEAD hides length/ranges; GET Range still reports Content-Range."""

    payloads: dict[str, bytes] = {}

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()

    def do_GET(self) -> None:
        data = self.payloads.get(self.path, b"")
        range_header = self.headers.get("Range")
        if range_header:
            match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if match:
                start = int(match.group(1))
                end = min(int(match.group(2)) if match.group(2) else len(data) - 1, len(data) - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(max(0, end - start + 1)))
                self.end_headers()
                self.wfile.write(data[start : end + 1])
                return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
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


class _FlaresolverrHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        command = payload.get("cmd")
        if command == "request.get":
            body = {
                "status": "ok",
                "message": "",
                "solution": {
                    "url": payload.get("url", "https://example.com/"),
                    "status": 200,
                    "headers": {"content-type": "text/html"},
                    "response": "<html><body>solved</body></html>",
                    "cookies": [
                        {
                            "name": "cf_clearance",
                            "value": "abc123",
                            "domain": ".example.com",
                            "path": "/",
                            "secure": True,
                            "sameSite": "None",
                        }
                    ],
                    "userAgent": "Mozilla/5.0 solved",
                },
            }
        elif command == "sessions.list":
            body = {"status": "ok", "sessions": ["s1"]}
        else:
            body = {"status": "error", "message": "unsupported"}
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

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


def test_task_queue_progress_meta() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "tasks.sqlite"
        queue = TaskQueue(db)
        task = queue.enqueue("download", {"url": "x", "dest": "y"})
        meta = {
            "downloaded": 4096,
            "total": 102400,
            "percent": 0.04,
            "speed": 8192.0,
            "eta_s": 12.0,
        }
        queue.update_progress(task.id, 0.04, stage="download", progress_meta=meta)
        record = queue.get(task.id)
        assert record is not None
        assert record.progress_meta == meta
        queue.close()

        reopened = TaskQueue(db)
        persisted = reopened.get(task.id)
        assert persisted is not None and persisted.progress_meta == meta
        reopened.close()


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


def test_download_progress_total_size_and_meta() -> None:
    payload = bytes(range(128)) * 32
    base, server = _start_server({"/video.bin": payload})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "video.bin"
            events = []
            result = download_file(
                f"{base}/video.bin",
                dest,
                session=MediaSession(),
                chunk_size=37,
                concurrency=3,
                progress=events.append,
            )
            assert result.path.read_bytes() == payload
            assert result.chunks_total == result.chunks_downloaded
            assert result.elapsed_s >= 0.0
            assert result.average_speed >= 0.0
            assert events, "download must emit progress snapshots"
            probe = events[0]
            assert probe.stage == "probe"
            assert probe.total == len(payload)
            assert probe.downloaded == 0
            assert any(event.phase == "merge" for event in events)
            done = events[-1]
            assert done.stage == "done"
            assert done.phase == "done"
            assert done.percent == 1.0
            assert done.downloaded == len(payload)
            assert done.total == len(payload)
            assert done.merge_total == len(payload)
            assert done.chunks_total == result.chunks_total
    finally:
        server.shutdown()


def test_download_auto_chunk_sizing() -> None:
    payload = bytes(range(256)) * (4 * 1024 * 1024 // 256)
    base, server = _start_server({"/video.bin": payload})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "video.bin"
            result = download_file(
                f"{base}/video.bin",
                dest,
                session=MediaSession(),
                concurrency=4,
            )
            assert result.path.read_bytes() == payload
            assert result.chunks_total == 16
    finally:
        server.shutdown()


def test_speed_tracker_and_tuning() -> None:
    tracker = SpeedTracker(window_seconds=1.0)
    tracker.add(100, 0.0)
    tracker.add(100, 0.5)
    assert tracker.speed(1.0) == 200.0
    tracker.add(100, 1.0)
    tracker.add(100, 1.5)
    assert tracker.speed(2.0) == 200.0
    assert _tune_concurrency(100.0, 120.0, 2, 4) == 3
    assert _tune_concurrency(100.0, 80.0, 3, 4) == 2
    assert _tune_concurrency(100.0, 100.0, 2, 4) == 2
    assert _tune_concurrency(100.0, 120.0, 2, 4, error_burst=True) == 1


def test_speed_limiter_throttles() -> None:
    limiter = SpeedLimiter(4096)
    start = time.monotonic()
    for _ in range(4):
        limiter.wait(4096)
    elapsed = time.monotonic() - start
    assert elapsed >= 2.8


def test_download_speed_limit_integration() -> None:
    payload = bytes(range(256)) * 256
    base, server = _start_server({"/video.bin": payload})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "video.bin"
            result = download_file(
                f"{base}/video.bin",
                dest,
                session=MediaSession(),
                chunk_size=37,
                concurrency=3,
                max_speed_bytes_per_sec=1024 * 1024,
            )
            assert result.path.read_bytes() == payload
            assert result.total_size == len(payload)
    finally:
        server.shutdown()


def test_download_adaptive_concurrency() -> None:
    payload = bytes(range(256)) * 8
    base, server = _start_server({"/video.bin": payload})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "video.bin"
            result = download_file(
                f"{base}/video.bin",
                dest,
                session=MediaSession(),
                chunk_size=37,
                concurrency=4,
                adaptive_concurrency=True,
                slow_shard_switch=True,
                slow_after_seconds=0.01,
                slow_idle_seconds=0.01,
                tune_interval=0.05,
            )
            assert result.path.read_bytes() == payload
            assert result.total_size == len(payload)
    finally:
        server.shutdown()


def test_download_content_range_fallback() -> None:
    payload = bytes(range(64)) * 4
    base, server = _start_server({"/video.bin": payload}, _RangeFallbackHandler)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "video.bin"
            result = download_file(
                f"{base}/video.bin",
                dest,
                session=MediaSession(),
                chunk_size=19,
                concurrency=3,
            )
            assert result.path.read_bytes() == payload
            assert result.resumed is True
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


def test_hls_byterange_init_and_fallback_merge() -> None:
    init_data = b"INITDATA"
    media_data = b"ABCDEFGHIJKLMNOP"
    playlist = (
        "#EXTM3U\n"
        "#EXT-X-TARGETDURATION:6\n"
        '#EXT-X-MAP:URI="/init.mp4",BYTERANGE="8@0"\n'
        "#EXT-X-BYTERANGE:4@8\n"
        "#EXTINF:6.0,\n"
        "/media.bin\n"
        "#EXT-X-BYTERANGE:4\n"
        "#EXTINF:6.0,\n"
        "/media.bin\n"
    )
    base, server = _start_server(
        {
            "/playlist.m3u8": playlist.encode("utf-8"),
            "/init.mp4": init_data,
            "/media.bin": media_data,
        }
    )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            result = download_hls(
                f"{base}/playlist.m3u8",
                tmp,
                ffmpeg_path=None,
                concurrency=2,
                segment_retries=2,
            )
            assert result.output_path is not None
            assert result.output_path.read_bytes() == b"INITDATAIJKLMNOP"
            assert (Path(tmp) / "segments" / "init.mp4").read_bytes() == init_data
            assert (Path(tmp) / "segments" / "seg_000000.ts").read_bytes() == b"IJKL"
            assert (Path(tmp) / "segments" / "seg_000001.ts").read_bytes() == b"MNOP"
            concat = (Path(tmp) / "concat.txt").read_text(encoding="utf-8")
            assert "init.mp4" in concat
    finally:
        server.shutdown()


def test_dependencies_status() -> None:
    status = check_status()
    for key in (
        "playwright",
        "pycryptodome",
        "curl_cffi",
        "cloudscraper",
        "httpx",
        "h2",
        "patchright",
        "nodriver",
        "drission_page",
        "ocr",
        "chromium",
        "ffmpeg",
        "ffprobe",
        "runtime_dir",
        "ready",
    ):
        assert key in status, f"check_status missing {key}"


def test_transcode_profiles_hardware_and_copy() -> None:
    encoder_text = " Encoders:\n" " V..... libx264\n" " V..... h264_nvenc\n" " A..... aac\n"
    encoders = parse_encoder_list(encoder_text)
    assert {"libx264", "h264_nvenc", "aac"}.issubset(encoders)
    assert select_hardware_encoder("h264", encoders) == "h264_nvenc"
    assert select_hardware_encoder("h264", encoders, prefer="h264_qsv") is None

    info = MediaInfo(10.0, "mp4", [], video_codec="h264", audio_codec="aac")
    copy_args = build_ffmpeg_args(
        "in.mp4",
        "out.mp4",
        TranscodeOptions(),
        info=info,
        encoders=encoders,
    )
    assert copy_args[copy_args.index("-c:v") + 1] == "copy"
    assert copy_args[copy_args.index("-c:a") + 1] == "copy"
    assert copy_args[copy_args.index("-movflags") + 1] == "+faststart"
    assert "-progress" in copy_args
    assert copy_args[copy_args.index("-progress") + 1] == "pipe:1"
    assert "-nostats" in copy_args

    reencode_args = build_ffmpeg_args(
        "in.mp4",
        "out.mp4",
        TranscodeOptions(smart_copy=False),
        info=MediaInfo(10.0, "mp4", [], video_codec="hevc", audio_codec="aac"),
        encoders=encoders,
    )
    assert reencode_args[reencode_args.index("-c:v") + 1] == "libx264"
    assert "-crf" in reencode_args

    hw_args = build_ffmpeg_args(
        "in.mp4",
        "out.mp4",
        TranscodeOptions(video_codec="libx264", hardware=True, smart_copy=False),
        info=info,
        encoders=encoders,
    )
    assert hw_args[hw_args.index("-c:v") + 1] == "h264_nvenc"
    assert "-cq" in hw_args
    assert "-preset" in hw_args

    audio_args = build_ffmpeg_args(
        "in.mp4",
        "out.mp3",
        TranscodeOptions(audio_only=True, audio_codec="libmp3lame", smart_copy=False),
        info=info,
        encoders=encoders,
    )
    assert "-vn" in audio_args
    assert audio_args[audio_args.index("-c:a") + 1] == "libmp3lame"
    assert transcode_main(["--list-profiles"]) == 0


def test_transcode_file_progress_with_fake_ffmpeg() -> None:
    class _FakeProcess:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.stdout = io.StringIO("out_time_ms=1000000\nspeed=2.5x\n")
            self.stderr = io.StringIO("")
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = 1

        def wait(self) -> None:
            pass

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(b"fake")
        dst = Path(tmp) / "out.mp3"
        events = []
        with mock.patch(
            "ffmpeg_transcoder.subprocess.Popen",
            return_value=_FakeProcess(),
        ):
            transcode_file(
                src,
                dst,
                ffmpeg_path=sys.executable,
                ffprobe_path="missing-ffprobe",
                profile="mp3",
                smart_copy=False,
                progress=events.append,
            )
        assert events
        assert events[-1].out_time_s == 1.0
        assert events[-1].speed == "2.5x"


def test_transcode_rich_progress_fields() -> None:
    class _FakeProcess:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.stdout = io.StringIO(
                "out_time_ms=500000\n"
                "fps=30.0\n"
                "bitrate=1234.5kbits/s\n"
                "total_size=2048\n"
                "frame=15\n"
                "progress=continue\n"
                "speed=2.0x\n"
            )
            self.stderr = io.StringIO("")
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = 1

        def wait(self) -> None:
            pass

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(b"fake")
        dst = Path(tmp) / "out.mp3"
        events = []
        with mock.patch(
            "ffmpeg_transcoder.subprocess.Popen",
            return_value=_FakeProcess(),
        ):
            transcode_file(
                src,
                dst,
                ffmpeg_path=sys.executable,
                ffprobe_path="missing-ffprobe",
                profile="mp3",
                smart_copy=False,
                progress=events.append,
            )
        assert events
        transcode_event = next(
            event for event in events if event.stage == "transcode" and event.state == "continue"
        )
        assert transcode_event.fps == 30.0
        assert transcode_event.bitrate == "1234.5kbits/s"
        assert transcode_event.output_size == 2048
        assert transcode_event.frame == 15
        assert transcode_event.state == "continue"
        assert events[-1].stage == "finalize"
        assert events[-1].percent == 1.0
        assert events[-1].state == "end"
        assert events[-1].output_size == 2048


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

    expired = extract_cloudflare_state(
        "<html><body>ok</body></html>",
        "https://example.com/",
        cookies=[
            {
                "name": "cf_clearance",
                "value": "old",
                "domain": "example.com",
                "path": "/",
                "expires": 1,
            }
        ],
    )
    assert expired.clearance_cookie == "old"
    assert not expired.clearance_valid
    assert expired.stage == "none"

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


def test_smart_fetch_factory_and_status() -> None:
    assert isinstance(create_fetch_session({"backend": "standard"}), MediaSession)
    assert isinstance(create_fetch_session({"backend": "auto"}), SmartFetchSession)
    assert "urllib" in available_backends()
    status = backend_status()
    assert status["backends"][-1]["name"] == "urllib"


def test_smart_fetch_auto_fallback_local() -> None:
    base, server = _start_server({"/page.html": b"<html><body>ok</body></html>"})
    try:
        session = SmartFetchSession(min_interval=0.0, max_retries=0)
        body, status, headers = session.get_bytes_with_meta(f"{base}/page.html")
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
    assert session.stats["switches"] == 1


def test_smart_fetch_blocked_metadata() -> None:
    base, server = _start_server({"/blocked": b"ignored"}, _BlockingHandler)
    _BlockingHandler.blocked_paths = {"/blocked"}
    try:
        session = SmartFetchSession(min_interval=0.0, max_retries=0)
        body, status, _ = session.get_bytes_with_meta(f"{base}/blocked")
        assert status == 403
        assert b"Access Denied" in body
        assert session.stats["last_backend"] == "urllib"
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
    assert session._cookie_header("http://example.com/") == ""


def test_ensure_web_fetch_dependencies_status() -> None:
    status = ensure_status()
    names = {item["name"] for item in status["packages"]}
    assert names == {
        "curl_cffi",
        "cloudscraper",
        "httpx",
        "h2",
        "patchright",
        "nodriver",
        "DrissionPage",
    }
    assert set(missing_packages()).issubset(names)
    check = ensure_dependencies(install=False)
    assert check["ready"] == status["ready"]


def test_ensure_web_fetch_dependencies_frozen_install_blocked() -> None:
    original = getattr(sys, "frozen", None)
    try:
        sys.frozen = True
        with mock.patch("ensure_web_fetch_dependencies._module_available", return_value=False):
            try:
                ensure_dependencies(install=True, packages=["curl_cffi"])
            except DependencyInstallError as exc:
                assert "not bundled" in str(exc)
            else:
                raise AssertionError("frozen web-fetch install should be blocked")
    finally:
        if original is None:
            del sys.frozen
        else:
            sys.frozen = original


def test_media_dependencies_frozen_install_blocked() -> None:
    original = getattr(sys, "frozen", None)
    try:
        sys.frozen = True
        with tempfile.TemporaryDirectory() as tmp:
            try:
                install_dependencies(install=True, runtime_dir=tmp)
            except RuntimeError as exc:
                assert "not bundled" in str(exc)
            else:
                raise AssertionError("frozen media install should be blocked")
    finally:
        if original is None:
            del sys.frozen
        else:
            sys.frozen = original


def test_ensure_all_dependencies_status() -> None:
    result = ensure_all_status()
    assert set(result) == {"web_fetch", "media", "manifest", "ready"}
    assert isinstance(result["ready"], bool)


def test_ensure_all_dependencies_frozen_install_blocked() -> None:
    original = getattr(sys, "frozen", None)
    try:
        sys.frozen = True
        try:
            ensure_all_dependencies(install=True)
        except RuntimeError as exc:
            assert "not bundled" in str(exc)
        else:
            raise AssertionError("frozen unified install should be blocked")
    finally:
        if original is None:
            del sys.frozen
        else:
            sys.frozen = original


def test_smart_fetch_auto_install_hook() -> None:
    session = SmartFetchSession(
        backend="auto",
        auto_install_dependencies=True,
        min_interval=0.0,
        max_retries=0,
    )
    with mock.patch.object(session, "_ensure_dependencies") as ensure_mock:
        order = session._ordered_backends()
    ensure_mock.assert_called_once_with()
    assert "urllib" in order


def test_flaresolverr_client_parses_solution() -> None:
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
        assert client.list_sessions() == ["s1"]
    finally:
        server.shutdown()


def test_smart_fetch_flaresolverr_backend_order() -> None:
    session = SmartFetchSession(
        backend="auto",
        flaresolverr_config={"base_url": "http://127.0.0.1:8191"},
        auto_install_dependencies=False,
        min_interval=0.0,
        max_retries=0,
    )
    assert "flaresolverr" in session._ordered_backends()


def test_stealth_browser_engine_availability() -> None:
    engines = set(available_stealth_engines())
    assert engines.issubset({"patchright", "nodriver", "drission_page"})
    try:
        solve_cloudflare_with_stealth_browser("https://example.com/", engine="unsupported")
        raise AssertionError("unsupported engine must raise")
    except StealthBrowserError:
        pass


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
        client = ApiClient(
            min_interval=0.0,
            max_retries=0,
            backend="auto",
            auto_install=False,
        )
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
            backend="auto",
            auto_install=False,
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


def test_sidecar_media_probe_endpoint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = MediaPipelineService(Path(tmp) / "tasks.sqlite", token="test-token")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        media_path = Path(tmp) / "video.mp4"
        media_path.write_bytes(b"fake")

        def auth_request(path: str, data: dict) -> urllib.request.Request:
            headers = {
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            }
            return urllib.request.Request(
                f"{base}{path}",
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
                method="POST",
            )

        try:
            try:
                urllib.request.urlopen(auth_request("/media/probe", {"path": str(media_path)}))
            except urllib.error.HTTPError as exc:
                assert exc.code in (200, 404), exc.code
            try:
                urllib.request.urlopen(
                    auth_request("/media/probe", {"path": str(Path(tmp) / "missing.mp4")})
                )
                raise AssertionError("missing media file must be rejected")
            except urllib.error.HTTPError as exc:
                assert exc.code == 400, exc.code
        finally:
            server.shutdown()
            server.server_close()
            service.close()


def test_sidecar_progress_meta_endpoint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = MediaPipelineService(Path(tmp) / "tasks.sqlite", token="test-token")
        task = service.queue.enqueue("download", {"url": "x", "dest": "y"})
        meta = {
            "downloaded": 4096,
            "total": 102400,
            "percent": 0.04,
            "speed": 8192.0,
            "eta_s": 12.0,
            "chunks_done": 1,
            "chunks_total": 8,
        }
        service._publish_progress(task.id, "download", 0.04, meta, message="chunk 1/8")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            request = urllib.request.Request(
                f"{base}/tasks/{task.id}/progress",
                headers={"Authorization": "Bearer test-token"},
            )
            with urllib.request.urlopen(request) as response:
                snapshot = json.loads(response.read().decode("utf-8"))
            assert snapshot["progress_meta"] == meta
            assert snapshot["stage"] == "download"
            assert snapshot["events"][0]["meta"] == meta
            request = urllib.request.Request(
                f"{base}/tasks/{task.id}/events",
                headers={"Authorization": "Bearer test-token"},
            )
            with urllib.request.urlopen(request) as response:
                events = json.loads(response.read().decode("utf-8"))
            assert events["events"][0]["stage"] == "download"
            assert events["next"] == 1
        finally:
            server.shutdown()
            server.server_close()
            service.close()


def test_sidecar_long_poll_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = MediaPipelineService(Path(tmp) / "tasks.sqlite", token="test-token")
        task = service.queue.enqueue("download", {"url": "x", "dest": "y"})
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def emit_event() -> None:
            time.sleep(0.15)
            service._publish_progress(
                task.id,
                "download",
                0.5,
                {"downloaded": 512, "total": 1024},
                message="long-poll event",
            )

        emitter = threading.Thread(target=emit_event, daemon=True)
        emitter.start()
        try:
            request = urllib.request.Request(
                f"{base}/tasks/{task.id}/events?after=0&timeout=3",
                headers={"Authorization": "Bearer test-token"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            assert payload["events"], "long poll must wait for a new event"
            assert payload["events"][0]["stage"] == "download"
            assert payload["events"][0]["meta"]["total"] == 1024
        finally:
            emitter.join()
            server.shutdown()
            server.server_close()
            service.close()


def test_sidecar_transcode_payload_options() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = MediaPipelineService(Path(tmp) / "tasks.sqlite")
        captured: dict = {}

        def fake_transcode_file(*args: object, **kwargs: object) -> Path:
            captured.update(kwargs)
            return Path(tmp) / "out.mp3"

        with mock.patch(
            "ffmpeg_transcoder.transcode_file",
            side_effect=fake_transcode_file,
        ):
            task = service.queue.enqueue(
                "transcode",
                {
                    "src": str(Path(tmp) / "in.mp4"),
                    "dst": str(Path(tmp) / "out.mp3"),
                    "profile": "mp3",
                    "hardware": True,
                    "smart_copy": False,
                    "extra_args": ["-map", "0:a"],
                    "start_time": "00:01:00",
                    "duration": "120",
                    "threads": 4,
                },
            )
            result = service._run_task(task)
        assert result is not None
        assert captured["profile"] == "mp3"
        assert captured["hardware"] is True
        assert captured["smart_copy"] is False
        assert captured["extra_args"] == ["-map", "0:a"]
        assert captured["start_time"] == "00:01:00"
        assert captured["duration"] == "120"
        assert captured["threads"] == 4
        service.close()


def test_format_catalog_integrates_profiles() -> None:
    assert lookup_format(".MP4") is not None
    assert lookup_format("jpg") is not None
    assert lookup_format("mp4").profile == "mp4"
    assert "video" in formats_by_category("video")[0].category
    categories = {item["id"] for item in catalog_payload()["categories"]}
    assert {
        "video",
        "audio",
        "image",
        "subtitle",
        "document",
        "data",
        "archive",
    }.issubset(categories)
    assert engine_targets("stdlib")
    for spec in FORMAT_CATALOG:
        if spec.engine == "ffmpeg" and spec.profile:
            assert spec.profile in TRANSCODE_PROFILES, spec.profile
    for extension, profile in EXTENSION_PROFILE.items():
        assert profile in TRANSCODE_PROFILES, extension
    payload = catalog_payload()
    assert payload["count"] == len(FORMAT_CATALOG)
    assert len(payload["formats"]) == payload["count"]


def test_file_converter_text_archive_subtitle_batch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        md = root / "a.md"
        md.write_text("# Hello\n\nWorld\n", encoding="utf-8")
        html_path = root / "a.html"
        result = convert_file(md, html_path)
        assert result.engine == "stdlib"
        assert "<h1>Hello</h1>" in html_path.read_text(encoding="utf-8")

        csv_path = root / "data.csv"
        csv_path.write_text("id,name\n1,Alpha\n", encoding="utf-8")
        json_path = root / "data.json"
        convert_file(csv_path, json_path)
        assert json.loads(json_path.read_text(encoding="utf-8"))[0]["name"] == "Alpha"

        srt_path = root / "sub.srt"
        srt_path.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
            encoding="utf-8",
        )
        vtt_path = root / "sub.vtt"
        convert_file(srt_path, vtt_path)
        assert "00:00:01.000" in vtt_path.read_text(encoding="utf-8")

        zip_path = root / "bundle.zip"
        convert_file(csv_path, zip_path)
        extracted = root / "extracted"
        written = extract_archive(zip_path, extracted)
        assert written and (extracted / csv_path.name).exists()

        md2 = root / "b.md"
        md2.write_text("## Second\n\nBody\n", encoding="utf-8")
        events: list[BatchConvertProgress] = []
        summary = convert_many(
            [md, md2],
            root / "batch",
            "html",
            progress=events.append,
        )
        assert len(summary["results"]) == 2
        assert events and isinstance(events[0], BatchConvertProgress)
        assert events[-1].done == 2
        assert events[-1].percent == 1.0


def test_file_converter_ffmpeg_dispatch_and_optional() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(b"fake")
        captured: dict = {}

        def fake_transcode(*args: object, **kwargs: object) -> Path:
            captured.update(kwargs)
            dst = Path(args[1])
            dst.write_bytes(b"out")
            return dst

        with mock.patch(
            "ffmpeg_transcoder.transcode_file",
            side_effect=fake_transcode,
        ):
            result = convert_file(src, Path(tmp) / "out.mp3")
        assert result.engine == "ffmpeg"
        assert captured["profile"] == "mp3"

        md = Path(tmp) / "doc.md"
        md.write_text("# Doc\n", encoding="utf-8")
        try:
            convert_file(md, Path(tmp) / "doc.pdf")
            raise AssertionError("optional PDF conversion must be unavailable by default")
        except ConversionUnavailable:
            pass


def test_download_checkpoint_entity_and_hash() -> None:
    import hashlib

    payload = bytes(range(256)) * 4
    base, server = _start_server({"/video.bin": payload})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "video.bin"
            stale = _build_chunk_map(
                len(payload),
                1024,
                entity_tag='"old"',
                last_modified="Thu, 01 Jan 2024 00:00:00 GMT",
            )
            checkpoint = dest.with_name(f"{dest.name}.chunks.json")
            checkpoint.write_text(json.dumps(stale), encoding="utf-8")
            assert (
                _load_chunk_map(
                    dest,
                    len(payload),
                    entity_tag=f'"v1-{len(payload)}"',
                    last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
                )
                is None
            )
            expected = hashlib.sha256(payload).hexdigest()
            result = download_file(
                f"{base}/video.bin",
                dest,
                session=MediaSession(),
                chunk_size=37,
                concurrency=3,
                expected_sha256=expected,
            )
            assert result.path.read_bytes() == payload
            assert result.content_type == "application/octet-stream"
            assert result.filename == "video.bin"
            try:
                download_file(
                    f"{base}/video.bin",
                    dest.with_name("bad.bin"),
                    session=MediaSession(),
                    expected_sha256="0" * 64,
                )
                raise AssertionError("hash mismatch must raise")
            except DownloadHashError:
                pass
    finally:
        server.shutdown()


def test_download_batch_progress() -> None:
    first = b"a" * 1024
    second = b"b" * 2048
    base, server = _start_server({"/one.bin": first, "/two.bin": second})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            result = download_batch(
                [f"{base}/one.bin", f"{base}/two.bin"],
                Path(tmp),
                session=MediaSession(),
                chunk_size=64,
                concurrency=2,
                progress=events.append,
            )
            assert len(result.paths) == 2
            assert result.total_bytes == len(first) + len(second)
            assert result.downloaded_bytes == len(first) + len(second)
            assert events and events[0].stage == "preflight"
            assert events[-1].done == 2
            assert events[-1].percent == 1.0
            assert (Path(tmp) / "one.bin").read_bytes() == first
            assert (Path(tmp) / "two.bin").read_bytes() == second
    finally:
        server.shutdown()


def test_sidecar_formats_and_convert_task() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = MediaPipelineService(Path(tmp) / "tasks.sqlite", token="test-token")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def request(path: str) -> dict:
            req = urllib.request.Request(
                f"{base}{path}",
                headers={"Authorization": "Bearer test-token"},
            )
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode("utf-8"))

        try:
            formats = request("/formats")
            assert formats["count"] == len(FORMAT_CATALOG)
            assert any(category["id"] == "video" for category in formats["categories"])

            captured: dict = {}

            def fake_convert(*args: object, **kwargs: object) -> ConvertResult:
                captured.update(kwargs)
                return ConvertResult(Path(tmp) / "out.mp3", "ffmpeg", 1, 1)

            with mock.patch(
                "file_converter.convert_file",
                side_effect=fake_convert,
            ):
                task = service.queue.enqueue(
                    "convert",
                    {
                        "src": str(Path(tmp) / "in.mp4"),
                        "dst": str(Path(tmp) / "out.mp3"),
                        "profile": "mp3",
                    },
                )
                result = service._run_task(task)
            assert result == str(Path(tmp) / "out.mp3")
            assert captured["profile"] == "mp3"

            captured2: dict = {}

            def fake_many(*args: object, **kwargs: object) -> dict:
                captured2.update(kwargs)
                return {
                    "results": [],
                    "total_input_bytes": 10,
                    "total_output_bytes": 8,
                    "elapsed_s": 0.1,
                    "average_speed": 80.0,
                }

            with mock.patch(
                "file_converter.convert_many",
                side_effect=fake_many,
            ):
                task = service.queue.enqueue(
                    "batch-convert",
                    {
                        "srcs": ["a.mp3", "b.mp3"],
                        "output_dir": str(Path(tmp) / "out"),
                        "target": "mp3",
                    },
                )
                summary = json.loads(service._run_task(task))
            assert summary["total_input_bytes"] == 10
            assert captured2["target_ext"] == "mp3"

            captured3: dict = {}

            def fake_batch(*args: object, **kwargs: object) -> BatchDownloadResult:
                captured3.update(kwargs)
                return BatchDownloadResult(
                    paths=[Path(tmp) / "a.bin"],
                    total_bytes=10,
                    downloaded_bytes=10,
                    elapsed_s=0.1,
                    average_speed=100.0,
                )

            with mock.patch(
                "media_pipeline_service.download_batch",
                side_effect=fake_batch,
            ):
                task = service.queue.enqueue(
                    "batch-download",
                    {
                        "urls": ["https://example.com/a.bin"],
                        "dest_dir": str(Path(tmp) / "downloads"),
                    },
                )
                summary = json.loads(service._run_task(task))
            assert summary["total_bytes"] == 10
            assert captured3["task_id"] == task.id
        finally:
            server.shutdown()
            server.server_close()
            service.close()


def test_builtin_dependency_manager_archive_install() -> None:
    import hashlib
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bin/tool.bin", b"tool")
    payload = buffer.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    base, server = _start_server({"/tool.zip": payload})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            spec = DependencySpec(
                name="tool",
                kind="archive",
                url=f"{base}/tool.zip",
                version="1.0",
                sha256=digest,
                bin_names=("tool.bin",),
            )
            events: list[tuple[str, float | None, str]] = []
            manager = BuiltinDependencyManager(
                runtime,
                [spec],
                progress=lambda stage, percent, message: events.append((stage, percent, message)),
            )
            before = manager.check_status()
            assert before["items"][0]["installed"] is False
            result = manager.install(install=True)
            assert result["ready"] is True
            assert (runtime / "tool" / "bin" / "tool.bin").is_file()
            assert manager.environment()["tool"]["paths"]
            assert any("downloaded" in message for _, _, message in events)
    finally:
        server.shutdown()


def test_builtin_dependency_manager_portable_and_sha_mismatch() -> None:
    import hashlib

    payload = b"portable-tool"
    digest = hashlib.sha256(payload).hexdigest()
    base, server = _start_server({"/tool.exe": payload})
    try:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            spec = DependencySpec(
                name="tool",
                kind="portable",
                url=f"{base}/tool.exe",
                sha256=digest,
                bin_names=("tool.bin",),
                download_name="tool",
            )
            manager = BuiltinDependencyManager(
                runtime,
                [spec],
                progress=lambda stage, percent, message: None,
            )
            result = manager.install(install=True)
            assert result["items"][0]["paths"][0].endswith("tool.bin")

            bad_spec = DependencySpec(
                name="bad",
                kind="portable",
                url=f"{base}/tool.exe",
                sha256="0" * 64,
                bin_names=("bad.bin",),
                download_name="bad",
            )
            bad_manager = BuiltinDependencyManager(
                runtime,
                [bad_spec],
                progress=lambda stage, percent, message: None,
            )
            try:
                bad_manager.install(install=True)
                raise AssertionError("sha256 mismatch must fail the install")
            except DependencyError:
                pass
            assert not (runtime / "downloads" / "bad.exe").exists()
    finally:
        server.shutdown()


def test_builtin_dependency_manager_check_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp) / "runtime"
        spec = DependencySpec(
            name="tool",
            kind="archive",
            url="https://example.invalid/tool.zip",
            bin_names=("tool.bin",),
        )
        manager = BuiltinDependencyManager(runtime, [spec])
        result = manager.install(install=False)
        assert result["ready"] is False
        assert not runtime.exists()
        empty = BuiltinDependencyManager(runtime, [])
        assert empty.check_status()["ready"] is True


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
        test_task_queue_progress_meta,
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
        test_speed_tracker_and_tuning,
        test_download_adaptive_concurrency,
        test_download_content_range_fallback,
        test_download_without_content_length,
        test_download_progress_total_size_and_meta,
        test_download_auto_chunk_sizing,
        test_speed_limiter_throttles,
        test_download_speed_limit_integration,
        test_hls_download,
        test_hls_quality_selection,
        test_hls_byterange_init_and_fallback_merge,
        test_dependencies_status,
        test_transcode_profiles_hardware_and_copy,
        test_transcode_file_progress_with_fake_ffmpeg,
        test_transcode_rich_progress_fields,
        test_pipeline_service,
        test_pipeline_bad_requests,
        test_crawl_task,
        test_crawl_deep,
        test_analyze_task,
        test_security_detector_classifications,
        test_cloudflare_state_extraction,
        test_cloudflare_challenge_handler,
        test_smart_fetch_factory_and_status,
        test_smart_fetch_auto_fallback_local,
        test_smart_fetch_switches_backend,
        test_smart_fetch_blocked_metadata,
        test_smart_fetch_preserves_clearance_cookie,
        test_ensure_web_fetch_dependencies_status,
        test_ensure_web_fetch_dependencies_frozen_install_blocked,
        test_media_dependencies_frozen_install_blocked,
        test_ensure_all_dependencies_status,
        test_ensure_all_dependencies_frozen_install_blocked,
        test_smart_fetch_auto_install_hook,
        test_flaresolverr_client_parses_solution,
        test_smart_fetch_flaresolverr_backend_order,
        test_stealth_browser_engine_availability,
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
        test_sidecar_media_probe_endpoint,
        test_sidecar_progress_meta_endpoint,
        test_sidecar_long_poll_events,
        test_sidecar_transcode_payload_options,
        test_format_catalog_integrates_profiles,
        test_file_converter_text_archive_subtitle_batch,
        test_file_converter_ffmpeg_dispatch_and_optional,
        test_download_checkpoint_entity_and_hash,
        test_download_batch_progress,
        test_sidecar_formats_and_convert_task,
        test_builtin_dependency_manager_archive_install,
        test_builtin_dependency_manager_portable_and_sha_mismatch,
        test_builtin_dependency_manager_check_only,
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
