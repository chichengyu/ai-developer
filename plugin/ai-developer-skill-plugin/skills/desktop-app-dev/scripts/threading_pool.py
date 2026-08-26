"""Bounded, cancellable worker pool for desktop apps.

This is the runtime-safe core behind the skill's concurrency templates.
It keeps every pool bounded by ``max_workers``, reports aggregate progress,
supports per-item retry, and propagates cancellation to pending and running
jobs. UI code must still marshal callbacks through the framework bridge
(``root.after``, Qt signals, Dispatcher, etc.); this module never touches
widgets.

Usage:
    pool = WorkerPool(
        job=download_one,
        max_workers=4,
        retry=RetryPolicy(max_attempts=3, delay_seconds=0.2),
        on_progress=lambda p: root.after(0, status.set, f"{p.percent:.0%}"),
        on_done=lambda items: root.after(0, finish_ui, items),
    )
    pool.submit_many(urls)
    pool.start()
    # later: pool.cancel(); pool.wait(timeout=5)
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class Cancelled(Exception):
    """Raised inside a job when the pool cancellation event is set."""


def check_cancel(event: threading.Event, every: int = 16) -> None:
    """Cheap cooperative cancel check for CPU loops and long jobs."""
    if every <= 0 or event.is_set():
        raise Cancelled()


@dataclass(frozen=True)
class BatchProgress:
    """Aggregate progress snapshot shared with UI callbacks."""

    completed: int
    total: int
    succeeded: int
    failed: int

    @property
    def percent(self) -> float:
        return self.completed / self.total if self.total else 1.0


@dataclass
class BatchItem(Generic[T]):
    """One pool task and its outcome."""

    index: int
    payload: Any
    result: T | None = None
    error: Exception | None = None
    attempts: int = 0
    status: str = "queued"


@dataclass
class RetryPolicy:
    """Retry policy for a pool task.

    ``retry_on`` may be one exception type or a tuple of types; when ``None``,
    every exception is retried up to ``max_attempts``.
    """

    max_attempts: int = 1
    delay_seconds: float = 0.0
    backoff: float = 1.0
    max_delay_seconds: float = 30.0
    retry_on: type[Exception] | tuple[type[Exception], ...] | None = None

    def __post_init__(self) -> None:
        self.max_attempts = max(1, int(self.max_attempts))
        self.delay_seconds = max(0.0, float(self.delay_seconds))
        self.backoff = max(1.0, float(self.backoff))
        self.max_delay_seconds = max(self.delay_seconds, float(self.max_delay_seconds))

    def should_retry(self, exc: Exception) -> bool:
        if self.retry_on is None:
            return True
        if isinstance(self.retry_on, tuple):
            return isinstance(exc, self.retry_on)
        return isinstance(exc, self.retry_on)


class WorkerPool(Generic[T]):
    """Run independent jobs on a bounded thread pool with aggregate callbacks."""

    def __init__(
        self,
        job: Callable[[Any, Callable[[Any], None], threading.Event], T],
        max_workers: int = 4,
        retry: RetryPolicy | None = None,
        fail_fast: bool = False,
        progress_throttle: float = 0.05,
        on_progress: Callable[[BatchProgress], None] | None = None,
        on_item_progress: Callable[[int, Any], None] | None = None,
        on_item_done: Callable[[BatchItem[T]], None] | None = None,
        on_error: Callable[[BatchItem[T]], None] | None = None,
        on_done: Callable[[list[BatchItem[T]]], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self._job = job
        self._max_workers = max(1, int(max_workers))
        self._retry = retry or RetryPolicy()
        self._fail_fast = fail_fast
        self._progress_throttle = max(0.0, float(progress_throttle))
        self._on_progress = on_progress
        self._item_progress_cb = on_item_progress
        self._on_item_done = on_item_done
        self._on_error = on_error
        self._on_done = on_done
        self._on_cancel = on_cancel

        self._cancel_event = threading.Event()
        self._finished = threading.Event()
        self._lock = threading.Lock()
        self._items: list[BatchItem[T]] = []
        self._pending: list[BatchItem[T]] = []
        self._futures: dict[Future[None], BatchItem[T]] = {}
        self._executor: ThreadPoolExecutor | None = None
        self._started = False
        self._completed = 0
        self._succeeded = 0
        self._failed = 0
        self._last_progress = 0.0

    def submit(self, payload: Any) -> int:
        """Enqueue one task and return its index. Call before ``start()``."""
        with self._lock:
            if self._started:
                raise RuntimeError("WorkerPool already started")
            index = len(self._items)
            item = BatchItem[T](index=index, payload=payload)
            self._items.append(item)
            self._pending.append(item)
            return index

    def submit_many(self, payloads: Iterable[Any]) -> list[int]:
        """Enqueue many tasks and return their indices."""
        return [self.submit(payload) for payload in payloads]

    def start(self) -> None:
        """Start processing all enqueued tasks without blocking the caller."""
        with self._lock:
            if self._started:
                raise RuntimeError("WorkerPool already started")
            if not self._items:
                raise ValueError("WorkerPool has no tasks")
            self._started = True
            pending = list(self._pending)
            self._pending.clear()
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="WorkerPool",
        )
        for item in pending:
            future = self._executor.submit(self._run_item, item)
            with self._lock:
                self._futures[future] = item
            future.add_done_callback(self._done_callback(item.index))

    def _done_callback(self, index: int) -> Callable[[Future[None]], None]:
        def callback(future: Future[None]) -> None:
            self._on_item_finished(index, future)

        return callback

    def cancel(self) -> None:
        """Request cancellation for pending and running tasks."""
        self._cancel_event.set()
        with self._lock:
            futures = list(self._futures)
            if not self._started:
                for item in self._items:
                    if item.status == "queued":
                        item.status = "cancelled"
                self._finished.set()
        for future in futures:
            future.cancel()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for the pool to finish. Returns True when all tasks settled."""
        if not self._started:
            return not self._items
        return self._finished.wait(timeout)

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the backing executor. Call ``cancel()`` first to stop work."""
        executor = self._executor
        self._executor = None
        if executor is not None:
            executor.shutdown(wait=wait, cancel_futures=True)

    def is_running(self) -> bool:
        return self._started and not self._finished.is_set()

    def items(self) -> list[BatchItem[T]]:
        with self._lock:
            return list(self._items)

    def results(self) -> list[T]:
        return [
            item.result
            for item in self.items()
            if item.status == "succeeded" and item.result is not None
        ]

    def run_all(self, payloads: Iterable[Any]) -> list[BatchItem[T]]:
        """Convenience: enqueue, start, wait, and return all items."""
        self.submit_many(payloads)
        self.start()
        self.wait()
        return self.items()

    def _run_item(self, item: BatchItem[T]) -> None:
        attempts = 0
        delay = self._retry.delay_seconds
        while True:
            attempts += 1
            item.attempts = attempts
            if self._cancel_event.is_set():
                item.status = "cancelled"
                return
            try:
                result = self._job(
                    item.payload,
                    lambda p: self._on_item_progress(item.index, p),
                    self._cancel_event,
                )
                item.result = result
                item.error = None
                item.status = "succeeded"
                return
            except Cancelled:
                item.status = "cancelled"
                return
            except Exception as exc:  # noqa: BLE001 -- surfaced through on_error
                item.error = exc
                item.status = "failed"
                if attempts >= self._retry.max_attempts or not self._retry.should_retry(exc):
                    if self._fail_fast:
                        self._cancel_event.set()
                    return
                time.sleep(min(delay, self._retry.max_delay_seconds))
                delay = min(
                    self._retry.max_delay_seconds,
                    delay * self._retry.backoff,
                )

    def _on_item_progress(self, index: int, value: Any) -> None:
        if self._item_progress_cb is not None:
            self._item_progress_cb(index, value)

    def _on_item_finished(self, index: int, future: Future[None]) -> None:
        item = self._items[index]
        cancelled = future.cancelled()
        if cancelled:
            item.status = "cancelled"
            item.error = None
        else:
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001 -- defensive only
                item.status = "failed"
                item.error = exc

        with self._lock:
            self._futures.pop(future, None)
            self._completed += 1
            if item.status == "succeeded":
                self._succeeded += 1
            elif item.status == "cancelled":
                self._failed += 1
            else:
                self._failed += 1
            finished = not self._futures

        if item.error is not None and self._on_error is not None:
            self._on_error(item)
        if self._on_item_done is not None:
            self._on_item_done(item)
        self._emit_progress()

        if finished:
            snapshot = self.items()
            if self._cancel_event.is_set() and self._on_cancel is not None:
                self._on_cancel()
            if self._on_done is not None:
                self._on_done(snapshot)
            self._finished.set()

    def _emit_progress(self) -> None:
        now = time.monotonic()
        with self._lock:
            if now - self._last_progress < self._progress_throttle:
                return
            self._last_progress = now
            progress = BatchProgress(
                completed=self._completed,
                total=len(self._items),
                succeeded=self._succeeded,
                failed=self._failed,
            )
        if self._on_progress is not None:
            self._on_progress(progress)

    def __enter__(self) -> WorkerPool[T]:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.shutdown(wait=True)


if __name__ == "__main__":
    import time

    def demo_job(payload, progress, cancel_event):
        for step in range(5):
            check_cancel(cancel_event)
            time.sleep(0.01)
            progress((step + 1) / 5)
        return payload * 2

    with WorkerPool(demo_job, max_workers=3) as pool:
        pool.submit_many(range(6))
        pool.start()
        pool.wait(timeout=5)
        print(f"threading_pool: {len(pool.results())} results")
