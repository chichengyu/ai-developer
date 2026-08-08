"""Local HTTP service for the media pipeline.

Runs the Python media engine as a sidecar so any desktop UI language
(C#, JS/TS, Go, Rust, Kotlin, Swift, Java, C++) can use it over
127.0.0.1 with JSON. The service also owns the SQLite task queue and an
optional worker pool.

Endpoints:
  GET  /health
  GET  /deps/status
  GET  /deps/progress
  POST /deps/install
  POST /tasks                 enqueue {kind, payload, dedupe_key, priority}
  GET  /tasks                 list with status/limit/offset/search
  GET  /tasks/<id>            one task
  POST /tasks/<id>/pause|resume|cancel
  POST /workers/start|stop

Optional auth: pass `--token` and send
`Authorization: Bearer <token>` on every request except `/health`.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from media_dependencies import check_status, install_dependencies
from media_downloader import download_file, safe_output_name
from task_queue import TaskQueue, TaskRecord

MAX_REQUEST_BODY = 16 * 1024 * 1024


def _task_to_dict(task: TaskRecord) -> dict[str, Any]:
    return asdict(task)


def _filename_from_url(url: str, default_ext: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] if "/" in path else path
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    fallback = f"{digest}{default_ext}"
    if not name or "." not in name:
        return fallback
    return safe_output_name(unquote(name), fallback)


class MediaPipelineService:
    """Owns the SQLite queue and runs download/HLS/transcode workers."""

    def __init__(
        self,
        db_path: str | Path,
        runtime_dir: str | Path | None = None,
        workers: int = 2,
        token: str | None = None,
    ) -> None:
        self.queue = TaskQueue(db_path)
        self.runtime_dir = runtime_dir
        self.workers = workers
        self.token = token
        self._pool: ThreadPoolExecutor | None = None
        self._stop = threading.Event()
        self._install_lock = threading.Lock()
        self._progress_lock = threading.Lock()
        self._installing = False
        self._install_progress: dict[str, Any] = {
            "stage": "",
            "percent": None,
            "message": "",
        }
        self.queue.reset_stale_running()

    def start_workers(self) -> None:
        if self._pool is not None:
            return
        self._stop.clear()
        self._pool = ThreadPoolExecutor(max_workers=self.workers)
        for _ in range(self.workers):
            self._pool.submit(self._worker_loop)

    def stop_workers(self) -> None:
        self._stop.set()
        if self._pool is not None:
            self._pool.shutdown(wait=False)
            self._pool = None

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            task = self.queue.claim_next()
            if task is None:
                time.sleep(0.5)
                continue
            try:
                result = self._run_task(task)
                self.queue.succeed(task.id, result_path=str(result) if result else None)
            except Exception as exc:
                self.queue.fail(task.id, str(exc), retry=True)

    def _run_task(self, task: TaskRecord) -> str | None:
        payload = task.payload
        if task.kind == "crawl":
            from media_parser import extract_media_urls

            url = payload["url"]
            session = self._build_session(payload)
            body, _ = session.get_bytes(url)
            extraction = extract_media_urls(
                body.decode("utf-8", "replace"),
                base_url=payload.get("base_url") or url,
            )
            summary = {
                "url": url,
                "videos": len(extraction.videos),
                "audios": len(extraction.audios),
                "images": len(extraction.images),
                "hls": len(extraction.hls),
                "links": len(extraction.links),
            }
            if payload.get("download", True):
                dest_dir = Path(payload.get("dest_dir", "downloads"))
                dest_dir.mkdir(parents=True, exist_ok=True)
                media_groups = [
                    ("hls", extraction.hls, ".mp4"),
                    ("video", extraction.videos, ".mp4"),
                    ("audio", extraction.audios, ".mp3"),
                    ("image", extraction.images, ".jpg"),
                ]
                for kind, urls, default_ext in media_groups:
                    for media_url in urls:
                        dedupe_key = (
                            "sha256:" + hashlib.sha256(media_url.encode("utf-8")).hexdigest()
                        )
                        filename = _filename_from_url(media_url, default_ext)
                        if kind == "hls":
                            self.queue.enqueue(
                                "hls",
                                {
                                    "playlist_url": media_url,
                                    "output_dir": str(dest_dir / "hls"),
                                    "output_name": filename,
                                },
                                dedupe_key=dedupe_key,
                            )
                        else:
                            self.queue.enqueue(
                                "download",
                                {
                                    "url": media_url,
                                    "dest": str(dest_dir / filename),
                                },
                                dedupe_key=dedupe_key,
                            )
            return json.dumps(summary, ensure_ascii=False)
        if task.kind == "download":
            session = self._build_session(payload)
            download_kwargs: dict[str, Any] = {
                "resume": bool(payload.get("resume", True)),
            }
            if payload.get("chunk_size") is not None:
                download_kwargs["chunk_size"] = int(payload["chunk_size"])
            if payload.get("concurrency") is not None:
                download_kwargs["concurrency"] = int(payload["concurrency"])
            download_result = download_file(
                payload["url"],
                payload["dest"],
                session=session,
                task_id=task.id,
                headers=payload.get("headers"),
                **download_kwargs,
                progress=lambda progress: self.queue.update_progress(
                    task.id,
                    progress.percent or 0,
                    stage=progress.stage,
                ),
            )
            return str(download_result.path)
        if task.kind == "hls":
            from hls_downloader import download_hls

            session = self._build_session(payload)
            hls_result = download_hls(
                payload["playlist_url"],
                payload["output_dir"],
                output_name=payload.get("output_name", "output.mp4"),
                session=session,
                concurrency=int(payload.get("concurrency", 4)),
                quality=payload.get("quality"),
                task_id=task.id,
                ffmpeg_path=self._runtime_bin("ffmpeg"),
                progress=lambda progress: self.queue.update_progress(
                    task.id,
                    progress.percent,
                    stage="segments",
                ),
            )
            return str(hls_result.output_path or hls_result.output_dir)
        if task.kind == "transcode":
            from ffmpeg_transcoder import transcode_file

            transcode_result = transcode_file(
                payload["src"],
                payload["dst"],
                task_id=task.id,
                ffmpeg_path=self._runtime_bin("ffmpeg"),
                ffprobe_path=self._runtime_bin("ffprobe"),
                progress=lambda progress: self.queue.update_progress(
                    task.id,
                    progress.percent or 0,
                    stage="transcode",
                ),
            )
            return str(transcode_result)
        raise NotImplementedError(f"publisher adapter for kind={task.kind} is not implemented")

    def _runtime_bin(self, name: str) -> str:
        if self.runtime_dir:
            for suffix in ("", ".exe"):
                candidate = Path(self.runtime_dir) / "bin" / f"{name}{suffix}"
                if candidate.exists():
                    return str(candidate)
        return name

    @staticmethod
    def _build_session(payload: dict[str, Any]):
        from media_session import MediaSession

        return MediaSession(
            headers=payload.get("headers"),
            proxy=payload.get("proxy"),
        )

    def install_deps_async(self) -> bool:
        with self._install_lock:
            if self._installing:
                return False
            self._installing = True
        thread = threading.Thread(target=self._install_deps_worker, daemon=True)
        thread.start()
        return True

    def _install_deps_worker(self) -> None:
        try:
            install_dependencies(
                install=True,
                runtime_dir=self.runtime_dir,
                progress=self.set_install_progress,
            )
        finally:
            with self._install_lock:
                self._installing = False
            self.set_install_progress("done", 1.0, "install finished")

    @property
    def installing(self) -> bool:
        with self._install_lock:
            return self._installing

    def set_install_progress(self, stage: str, percent: float | None, message: str) -> None:
        with self._progress_lock:
            self._install_progress = {
                "stage": stage,
                "percent": percent,
                "message": message,
            }

    @property
    def install_progress(self) -> dict[str, Any]:
        with self._progress_lock:
            return dict(self._install_progress)

    def close(self) -> None:
        self.stop_workers()
        self.queue.close()


class MediaHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server that owns a media pipeline service."""

    media_service: MediaPipelineService


