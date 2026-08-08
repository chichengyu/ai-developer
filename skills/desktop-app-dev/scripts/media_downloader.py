"""Chunked, resumable, concurrent downloader for the media pipeline.

Uses HTTP Range requests with one `.part` file per chunk and a JSON
checkpoint next to the destination file. Re-running with `resume=True`
skips finished chunks and restarts incomplete chunks from their current
byte offset.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from media_session import MediaSession

DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
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


@dataclass
class DownloadResult:
    path: Path
    total_size: int | None
    chunks_downloaded: int
    resumed: bool


class _DownloadState:
    def __init__(self, total: int | None) -> None:
        self.total = total
        self.downloaded = 0
        self.lock = threading.Lock()
        self.last_report = 0.0

    def add(
        self,
        amount: int,
        task_id: int | str | None,
        stage: str,
        callback: Callable[[DownloadProgress], None] | None,
    ) -> None:
        with self.lock:
            self.downloaded += amount
            now = time.monotonic()
            if callback is None or now - self.last_report < _PROGRESS_INTERVAL:
                return
            self.last_report = now
            total = self.total or 0
            percent = (self.downloaded / total) if total else None
            speed = self.downloaded / max(now - self._started, 0.001)
            callback(
                DownloadProgress(
                    task_id=task_id,
                    stage=stage,
                    downloaded=self.downloaded,
                    total=self.total,
                    percent=percent,
                    speed=speed,
                    phase="download",
                )
            )

    def start_timer(self) -> None:
        self._started = time.monotonic()


def _part_path(dest: Path, index: int) -> Path:
    return dest.with_name(f"{dest.name}.part.{index:05d}")


def _checkpoint_path(dest: Path) -> Path:
    return dest.with_name(f"{dest.name}.chunks.json")


def _load_chunk_map(dest: Path, total_size: int) -> dict | None:
    checkpoint = _checkpoint_path(dest)
    if not checkpoint.exists():
        return None
    try:
        data = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("total_size") != total_size:
        return None
    return data


def _build_chunk_map(total_size: int, chunk_size: int) -> dict:
    chunks: list[dict] = []
    start = 0
    index = 0
    while start < total_size:
        end = min(start + chunk_size - 1, total_size - 1)
        chunks.append({"index": index, "start": start, "end": end, "done": False})
        start = end + 1
        index += 1
    return {"total_size": total_size, "chunks": chunks}


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
            out.write(chunk)
            downloaded += len(chunk)
            state.add(len(chunk), task_id, "single", progress)
    os.replace(tmp, dest)
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
) -> None:
    part = _part_path(dest, int(chunk["index"]))
    expected = int(chunk["end"]) - int(chunk["start"]) + 1
    if part.exists() and part.stat().st_size == expected:
        chunk["done"] = True
        state.add(expected, task_id, "resume-skip", progress)
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
            data = response.read(1024 * 1024)
            if not data:
                break
            out.write(data)
            state.add(len(data), task_id, "chunk", progress)
    if part.stat().st_size != expected:
        raise RuntimeError(f"chunk {chunk['index']} incomplete: {part.stat().st_size}/{expected}")
    chunk["done"] = True


def _merge_chunks(dest: Path, chunk_map: dict) -> None:
    tmp = dest.with_name(f"{dest.name}.tmp")
    with tmp.open("wb") as out:
        for chunk in chunk_map["chunks"]:
            part = _part_path(dest, int(chunk["index"]))
            with part.open("rb") as source:
                shutil.copyfileobj(source, out, 1024 * 1024)
    os.replace(tmp, dest)
    for chunk in chunk_map["chunks"]:
        part = _part_path(dest, int(chunk["index"]))
        if part.exists():
            part.unlink()
    checkpoint = _checkpoint_path(dest)
    if checkpoint.exists():
        checkpoint.unlink()


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
) -> DownloadResult:
    """Download a file with Range chunks, concurrency, and resume."""
    session = session or MediaSession()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    probe = session.head(url, headers=headers)
    total_size = probe.total_size
    state = _DownloadState(total_size)
    state.start_timer()

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
        return DownloadResult(
            path=dest,
            total_size=downloaded,
            chunks_downloaded=1,
            resumed=False,
        )

    chunk_map = _load_chunk_map(dest, total_size) if resume else None
    if chunk_map is None:
        chunk_map = _build_chunk_map(total_size, chunk_size)
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

    if concurrency <= 1 or len(pending) == 0:
        for chunk in pending:
            run_chunk(chunk)
            _write_checkpoint(dest, chunk_map)
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(run_chunk, chunk): chunk for chunk in pending}
            for future in as_completed(futures):
                future.result()
                _write_checkpoint(dest, chunk_map)

    if progress:
        progress(
            DownloadProgress(
                task_id=task_id,
                stage="merge",
                downloaded=total_size,
                total=total_size,
                percent=1.0,
                speed=0.0,
                phase="merge",
            )
        )
    _merge_chunks(dest, chunk_map)
    return DownloadResult(
        path=dest,
        total_size=total_size,
        chunks_downloaded=len(chunk_map["chunks"]),
        resumed=True,
    )


if __name__ == "__main__":
    print(
        "desktop-app-dev media_downloader: import download_file() / safe_output_name() for downloads."
    )
