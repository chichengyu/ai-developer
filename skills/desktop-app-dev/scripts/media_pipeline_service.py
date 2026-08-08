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
  GET  /formats                unified format catalog
  POST /tasks                 enqueue {kind, payload, dedupe_key, priority}
  GET  /tasks                 list with status/limit/offset/search
  GET  /tasks/<id>            one task
  GET  /tasks/<id>/progress   rich progress snapshot
  GET  /tasks/<id>/events?after=N&timeout=0..30
  POST /tasks/<id>/pause|resume|cancel
  POST /workers/start|stop
  GET/POST/DELETE /proxy-pools, GET /proxy-pools/<name>
  GET/POST/DELETE /accounts, POST /accounts/<name>/acquire|release
  GET/POST /schedules, DELETE /schedules/<id>, POST /schedules/<id>/pause|resume
  GET /notifications/status, POST /notifications/test

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
from contextlib import suppress
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from account_manager import AccountManager
from ffmpeg_transcoder import probe_media
from media_dependencies import check_status, install_dependencies
from media_downloader import download_batch, download_file, safe_output_name
from media_formats import catalog_payload
from notifier import Notifier
from proxy_pool import ProxyPool, ProxyPoolStore
from task_queue import TaskQueue, TaskRecord
from task_scheduler import TaskScheduler

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
        accounts_path: str | Path | None = None,
        proxy_pools_path: str | Path | None = None,
        notifications: dict[str, Any] | None = None,
    ) -> None:
        self.queue = TaskQueue(db_path)
        self.scheduler = TaskScheduler(self.queue)
        self.accounts = AccountManager(accounts_path)
        self.proxy_pools = ProxyPoolStore(proxy_pools_path)
        self.notifier = Notifier.from_config(notifications)
        self.runtime_dir = runtime_dir
        self.workers = workers
        self.token = token
        self._pool: ThreadPoolExecutor | None = None
        self._stop = threading.Event()
        self._install_lock = threading.Lock()
        self._progress_lock = threading.Lock()
        self._events_lock = threading.Condition()
        self._task_events: dict[int, list[dict[str, Any]]] = {}
        self._installing = False
        self._install_progress: dict[str, Any] = {
            "stage": "",
            "percent": None,
            "message": "",
        }
        self._scheduler_thread: threading.Thread | None = None
        self.queue.reset_stale_running()

    def start_workers(self) -> None:
        if self._pool is not None:
            return
        self._stop.clear()
        self._pool = ThreadPoolExecutor(max_workers=self.workers)
        for _ in range(self.workers):
            self._pool.submit(self._worker_loop)
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
        )
        self._scheduler_thread.start()

    def stop_workers(self) -> None:
        self._stop.set()
        if self._pool is not None:
            self._pool.shutdown(wait=False)
            self._pool = None
        self._scheduler_thread = None

    def _scheduler_loop(self) -> None:
        while not self._stop.is_set():
            with suppress(Exception):
                self.scheduler.enqueue_due()
            time.sleep(1)

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            task = self.queue.claim_next()
            if task is None:
                time.sleep(0.5)
                continue
            account_name = task.payload.get("account")
            account = None
            success = False
            if account_name:
                account = self.accounts.acquire(str(account_name))
                if account is None:
                    self.queue.fail(
                        task.id,
                        f"account unavailable or in use: {account_name}",
                        retry=True,
                        delay_seconds=float(task.payload.get("retry_delay_seconds", 5.0)),
                    )
                    self._notify_task(task.id)
                    continue
            try:
                result = self._run_task(task, account=account)
                self.queue.succeed(task.id, result_path=str(result) if result else None)
                success = True
            except Exception as exc:
                self.queue.fail(
                    task.id,
                    str(exc),
                    retry=bool(task.payload.get("auto_retry", True)),
                    delay_seconds=float(task.payload.get("retry_delay_seconds", 0.0)),
                )
            finally:
                if account_name and account is not None:
                    self.accounts.release(
                        str(account_name),
                        success=success,
                        error=None if success else "task failed",
                    )
            self._notify_task(task.id)

    def _run_task(
        self,
        task: TaskRecord,
        account: dict[str, Any] | None = None,
    ) -> str | None:
        payload = task.payload
        if task.kind == "analyze":
            from page_data_parser import analyze_page

            url = payload["url"]
            session = self._build_session(
                payload,
                account=account,
                proxy_pool_store=self.proxy_pools,
            )
            body, _ = session.get_bytes(url)
            analysis = analyze_page(
                body.decode("utf-8", "replace"),
                base_url=payload.get("base_url") or url,
            )
            return json.dumps(
                analysis.to_dict(include_data=bool(payload.get("include_data", True))),
                ensure_ascii=False,
            )
        if task.kind == "webdata":
            from web_data_pipeline import WebDataPipeline

            config = payload.get("config")
            if not isinstance(config, dict):
                raise ValueError("webdata payload config must be an object")
            config = dict(config)
            if account:
                config = self._apply_account(config, account)
            if payload.get("proxy_pool") and "proxy_pool" not in config:
                config["proxy_pool"] = payload["proxy_pool"]
            output = payload.get("output")

            def progress(stage: str, percent: float, message: str) -> None:
                self._publish_progress(
                    task.id,
                    stage,
                    percent,
                    {
                        "stage": stage,
                        "percent": percent,
                        "message": message,
                    },
                    message=message,
                )

            summary = WebDataPipeline(config, output=output).run(progress=progress)
            return json.dumps(summary, ensure_ascii=False)
        if task.kind == "crawl":
            from media_parser import extract_media_urls

            url = payload["url"]
            session = self._build_session(
                payload,
                account=account,
                proxy_pool_store=self.proxy_pools,
            )
            body, _ = session.get_bytes(url)
            html = body.decode("utf-8", "replace")
            base_url = payload.get("base_url") or url
            extraction = extract_media_urls(
                html,
                base_url=base_url,
            )
            summary = {
                "url": url,
                "videos": len(extraction.videos),
                "audios": len(extraction.audios),
                "images": len(extraction.images),
                "hls": len(extraction.hls),
                "links": len(extraction.links),
            }
            if payload.get("deep", False):
                from page_data_parser import analyze_page

                summary["page_data"] = analyze_page(html, base_url=base_url).summary()
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
            session = self._build_session(
                payload,
                account=account,
                proxy_pool_store=self.proxy_pools,
            )
            download_kwargs: dict[str, Any] = {
                "resume": bool(payload.get("resume", True)),
            }
            if payload.get("chunk_size") is not None:
                download_kwargs["chunk_size"] = int(payload["chunk_size"])
            if payload.get("concurrency") is not None:
                download_kwargs["concurrency"] = int(payload["concurrency"])
            if payload.get("chunk_retries") is not None:
                download_kwargs["chunk_retries"] = int(payload["chunk_retries"])
            if payload.get("adaptive_concurrency") is not None:
                download_kwargs["adaptive_concurrency"] = bool(payload["adaptive_concurrency"])
            if payload.get("slow_shard_switch") is not None:
                download_kwargs["slow_shard_switch"] = bool(payload["slow_shard_switch"])
            if payload.get("slow_after_seconds") is not None:
                download_kwargs["slow_after_seconds"] = float(payload["slow_after_seconds"])
            if payload.get("slow_idle_seconds") is not None:
                download_kwargs["slow_idle_seconds"] = float(payload["slow_idle_seconds"])
            if payload.get("slow_restart_limit") is not None:
                download_kwargs["slow_restart_limit"] = int(payload["slow_restart_limit"])
            if payload.get("tune_interval") is not None:
                download_kwargs["tune_interval"] = float(payload["tune_interval"])
            if payload.get("auto_chunk_sizing") is not None:
                download_kwargs["auto_chunk_sizing"] = bool(payload["auto_chunk_sizing"])
            if payload.get("max_speed_bytes_per_sec") is not None:
                download_kwargs["max_speed_bytes_per_sec"] = float(
                    payload["max_speed_bytes_per_sec"]
                )
            download_result = download_file(
                payload["url"],
                payload["dest"],
                session=session,
                task_id=task.id,
                headers=payload.get("headers"),
                **download_kwargs,
                progress=lambda progress: self._publish_progress(
                    task.id,
                    progress.stage,
                    progress.percent,
                    self._download_meta(progress),
                ),
            )
            return str(download_result.path)
        if task.kind == "batch-download":
            session = self._build_session(
                payload,
                account=account,
                proxy_pool_store=self.proxy_pools,
            )
            batch_kwargs: dict[str, Any] = {
                key: payload[key]
                for key in (
                    "chunk_size",
                    "concurrency",
                    "chunk_retries",
                    "resume",
                    "auto_chunk_sizing",
                    "adaptive_concurrency",
                    "slow_shard_switch",
                    "slow_after_seconds",
                    "slow_idle_seconds",
                    "slow_restart_limit",
                    "tune_interval",
                    "max_speed_bytes_per_sec",
                )
                if payload.get(key) is not None
            }
            batch_result = download_batch(
                payload["urls"],
                payload["dest_dir"],
                session=session,
                task_id=task.id,
                headers=payload.get("headers"),
                progress=lambda progress: self._publish_progress(
                    task.id,
                    progress.stage,
                    progress.percent,
                    self._batch_download_meta(progress),
                ),
                **batch_kwargs,
            )
            return json.dumps(
                {
                    "paths": [str(path) for path in batch_result.paths],
                    "total_bytes": batch_result.total_bytes,
                    "downloaded_bytes": batch_result.downloaded_bytes,
                    "elapsed_s": batch_result.elapsed_s,
                    "average_speed": batch_result.average_speed,
                },
                ensure_ascii=False,
            )
        if task.kind == "hls":
            from hls_downloader import download_hls

            session = self._build_session(
                payload,
                account=account,
                proxy_pool_store=self.proxy_pools,
            )
            hls_result = download_hls(
                payload["playlist_url"],
                payload["output_dir"],
                output_name=payload.get("output_name", "output.mp4"),
                session=session,
                concurrency=int(payload.get("concurrency", 4)),
                quality=payload.get("quality"),
                segment_retries=int(payload.get("segment_retries", 3)),
                merge_fallback=bool(payload.get("merge_fallback", True)),
                keep_segments=bool(payload.get("keep_segments", True)),
                task_id=task.id,
                ffmpeg_path=self._runtime_bin("ffmpeg"),
                progress=lambda progress: self._publish_progress(
                    task.id,
                    progress.stage,
                    progress.percent,
                    self._hls_meta(progress),
                ),
            )
            return str(hls_result.output_path or hls_result.output_dir)
        if task.kind == "transcode":
            from ffmpeg_transcoder import transcode_file

            transcode_kwargs: dict[str, Any] = {}
            for key in (
                "profile",
                "video_codec",
                "video_preset",
                "crf",
                "audio_codec",
                "extra_args",
                "audio_bitrate",
                "video_bitrate",
                "resolution",
                "fps",
                "audio_channels",
                "audio_sample_rate",
                "faststart",
                "audio_only",
                "start_time",
                "duration",
                "threads",
            ):
                if payload.get(key) is not None:
                    transcode_kwargs[key] = payload[key]
            if payload.get("smart_copy") is not None:
                transcode_kwargs["smart_copy"] = bool(payload["smart_copy"])
            if payload.get("hardware") is not None:
                transcode_kwargs["hardware"] = payload["hardware"]
            transcode_result = transcode_file(
                payload["src"],
                payload["dst"],
                task_id=task.id,
                ffmpeg_path=self._runtime_bin("ffmpeg"),
                ffprobe_path=self._runtime_bin("ffprobe"),
                progress=lambda progress: self._publish_progress(
                    task.id,
                    progress.stage,
                    progress.percent,
                    self._transcode_meta(progress),
                ),
                **transcode_kwargs,
            )
            return str(transcode_result)
        if task.kind == "convert":
            from file_converter import convert_file

            convert_result = convert_file(
                payload["src"],
                payload["dst"],
                profile=payload.get("profile"),
                task_id=task.id,
                ffmpeg_path=self._runtime_bin("ffmpeg"),
                ffprobe_path=self._runtime_bin("ffprobe"),
                extra_args=payload.get("extra_args"),
                progress=lambda progress: self._publish_progress(
                    task.id,
                    progress.stage,
                    progress.percent,
                    self._convert_meta(progress),
                ),
            )
            return str(convert_result.path)
        if task.kind == "batch-convert":
            from file_converter import convert_many

            summary = convert_many(
                payload["srcs"],
                output_dir=payload["output_dir"],
                target_ext=payload["target"],
                task_id=task.id,
                ffmpeg_path=self._runtime_bin("ffmpeg"),
                ffprobe_path=self._runtime_bin("ffprobe"),
                progress=lambda progress: self._publish_progress(
                    task.id,
                    progress.stage,
                    progress.percent,
                    self._batch_convert_meta(progress),
                ),
            )
            return json.dumps(summary, ensure_ascii=False)
        raise NotImplementedError(f"publisher adapter for kind={task.kind} is not implemented")

    def _runtime_bin(self, name: str) -> str:
        if self.runtime_dir:
            for suffix in ("", ".exe"):
                candidate = Path(self.runtime_dir) / "bin" / f"{name}{suffix}"
                if candidate.exists():
                    return str(candidate)
        return name

    @staticmethod
    def _download_meta(progress: Any) -> dict[str, Any]:
        return asdict(progress)

    @staticmethod
    def _batch_download_meta(progress: Any) -> dict[str, Any]:
        return asdict(progress)

    @staticmethod
    def _hls_meta(progress: Any) -> dict[str, Any]:
        return asdict(progress)

    @staticmethod
    def _transcode_meta(progress: Any) -> dict[str, Any]:
        return asdict(progress)

    @staticmethod
    def _convert_meta(progress: Any) -> dict[str, Any]:
        return asdict(progress)

    @staticmethod
    def _batch_convert_meta(progress: Any) -> dict[str, Any]:
        return asdict(progress)

    def _publish_progress(
        self,
        task_id: int,
        stage: str,
        percent: float | None,
        meta: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        normalized = float(percent or 0)
        self.queue.update_progress(
            task_id,
            normalized,
            stage=stage,
            progress_meta=meta,
        )
        self.record_task_event(
            task_id,
            stage,
            normalized,
            message or stage,
            meta=meta,
        )

    def probe_media_file(self, path: str) -> dict[str, Any] | None:
        """Probe a local media file with ffprobe and return serializable info."""
        info = probe_media(path, ffprobe_path=self._runtime_bin("ffprobe"))
        if info is None:
            return None
        return asdict(info)

    @staticmethod
    def _build_session(
        payload: dict[str, Any],
        account: dict[str, Any] | None = None,
        proxy_pool_store: ProxyPoolStore | None = None,
    ):
        from media_session import MediaSession
        from scrape_guard import AdaptiveThrottle, RobotsPolicy

        headers = payload.get("headers")
        proxy = payload.get("proxy")
        cookies = payload.get("cookies")
        if account:
            headers = {**(account.get("headers") or {}), **(headers or {})}
            proxy = account.get("proxy") or proxy
            if account.get("cookies"):
                cookies = (cookies or []) + list(account["cookies"])
            elif account.get("cookies_path"):
                cookies_path = Path(account["cookies_path"])
                if cookies_path.exists():
                    loaded = json.loads(cookies_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, list):
                        cookies = (cookies or []) + loaded
        robots = None
        robots_text = payload.get("robots_text")
        if robots_text:
            robots = RobotsPolicy(user_agent=payload.get("user_agent") or "MediaPipeline/1.0")
            robots.load_text(str(robots_text))
        throttle = None
        if payload.get("adaptive_throttle", False):
            throttle = AdaptiveThrottle(
                base_delay=float(payload.get("throttle_base_delay", 1.0)),
                max_delay=float(payload.get("throttle_max_delay", 60.0)),
            )
        session = MediaSession(
            headers=headers,
            proxy=proxy,
            proxy_pool=MediaPipelineService._resolve_proxy_pool(
                payload.get("proxy_pool"),
                proxy_pool_store,
            ),
            min_interval=float(payload.get("min_interval", 0.0)),
            jitter=float(payload.get("jitter", 0.2)),
            max_retries=int(payload.get("max_retries", 0)),
            backoff_base=float(payload.get("backoff_base", 0.5)),
            backoff_max=float(payload.get("backoff_max", 30.0)),
            robots=robots,
            adaptive_throttle=throttle,
        )
        if cookies:
            session.load_cookies(cookies if isinstance(cookies, list) else [cookies])
        return session

    @staticmethod
    def _resolve_proxy_pool(value: Any, store: ProxyPoolStore | None = None):
        if value is None:
            return None
        if isinstance(value, str):
            if store is None:
                raise ValueError("proxy pool store is not configured")
            pool = store.get(value)
            if pool is None:
                raise ValueError(f"proxy pool not found: {value}")
            return pool
        return ProxyPool.from_config(value)

    @staticmethod
    def _apply_account(
        config: dict[str, Any],
        account: dict[str, Any],
    ) -> dict[str, Any]:
        config = dict(config)
        browser = dict(config.get("browser") or {})
        api = dict(config.get("api") or {})
        if account.get("storage_state"):
            browser["storage_state"] = account["storage_state"]
        if account.get("cookies_path"):
            browser.setdefault("cookies_path", account["cookies_path"])
            api.setdefault("cookies_path", account["cookies_path"])
        if account.get("user_data_dir"):
            browser["user_data_dir"] = account["user_data_dir"]
        if account.get("proxy"):
            browser["proxy"] = account["proxy"]
            api["proxy"] = account["proxy"]
        if account.get("headers"):
            merged_headers = dict(api.get("headers") or {})
            merged_headers.update(account["headers"])
            api["headers"] = merged_headers
        if account.get("login"):
            merged_login = dict(browser.get("login") or {})
            merged_login.update(account["login"])
            browser["login"] = merged_login
        config["browser"] = browser
        config["api"] = api
        return config

    def _notify_task(self, task_id: int) -> None:
        if not self.notifier.enabled_channels():
            return
        task = self.queue.get(task_id)
        if task is None or task.payload.get("notify") is False:
            return
        if task.status not in {"succeeded", "failed", "cancelled"}:
            return
        self.notifier.notify_task(_task_to_dict(task))

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

    def record_task_event(
        self,
        task_id: int,
        stage: str,
        percent: float,
        message: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        with self._events_lock:
            events = self._task_events.setdefault(task_id, [])
            events.append(
                {
                    "stage": stage,
                    "percent": percent,
                    "message": message,
                    "meta": meta,
                    "at": time.time(),
                }
            )
            if len(events) > 200:
                self._task_events[task_id] = events[-200:]
            self._events_lock.notify_all()

    def task_events(self, task_id: int, after: int = 0) -> list[dict[str, Any]]:
        with self._events_lock:
            events = self._task_events.get(task_id, [])
            return list(events[max(0, after) :])

    def wait_for_task_events(
        self,
        task_id: int,
        after: int = 0,
        timeout_s: float = 0.0,
    ) -> list[dict[str, Any]]:
        with self._events_lock:
            events = self._task_events.get(task_id, [])
            if len(events) > after:
                return list(events[max(0, after) :])
            if timeout_s > 0:
                self._events_lock.wait(min(float(timeout_s), 30.0))
                events = self._task_events.get(task_id, [])
            return list(events[max(0, after) :])

    def close(self) -> None:
        self.stop_workers()
        self.queue.close()
        self.accounts.close()
        self.proxy_pools.close()


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
            if path == "/formats":
                self._send_json(200, catalog_payload())
                return
            if path == "/accounts":
                self._send_json(200, {"items": service.accounts.list()})
                return
            if path == "/schedules":
                self._send_json(
                    200,
                    {"items": [asdict(item) for item in service.scheduler.list()]},
                )
                return
            if path == "/proxy-pools":
                self._send_json(200, {"items": service.proxy_pools.list()})
                return
            if path.startswith("/proxy-pools/"):
                name = unquote(path[len("/proxy-pools/") :].rstrip("/"))
                if not name or "/" in name:
                    self._send_json(404, {"error": "not found"})
                    return
                try:
                    self._send_json(200, service.proxy_pools.get_status(name))
                except KeyError:
                    self._send_json(404, {"error": "proxy pool not found"})
                return
            if path == "/notifications/status":
                self._send_json(
                    200,
                    {
                        "channels": service.notifier.enabled_channels(),
                        "config": service.notifier.config,
                    },
                )
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
                if len(parts) == 4 and parts[2].isdigit():
                    task_id = int(parts[2])
                    if parts[3] == "events":
                        after_text = query.get("after", ["0"])[0] or "0"
                        try:
                            after = max(0, int(after_text))
                        except ValueError:
                            after = 0
                        timeout_text = query.get("timeout", ["0"])[0] or "0"
                        try:
                            timeout_s = min(max(float(timeout_text), 0.0), 30.0)
                        except ValueError:
                            timeout_s = 0.0
                        events = service.wait_for_task_events(
                            task_id,
                            after,
                            timeout_s,
                        )
                        self._send_json(200, {"events": events, "next": after + len(events)})
                        return
                    if parts[3] == "progress":
                        task = service.queue.get(task_id)
                        if task is None:
                            self._send_json(404, {"error": "task not found"})
                        else:
                            self._send_json(
                                200,
                                {
                                    "task_id": task.id,
                                    "progress": task.progress,
                                    "stage": task.stage,
                                    "progress_meta": task.progress_meta,
                                    "events": service.task_events(task_id),
                                },
                            )
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
            if path == "/media/probe":
                media_path = data.get("path")
                if not isinstance(media_path, str) or not Path(media_path).is_file():
                    self._send_json(400, {"error": "path must reference a local file"})
                    return
                info = service.probe_media_file(media_path)
                if info is None:
                    self._send_json(404, {"error": "ffprobe unavailable or probe failed"})
                    return
                self._send_json(200, info)
                return
            if path == "/notifications/test":
                sent = service.notifier.send(
                    "Test notification",
                    "Sidecar notification channels are configured.",
                )
                self._send_json(200, {"sent": sent})
                return
            if path == "/proxy-pools":
                name = data.get("name")
                config = data.get("config", data.get("proxies"))
                if not isinstance(name, str) or not name:
                    self._send_json(400, {"error": "proxy pool name is required"})
                    return
                try:
                    self._send_json(200, service.proxy_pools.upsert(name, config))
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                return
            if path == "/accounts":
                try:
                    self._send_json(200, service.accounts.upsert(data))
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                return
            if path.startswith("/accounts/"):
                parts = path.split("/")
                if len(parts) == 4 and parts[3] in ("acquire", "release"):
                    name = unquote(parts[2])
                    if parts[3] == "acquire":
                        profile = service.accounts.acquire(name)
                        if profile is None:
                            self._send_json(409, {"error": "account unavailable"})
                        else:
                            self._send_json(200, profile)
                        return
                    service.accounts.release(
                        name,
                        success=bool(data.get("success", True)),
                        error=data.get("error"),
                    )
                    self._send_json(200, {"ok": True})
                    return
            if path == "/schedules":
                kind = data.get("kind")
                payload = data.get("payload")
                schedule = data.get("schedule")
                if (
                    not isinstance(kind, str)
                    or not isinstance(payload, dict)
                    or not isinstance(schedule, dict)
                ):
                    self._send_json(
                        400,
                        {"error": "kind, payload, and schedule are required"},
                    )
                    return
                try:
                    item = service.scheduler.add(
                        kind,
                        payload,
                        schedule,
                        dedupe_key=data.get("dedupe_key"),
                        priority=int(data.get("priority", 0)),
                        max_attempts=(
                            int(data["max_attempts"])
                            if data.get("max_attempts") is not None
                            else None
                        ),
                        start_after_seconds=float(data.get("start_after_seconds", 0.0)),
                    )
                except (TypeError, ValueError) as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                self._send_json(200, asdict(item))
                return
            if path.startswith("/schedules/"):
                parts = path.split("/")
                if len(parts) == 4 and parts[2].isdigit() and parts[3] in ("pause", "resume"):
                    schedule_id = int(parts[2])
                    if parts[3] == "pause":
                        service.scheduler.pause(schedule_id)
                    else:
                        service.scheduler.resume(schedule_id)
                    self._send_json(200, {"ok": True})
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
                run_after = None
                if data.get("run_after_seconds") is not None:
                    try:
                        run_after = (
                            datetime.now(timezone.utc)
                            + timedelta(seconds=float(data["run_after_seconds"]))
                        ).isoformat()
                    except (TypeError, ValueError):
                        self._send_json(400, {"error": "run_after_seconds must be a number"})
                        return
                task = service.queue.enqueue(
                    kind=kind,
                    payload=payload,
                    dedupe_key=dedupe_key,
                    priority=priority,
                    max_attempts=max_attempts,
                    resume_token=resume_token,
                    run_after=run_after,
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

        def do_DELETE(self) -> None:
            if not self._authorized():
                return
            path = urlparse(self.path).path
            if path.startswith("/schedules/"):
                parts = path.split("/")
                if len(parts) == 3 and parts[2].isdigit():
                    removed = service.scheduler.remove(int(parts[2]))
                    self._send_json(200, {"ok": removed})
                    return
            if path.startswith("/accounts/"):
                name = unquote(path[len("/accounts/") :].rstrip("/"))
                if name and "/" not in name:
                    removed = service.accounts.remove(name)
                    self._send_json(200, {"ok": removed})
                    return
            if path.startswith("/proxy-pools/"):
                name = unquote(path[len("/proxy-pools/") :].rstrip("/"))
                if name and "/" not in name:
                    removed = service.proxy_pools.remove(name)
                    self._send_json(200, {"ok": removed})
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
    accounts_path: str | Path | None = None,
    proxy_pools_path: str | Path | None = None,
    notifications: dict[str, Any] | None = None,
) -> MediaHTTPServer:
    service = MediaPipelineService(
        db_path,
        runtime_dir=runtime_dir,
        workers=workers,
        token=token,
        accounts_path=accounts_path,
        proxy_pools_path=proxy_pools_path,
        notifications=notifications,
    )
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
    parser.add_argument("--accounts", default=None, help="JSON file for account profiles")
    parser.add_argument("--proxy-pools", default=None, help="JSON file for named proxy pools")
    parser.add_argument(
        "--notify-config",
        default=None,
        help="JSON file with desktop/email/webhook notification config",
    )
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
    notifications = None
    if args.notify_config:
        notifications = json.loads(Path(args.notify_config).read_text(encoding="utf-8"))
    server = run_service(
        db,
        host=args.host,
        port=args.port,
        workers=args.workers,
        runtime_dir=args.runtime_dir,
        token=args.token,
        accounts_path=args.accounts,
        proxy_pools_path=args.proxy_pools,
        notifications=notifications,
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