def _read_json(body: bytes) -> dict:
    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _make_handler(service: MediaPipelineService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if not service.token:
                return True
            expected = f"Bearer {service.token}"
            if hmac.compare_digest(self.headers.get("Authorization") or "", expected):
                return True
            self._send_json(401, {"error": "unauthorized"})
            return False

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path != "/health" and not self._authorized():
                return
            query = parse_qs(parsed.query)
            if path == "/health":
                self._send_json(200, {"ok": True, "installing": service.installing})
                return
            if path == "/deps/status":
                self._send_json(200, check_status(service.runtime_dir))
                return
            if path == "/deps/progress":
                self._send_json(200, service.install_progress)
                return
            if path == "/tasks":
                status = query.get("status", [None])[0]
                search = query.get("search", [None])[0]
                try:
                    limit = max(1, min(int(query.get("limit", ["50"])[0]), 500))
                    offset = max(0, int(query.get("offset", ["0"])[0]))
                except ValueError:
                    limit, offset = 50, 0
                items = service.queue.list_tasks(
                    status=status, search=search, limit=limit, offset=offset
                )
                self._send_json(
                    200,
                    {
                        "total": service.queue.count(status=status, search=search),
                        "items": [_task_to_dict(item) for item in items],
                    },
                )
                return
            if path.startswith("/tasks/"):
                parts = path.split("/")
                if len(parts) == 3 and parts[2].isdigit():
                    task = service.queue.get(int(parts[2]))
                    if task is None:
                        self._send_json(404, {"error": "task not found"})
                    else:
                        self._send_json(200, _task_to_dict(task))
                    return
            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if not self._authorized():
                return
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._send_json(400, {"error": "invalid Content-Length"})
                return
            if length < 0 or length > MAX_REQUEST_BODY:
                self._send_json(413, {"error": "request body too large"})
                return
            body = self.rfile.read(length) if length else b"{}"
            try:
                data = _read_json(body)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            if path == "/deps/install":
                started = service.install_deps_async()
                self._send_json(200, {"started": started})
                return
            if path == "/tasks":
                kind = data.get("kind")
                payload = data.get("payload")
                if not isinstance(kind, str) or not isinstance(payload, dict):
                    self._send_json(
                        400,
                        {"error": "kind must be a string and payload must be an object"},
                    )
                    return
                dedupe_key = data.get("dedupe_key")
                if dedupe_key is not None and not isinstance(dedupe_key, str):
                    self._send_json(400, {"error": "dedupe_key must be a string"})
                    return
                try:
                    priority = int(data.get("priority", 0))
                except (TypeError, ValueError):
                    self._send_json(400, {"error": "priority must be an integer"})
                    return
                max_attempts = data.get("max_attempts")
                if max_attempts is not None:
                    try:
                        max_attempts = int(max_attempts)
                    except (TypeError, ValueError):
                        self._send_json(400, {"error": "max_attempts must be an integer"})
                        return
                    if max_attempts <= 0:
                        self._send_json(400, {"error": "max_attempts must be positive"})
                        return
                resume_token = data.get("resume_token")
                if resume_token is not None and not isinstance(resume_token, dict):
                    self._send_json(400, {"error": "resume_token must be an object"})
                    return
                task = service.queue.enqueue(
                    kind=kind,
                    payload=payload,
                    dedupe_key=dedupe_key,
                    priority=priority,
                    max_attempts=max_attempts,
                    resume_token=resume_token,
                )
                self._send_json(200, _task_to_dict(task))
                return
            if path == "/workers/start":
                service.start_workers()
                self._send_json(200, {"ok": True})
                return
            if path == "/workers/stop":
                service.stop_workers()
                self._send_json(200, {"ok": True})
                return
            if path.startswith("/tasks/"):
                parts = path.split("/")
                if len(parts) == 4 and parts[2].isdigit():
                    task_id = int(parts[2])
                    action = parts[3]
                    if action == "pause":
                        service.queue.pause(task_id)
                    elif action == "resume":
                        service.queue.resume(task_id)
                    elif action == "cancel":
                        service.queue.cancel(task_id)
                    else:
                        self._send_json(404, {"error": "unknown action"})
                        return
                    self._send_json(200, {"ok": True})
                    return
            self._send_json(404, {"error": "not found"})

    return Handler


def run_service(
    db_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 0,
    workers: int = 2,
    runtime_dir: str | Path | None = None,
    token: str | None = None,
) -> MediaHTTPServer:
    service = MediaPipelineService(db_path, runtime_dir=runtime_dir, workers=workers, token=token)
    try:
        server = MediaHTTPServer((host, port), _make_handler(service))
    except Exception:
        service.close()
        raise
    service.start_workers()
    server.media_service = service
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the media pipeline sidecar")
    parser.add_argument("--db", default=None, help="SQLite task queue path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--runtime-dir", default=None)
    parser.add_argument("--token", default=None, help="Bearer token for local API")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        with tempfile.TemporaryDirectory() as tmp:
            svc = MediaPipelineService(Path(tmp) / "tasks.sqlite")
            task = svc.queue.enqueue("download", {"url": "x", "dest": "y"}, dedupe_key="self-test")
            assert task.id > 0
            assert svc.queue.count() == 1
            svc.close()
        print("media pipeline service self-test OK")
        return 0
    db = Path(args.db) if args.db else Path(tempfile.gettempdir()) / "media_tasks.sqlite"
    server = run_service(
        db,
        host=args.host,
        port=args.port,
        workers=args.workers,
        runtime_dir=args.runtime_dir,
        token=args.token,
    )
    print(f"media pipeline service on http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.media_service.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
