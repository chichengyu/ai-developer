"""Local, network-free tests for the media acquisition templates."""

from __future__ import annotations

import http.server
import json
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from captcha_solver import ManualCaptchaSolver  # noqa: E402
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
from task_queue import TaskQueue  # noqa: E402


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


def run() -> int:
    tests = [
        test_task_queue,
        test_task_queue_delayed_retry,
        test_media_parser,
        test_safe_output_name,
        test_filename_from_url,
        test_zip_member_safety,
        test_manual_captcha,
        test_chunked_download,
        test_download_without_content_length,
        test_hls_download,
        test_hls_quality_selection,
        test_dependencies_status,
        test_pipeline_service,
        test_pipeline_bad_requests,
        test_crawl_task,
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
