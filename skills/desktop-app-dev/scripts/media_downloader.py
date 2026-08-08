"""Chunked, resumable, concurrent downloader for the media pipeline.

Uses HTTP Range requests with one `.part` file per chunk and a JSON
checkpoint next to the destination file. Re-running with `resume=True`
skips finished chunks and restarts incomplete chunks from their current
byte offset.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from media_session import MediaProbe, MediaSession, guess_filename

DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
DEFAULT_AUTO_MIN_CHUNK_SIZE = 256 * 1024
DEFAULT_TARGET_CHUNKS_PER_CONNECTION = 4
_PROGRESS_INTERVAL = 0.5

_RESERVED_WINDOWS_BASENAMES = (
    {
        "con",
        "prn",
        "aux",
        "nul",
    }
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def safe_output_name(name: str, default: str = "output.mp4") -> str:
    """Return a filesystem-safe basename for a URL-derived file name."""
    candidate = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if candidate in ("", ".", ".."):
        return default
    candidate = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", candidate).rstrip(" .")
    stem = candidate.rsplit(".", 1)[0].lower() if "." in candidate else candidate.lower()
    if stem in _RESERVED_WINDOWS_BASENAMES:
        candidate = "_" + candidate
    return candidate or default


class DownloadCancelled(Exception):
    """Raised when the user cancels a download."""


class DownloadHashError(RuntimeError):
    """Raised when the final SHA-256 does not match the expected digest."""


class _ChunkRestart(Exception):
    """Internal signal: a slow shard should restart from its current offset."""


class CancelToken:
    """Thread-safe cancellation flag."""

    def __init__(self) -> None:
        self._flag = False
        self._lock = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            self._flag = True

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._flag


@dataclass
class DownloadProgress:
    task_id: int | str | None
    stage: str
    downloaded: int
    total: int | None
    percent: float | None
    speed: float
    phase: str
    speed_avg: float = 0.0
    eta_s: float | None = None
    chunks_done: int | None = None
    chunks_total: int | None = None
    merge_done: int | None = None
    merge_total: int | None = None
    elapsed_s: float = 0.0


@dataclass
class DownloadResult:
    path: Path
    total_size: int | None
    chunks_downloaded: int
    resumed: bool
    elapsed_s: float = 0.0
    average_speed: float = 0.0
    chunks_total: int | None = None
    content_type: str | None = None
    filename: str | None = None


@dataclass
class BatchDownloadProgress:
    task_id: int | str | None
    stage: str
    percent: float | None
    done: int
    total: int
    downloaded_bytes: int
    total_bytes: int | None
    speed: float
    eta_s: float | None
    current: str | None = None
    elapsed_s: float = 0.0


@dataclass
class BatchDownloadResult:
    paths: list[Path]
    total_bytes: int | None
    downloaded_bytes: int
    elapsed_s: float
    average_speed: float


class SpeedTracker:
    """Sliding-window throughput tracker shared by adaptive workers."""

    def __init__(self, window_seconds: float = 3.0) -> None:
        self.window_seconds = window_seconds
        self._samples: list[tuple[float, int]] = []
        self._lock = threading.Lock()

    def add(self, amount: int, now: float | None = None) -> None:
        with self._lock:
            now = now if now is not None else time.monotonic()
            self._samples.append((now, amount))
            cutoff = now - self.window_seconds
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.pop(0)

    def speed(self, now: float | None = None) -> float:
        with self._lock:
            now = now if now is not None else time.monotonic()
            cutoff = now - self.window_seconds
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.pop(0)
            if not self._samples:
                return 0.0
            total = sum(amount for _, amount in self._samples)
            span = now - self._samples[0][0]
            return total / span if span > 0 else 0.0


class SpeedLimiter:
    """Shared leaky-bucket throttle for total download throughput."""

    def __init__(self, max_bytes_per_sec: float | None) -> None:
        self.max_bytes_per_sec = max(0.0, float(max_bytes_per_sec or 0.0))
        self._lock = threading.Lock()
        self._ready_at = time.monotonic()

    def wait(self, amount: int) -> None:
        if self.max_bytes_per_sec <= 0 or amount <= 0:
            return
        with self._lock:
            now = time.monotonic()
            self._ready_at = max(self._ready_at, now)
            self._ready_at += amount / self.max_bytes_per_sec
            target = self._ready_at
        while True:
            now = time.monotonic()
            if now >= target:
                return
            time.sleep(min(target - now, 0.1))


@dataclass
class _ChunkState:
    started: float = field(default_factory=time.monotonic)
    last_progress: float = field(default_factory=time.monotonic)
    speed_tracker: SpeedTracker = field(default_factory=SpeedTracker)

    def on_bytes(self, amount: int) -> None:
        now = time.monotonic()
        self.speed_tracker.add(amount, now)
        self.last_progress = now


@dataclass
class _ChunkRun:
    chunk: dict
    token: CancelToken | None
    state: _ChunkState


class _DownloadState:
    def __init__(
        self,
        total: int | None,
        chunks_total: int | None = None,
        max_speed_bytes_per_sec: float | None = None,
    ) -> None:
        self.total = total
        self.downloaded = 0
        self.chunks_total = chunks_total
        self.chunks_done = 0
        self.lock = threading.Lock()
        self.last_report = 0.0
        self.speed_tracker = SpeedTracker()
        self.speed_limiter = SpeedLimiter(max_speed_bytes_per_sec)
        self._started = time.monotonic()

    def wait(self, amount: int) -> None:
        self.speed_limiter.wait(amount)

    def _snapshot(
        self,
        task_id: int | str | None,
        stage: str,
        phase: str,
        now: float,
    ) -> DownloadProgress:
        total = self.total or 0
        percent = (self.downloaded / total) if total else None
        speed = self.downloaded / max(now - self._started, 0.001)
        speed_avg = self.speed_tracker.speed(now)
        remaining = (self.total or 0) - self.downloaded
        eta_s = remaining / speed_avg if self.total and speed_avg > 0 else None
        return DownloadProgress(
            task_id=task_id,
            stage=stage,
            downloaded=self.downloaded,
            total=self.total,
            percent=percent,
            speed=speed,
            phase=phase,
            speed_avg=speed_avg,
            eta_s=eta_s,
            chunks_done=self.chunks_done,
            chunks_total=self.chunks_total,
            elapsed_s=now - self._started,
        )

    def add(
        self,
        amount: int,
        task_id: int | str | None,
        stage: str,
        callback: Callable[[DownloadProgress], None] | None,
        *,
        chunk_done: bool = False,
    ) -> None:
        with self.lock:
            self.downloaded += amount
            if chunk_done:
                self.chunks_done += 1
            now = time.monotonic()
            self.speed_tracker.add(amount, now)
            if callback is None or now - self.last_report < _PROGRESS_INTERVAL:
                return
            self.last_report = now
            callback(self._snapshot(task_id, stage, "download", now))

    def chunk_done(
        self,
        task_id: int | str | None,
        stage: str,
        callback: Callable[[DownloadProgress], None] | None,
    ) -> None:
        with self.lock:
            self.chunks_done += 1
            now = time.monotonic()
            if callback is None or now - self.last_report < _PROGRESS_INTERVAL:
                return
            self.last_report = now
            callback(self._snapshot(task_id, stage, "chunk", now))

    def report(
        self,
        task_id: int | str | None,
        stage: str,
        callback: Callable[[DownloadProgress], None] | None,
        phase: str = "probe",
    ) -> None:
        if callback is None:
            return
        with self.lock:
            self.last_report = time.monotonic()
            callback(self._snapshot(task_id, stage, phase, self.last_report))

    def start_timer(self) -> None:
        self._started = time.monotonic()

    def elapsed(self) -> float:
        return max(time.monotonic() - self._started, 0.0)


def _part_path(dest: Path, index: int) -> Path:
    return dest.with_name(f"{dest.name}.part.{index:05d}")


def _checkpoint_path(dest: Path) -> Path:
    return dest.with_name(f"{dest.name}.chunks.json")


def _load_chunk_map(
    dest: Path,
    total_size: int,
    entity_tag: str | None = None,
    last_modified: str | None = None,
) -> dict | None:
    checkpoint = _checkpoint_path(dest)
    if not checkpoint.exists():
        return None
    try:
        data = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("total_size") != total_size:
        return None
    if entity_tag is not None and data.get("entity_tag") != entity_tag:
        return None
    if last_modified is not None and data.get("last_modified") != last_modified:
        return None
    return data


def _build_chunk_map(
    total_size: int,
    chunk_size: int,
    entity_tag: str | None = None,
    last_modified: str | None = None,
) -> dict:
    chunks: list[dict] = []
    start = 0
    index = 0
    while start < total_size:
        end = min(start + chunk_size - 1, total_size - 1)
        chunks.append({"index": index, "start": start, "end": end, "done": False})
        start = end + 1
        index += 1
    return {
        "total_size": total_size,
        "chunks": chunks,
        "entity_tag": entity_tag,
        "last_modified": last_modified,
    }


def _write_checkpoint(dest: Path, chunk_map: dict) -> None:
    checkpoint = _checkpoint_path(dest)
    tmp = checkpoint.with_suffix(".tmp")
    tmp.write_text(json.dumps(chunk_map, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, checkpoint)


def _download_single(
    session: MediaSession,
    url: str,
    dest: Path,
    headers: dict[str, str] | None,
    task_id: int | str | None,
    state: _DownloadState,
    progress: Callable[[DownloadProgress], None] | None,
    cancel: CancelToken | None,
) -> int:
    tmp = dest.with_name(f"{dest.name}.tmp")
    downloaded = 0
    with session.open(url, headers=headers) as response, tmp.open("wb") as out:
        while True:
            if cancel and cancel.cancelled:
                raise DownloadCancelled()
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            state.wait(len(chunk))
            out.write(chunk)
            downloaded += len(chunk)
            state.add(len(chunk), task_id, "single", progress)
    os.replace(tmp, dest)
    state.chunk_done(task_id, "download", progress)
    state.report(task_id, "download", progress, phase="download")
    return downloaded


def _download_chunk(
    session: MediaSession,
    url: str,
    dest: Path,
    chunk: dict,
    headers: dict[str, str] | None,
    task_id: int | str | None,
    state: _DownloadState,
    progress: Callable[[DownloadProgress], None] | None,
    cancel: CancelToken | None,
    chunk_token: CancelToken | None = None,
    chunk_state: _ChunkState | None = None,
) -> None:
    part = _part_path(dest, int(chunk["index"]))
    expected = int(chunk["end"]) - int(chunk["start"]) + 1
    if part.exists() and part.stat().st_size == expected:
        chunk["done"] = True
        state.add(expected, task_id, "resume-skip", progress, chunk_done=True)
        return

    start = int(chunk["start"])
    mode = "wb"
    if part.exists() and 0 < part.stat().st_size < expected:
        start += part.stat().st_size
        mode = "ab"

    range_header = f"bytes={start}-{int(chunk['end'])}"
    merged_headers = dict(headers or {})
    merged_headers["Range"] = range_header
    with session.open(url, headers=merged_headers) as response, part.open(mode) as out:
        while True:
            if cancel and cancel.cancelled:
                raise DownloadCancelled()
            if chunk_token and chunk_token.cancelled:
                raise _ChunkRestart()
            data = response.read(1024 * 1024)
            if not data:
                break
            state.wait(len(data))
            out.write(data)
            state.add(len(data), task_id, "chunk", progress)
            if chunk_state:
                chunk_state.on_bytes(len(data))
    if part.stat().st_size != expected:
        raise RuntimeError(f"chunk {chunk['index']} incomplete: {part.stat().st_size}/{expected}")
    chunk["done"] = True
    state.chunk_done(task_id, "chunk", progress)


def _tune_concurrency(
    previous_speed: float,
    current_speed: float,
    workers: int,
    max_workers: int,
    error_burst: bool = False,
) -> int:
    """AIMD-style worker tuning: grow when adding workers helps, shrink on loss."""
    if error_burst:
        return max(1, workers - 1)
    if previous_speed <= 0 or current_speed <= 0:
        return workers
    ratio = current_speed / previous_speed
    if ratio >= 1.08 and workers < max_workers:
        return workers + 1
    if ratio <= 0.85:
        return max(1, workers - 1)
    return workers


def _probe_range(
    session: MediaSession,
    url: str,
    headers: dict[str, str] | None,
) -> MediaProbe | None:
    """Fall back to a 1-byte Range GET when HEAD hides the file size."""
    probe_headers = dict(headers or {})
    probe_headers["Range"] = "bytes=0-0"
    try:
        _, status, response_headers = session.get_bytes_with_meta(
            url,
            headers=probe_headers,
        )
    except Exception:
        return None
    content_range = response_headers.get("Content-Range", "")
    match = re.match(r"bytes\s+\d+-\d+/(\d+)", content_range)
    if status != 206 or not match or int(match.group(1)) <= 0:
        return None
    return MediaProbe(
        url=url,
        status=status,
        total_size=int(match.group(1)),
        accept_ranges=True,
        content_type=response_headers.get("Content-Type"),
        filename=guess_filename(url, response_headers.get("Content-Disposition")),
        headers=response_headers,
        content_range=content_range,
    )


def _effective_chunk_size(total_size: int, chunk_size: int, concurrency: int) -> int:
    """Split small files into enough shards to use every connection."""
    target_chunks = max(1, concurrency) * DEFAULT_TARGET_CHUNKS_PER_CONNECTION
    suggested = math.ceil(total_size / target_chunks)
    return max(DEFAULT_AUTO_MIN_CHUNK_SIZE, min(chunk_size, suggested))


def _run_chunks_adaptive(
    session: MediaSession,
    url: str,
    dest: Path,
    pending: list[dict],
    chunk_map: dict,
    headers: dict[str, str] | None,
    task_id: int | str | None,
    state: _DownloadState,
    progress: Callable[[DownloadProgress], None] | None,
    cancel: CancelToken | None,
    max_workers: int,
    chunk_retries: int,
    slow_after_seconds: float,
    slow_idle_seconds: float,
    slow_restart_limit: int,
    tune_interval: float,
) -> None:
    pending = list(pending)
    active: dict[Future[None], _ChunkRun] = {}
    forced: set[int] = set()
    workers = max(1, min(max_workers, len(pending)))
    last_tune = time.monotonic()
    previous_speed = 0.0
    errors_since_tune = 0

    def run_chunk(
        chunk: dict,
        chunk_state: _ChunkState,
        chunk_token: CancelToken | None,
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(max(1, chunk_retries)):
            if cancel and cancel.cancelled:
                raise DownloadCancelled()
            try:
                _download_chunk(
                    session,
                    url,
                    dest,
                    chunk,
                    headers,
                    task_id,
                    state,
                    progress,
                    cancel,
                    chunk_token=chunk_token,
                    chunk_state=chunk_state,
                )
                return
            except DownloadCancelled:
                raise
            except _ChunkRestart:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < max(1, chunk_retries) - 1:
                    time.sleep(min(2**attempt, 8))
        assert last_error is not None
        raise last_error

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while pending or active:
            now = time.monotonic()
            if now - last_tune >= tune_interval:
                current_speed = state.speed_tracker.speed(now)
                workers = _tune_concurrency(
                    previous_speed,
                    current_speed,
                    workers,
                    max_workers,
                    errors_since_tune > 0,
                )
                previous_speed = current_speed
                last_tune = now
                errors_since_tune = 0

            if slow_after_seconds > 0:
                global_speed = state.speed_tracker.speed(now)
                for run in list(active.values()):
                    if run.token is None or int(run.chunk.get("index", -1)) in forced:
                        continue
                    stalled = now - run.state.started >= slow_after_seconds
                    idle = now - run.state.last_progress >= slow_idle_seconds
                    if stalled and idle:
                        run_speed = run.state.speed_tracker.speed(now)
                        if run_speed < max(1.0, global_speed * 0.15):
                            run.token.cancel()

            while len(active) < workers and pending:
                chunk = pending.pop(0)
                chunk_state = _ChunkState()
                chunk_token = CancelToken()
                future = pool.submit(run_chunk, chunk, chunk_state, chunk_token)
                active[future] = _ChunkRun(
                    chunk=chunk,
                    token=chunk_token,
                    state=chunk_state,
                )

            if not active:
                break
            done, _ = wait(active, timeout=0.2, return_when=FIRST_COMPLETED)
            for future in done:
                run = active.pop(future)
                try:
                    future.result()
                except _ChunkRestart:
                    errors_since_tune += 1
                    chunk = run.chunk
                    if int(chunk.get("slow_restarts", 0)) < slow_restart_limit:
                        chunk["slow_restarts"] = int(chunk.get("slow_restarts", 0)) + 1
                    else:
                        forced.add(int(chunk["index"]))
                    pending.append(chunk)
                except DownloadCancelled:
                    raise
                except Exception:
                    errors_since_tune += 1
                    raise
                else:
                    _write_checkpoint(dest, chunk_map)


def _merge_chunks(
    dest: Path,
    chunk_map: dict,
    task_id: int | str | None = None,
    state: _DownloadState | None = None,
    progress: Callable[[DownloadProgress], None] | None = None,
) -> None:
    tmp = dest.with_name(f"{dest.name}.tmp")
    merge_total = 0
    for chunk in chunk_map["chunks"]:
        part = _part_path(dest, int(chunk["index"]))
        if part.exists():
            merge_total += part.stat().st_size
    merge_done = 0
    with tmp.open("wb") as out:
        for chunk in chunk_map["chunks"]:
            part = _part_path(dest, int(chunk["index"]))
            with part.open("rb") as source:
                shutil.copyfileobj(source, out, 1024 * 1024)
                merge_done += part.stat().st_size
                if progress:
                    downloaded = state.downloaded if state else merge_done
                    total = state.total if state else merge_total
                    percent = (downloaded / total) if total else 1.0
                    progress(
                        DownloadProgress(
                            task_id=task_id,
                            stage="merge",
                            downloaded=downloaded,
                            total=total,
                            percent=percent,
                            speed=0.0,
                            phase="merge",
                            chunks_done=state.chunks_done if state else None,
                            chunks_total=state.chunks_total if state else None,
                            merge_done=merge_done,
                            merge_total=merge_total,
                            elapsed_s=state.elapsed() if state else 0.0,
                        )
                    )
    os.replace(tmp, dest)
    for chunk in chunk_map["chunks"]:
        part = _part_path(dest, int(chunk["index"]))
        if part.exists():
            part.unlink()
    checkpoint = _checkpoint_path(dest)
    if checkpoint.exists():
        checkpoint.unlink()


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    url: str,
    dest: str | Path,
    session: MediaSession | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    concurrency: int = 4,
    chunk_retries: int = 3,
    resume: bool = True,
    progress: Callable[[DownloadProgress], None] | None = None,
    cancel: CancelToken | None = None,
    task_id: int | str | None = None,
    headers: dict[str, str] | None = None,
    *,
    auto_chunk_sizing: bool = True,
    max_speed_bytes_per_sec: float | None = None,
    adaptive_concurrency: bool = True,
    slow_shard_switch: bool = True,
    slow_after_seconds: float = 8.0,
    slow_idle_seconds: float = 2.0,
    slow_restart_limit: int = 3,
    tune_interval: float = 1.0,
    expected_sha256: str | None = None,
) -> DownloadResult:
    """Download a file with Range chunks, concurrency, and resume."""
    session = session or MediaSession()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    probe = session.head(url, headers=headers)
    if not probe.supports_resume:
        fallback = _probe_range(session, url, headers)
        if fallback is not None:
            probe = fallback
    total_size = probe.total_size
    entity_tag = probe.headers.get("ETag")
    last_modified = probe.headers.get("Last-Modified")
    state = _DownloadState(
        total_size,
        chunks_total=1,
        max_speed_bytes_per_sec=max_speed_bytes_per_sec,
    )
    state.start_timer()
    state.report(task_id, "probe", progress, phase="probe")

    if not probe.supports_resume or total_size is None:
        downloaded = _download_single(
            session,
            url,
            dest,
            headers,
            task_id,
            state,
            progress,
            cancel,
        )
        if expected_sha256:
            state.report(task_id, "verify", progress, phase="verify")
            actual = _sha256_file(dest)
            if actual.lower() != expected_sha256.lower():
                raise DownloadHashError(
                    f"sha256 mismatch: expected {expected_sha256}, got {actual}"
                )
        elapsed = state.elapsed()
        return DownloadResult(
            path=dest,
            total_size=downloaded,
            chunks_downloaded=1,
            resumed=False,
            elapsed_s=elapsed,
            average_speed=downloaded / elapsed if elapsed > 0 else 0.0,
            chunks_total=1,
            content_type=probe.content_type,
            filename=probe.filename,
        )

    if auto_chunk_sizing and chunk_size == DEFAULT_CHUNK_SIZE:
        chunk_size = _effective_chunk_size(total_size, chunk_size, concurrency)
    chunk_map = _load_chunk_map(dest, total_size, entity_tag, last_modified) if resume else None
    if chunk_map is None:
        chunk_map = _build_chunk_map(total_size, chunk_size, entity_tag, last_modified)
    state = _DownloadState(
        total_size,
        chunks_total=len(chunk_map["chunks"]),
        max_speed_bytes_per_sec=max_speed_bytes_per_sec,
    )
    state.start_timer()
    state.report(task_id, "probe", progress, phase="probe")
    pending = [chunk for chunk in chunk_map["chunks"] if not chunk.get("done")]

    def run_chunk(chunk: dict) -> None:
        last_error: Exception | None = None
        for attempt in range(max(1, chunk_retries)):
            if cancel and cancel.cancelled:
                raise DownloadCancelled()
            try:
                _download_chunk(
                    session,
                    url,
                    dest,
                    chunk,
                    headers,
                    task_id,
                    state,
                    progress,
                    cancel,
                )
                return
            except DownloadCancelled:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < max(1, chunk_retries) - 1:
                    time.sleep(min(2**attempt, 8))
        assert last_error is not None
        raise last_error

    slow_after = slow_after_seconds if slow_shard_switch else 0.0
    if adaptive_concurrency and concurrency > 1 and len(pending) > 0:
        _run_chunks_adaptive(
            session,
            url,
            dest,
            pending,
            chunk_map,
            headers,
            task_id,
            state,
            progress,
            cancel,
            concurrency,
            chunk_retries,
            slow_after,
            slow_idle_seconds,
            slow_restart_limit,
            tune_interval,
        )
    elif concurrency <= 1 or len(pending) == 0:
        for chunk in pending:
            run_chunk(chunk)
            _write_checkpoint(dest, chunk_map)
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(run_chunk, chunk): chunk for chunk in pending}
            for future in as_completed(futures):
                future.result()
                _write_checkpoint(dest, chunk_map)

    _merge_chunks(
        dest,
        chunk_map,
        task_id=task_id,
        state=state,
        progress=progress,
    )
    if total_size is not None and dest.exists() and dest.stat().st_size != total_size:
        raise RuntimeError(f"downloaded size mismatch: {dest.stat().st_size}/{total_size}")
    if expected_sha256:
        state.report(task_id, "verify", progress, phase="verify")
        actual = _sha256_file(dest)
        if actual.lower() != expected_sha256.lower():
            raise DownloadHashError(f"sha256 mismatch: expected {expected_sha256}, got {actual}")
    elapsed = state.elapsed()
    if progress:
        progress(
            DownloadProgress(
                task_id=task_id,
                stage="done",
                downloaded=total_size,
                total=total_size,
                percent=1.0,
                speed=total_size / elapsed if elapsed > 0 else 0.0,
                phase="done",
                speed_avg=state.speed_tracker.speed(),
                eta_s=0.0,
                chunks_done=state.chunks_done,
                chunks_total=state.chunks_total,
                merge_done=total_size,
                merge_total=total_size,
                elapsed_s=elapsed,
            )
        )
    return DownloadResult(
        path=dest,
        total_size=total_size,
        chunks_downloaded=len(chunk_map["chunks"]),
        resumed=True,
        elapsed_s=elapsed,
        average_speed=total_size / elapsed if elapsed > 0 else 0.0,
        chunks_total=len(chunk_map["chunks"]),
        content_type=probe.content_type,
        filename=probe.filename,
    )


def download_batch(
    urls: list[str],
    dest_dir: str | Path,
    session: MediaSession | None = None,
    progress: Callable[[BatchDownloadProgress], None] | None = None,
    cancel: CancelToken | None = None,
    task_id: int | str | None = None,
    headers: dict[str, str] | None = None,
    **download_kwargs: Any,
) -> BatchDownloadResult:
    """Download multiple files with aggregate bytes, speed, and ETA."""
    session = session or MediaSession()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    probes = [session.head(url, headers=headers) for url in urls]
    total_bytes = sum(probe.total_size or 0 for probe in probes)
    total_known = all(probe.total_size is not None for probe in probes)
    start = time.monotonic()
    downloaded_bytes = 0
    results: list[DownloadResult] = []
    used_names: set[str] = set()

    def emit(
        stage: str,
        percent: float | None,
        done: int,
        current: str | None = None,
    ) -> None:
        if progress is None:
            return
        elapsed = time.monotonic() - start
        speed = downloaded_bytes / elapsed if elapsed > 0 else 0.0
        remaining = (total_bytes - downloaded_bytes) if total_known else None
        eta_s = remaining / speed if remaining is not None and speed > 0 else None
        if percent is None and total_known and total_bytes > 0:
            percent = downloaded_bytes / total_bytes
        progress(
            BatchDownloadProgress(
                task_id=task_id,
                stage=stage,
                percent=percent,
                done=done,
                total=len(urls),
                downloaded_bytes=downloaded_bytes,
                total_bytes=total_bytes if total_known else None,
                speed=speed,
                eta_s=eta_s,
                current=current,
                elapsed_s=elapsed,
            )
        )

    emit("preflight", 0.0, 0)
    for index, (url, probe) in enumerate(zip(urls, probes, strict=False)):
        if cancel and cancel.cancelled:
            raise DownloadCancelled()
        name = probe.filename or safe_output_name(url, f"download_{index + 1}.bin")
        name = safe_output_name(name, f"download_{index + 1}.bin")
        stem = Path(name).stem
        suffix = Path(name).suffix or ".bin"
        candidate = dest_dir / name
        while candidate.name.lower() in used_names:
            candidate = dest_dir / f"{stem}_{len(used_names)}{suffix}"
        used_names.add(candidate.name.lower())
        size = probe.total_size or 0
        done_base = downloaded_bytes

        def on_child(
            event: DownloadProgress,
            done_base: int = done_base,
            size: int = size,
            index: int = index,
            current_name: str = candidate.name,
        ) -> None:
            nonlocal downloaded_bytes
            fraction = event.percent if event.percent is not None else 0.0
            downloaded_bytes = done_base + int(fraction * size)
            emit(event.stage, None, index, current=current_name)

        result = download_file(
            url,
            candidate,
            session=session,
            headers=headers,
            task_id=task_id,
            cancel=cancel,
            progress=on_child,
            **download_kwargs,
        )
        results.append(result)
        downloaded_bytes = done_base + (result.total_size or result.path.stat().st_size)
        percent = (downloaded_bytes / total_bytes) if total_known and total_bytes > 0 else None
        emit("done", percent, index + 1, current=candidate.name)
    elapsed = time.monotonic() - start
    return BatchDownloadResult(
        paths=[result.path for result in results],
        total_bytes=total_bytes if total_known else None,
        downloaded_bytes=downloaded_bytes,
        elapsed_s=elapsed,
        average_speed=downloaded_bytes / elapsed if elapsed > 0 else 0.0,
    )


if __name__ == "__main__":
    print(
        "desktop-app-dev media_downloader: import download_file() / safe_output_name() for downloads."
    )
