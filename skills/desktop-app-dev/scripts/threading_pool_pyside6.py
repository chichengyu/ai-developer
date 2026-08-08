"""PySide6 bounded worker pool using QThreadPool + QRunnable + signals.

This is the canonical Qt parallel-pool pattern: each task is a QRunnable,
the pool bounds concurrency, and all callbacks arrive through queued
signals on the UI thread. Widgets are never touched from a pool thread.

Usage:
    pool = PySide6WorkerPool(job=download_many, max_workers=4, parent=window)
    pool.progress.connect(on_pool_progress)
    pool.done.connect(on_pool_done)
    pool.item_failed.connect(on_item_failed)
    pool.start(urls)
    # later: pool.cancel()
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

T = TypeVar("T")


class Cancelled(Exception):
    """Raised inside a pool job to abort cleanly."""


def cancelled() -> None:
    raise Cancelled()


def check_cancel(token: CancelToken, every: int = 16) -> None:
    if token.cancelled:
        raise Cancelled()


@dataclass
class CancelToken:
    _flag: bool = False

    def cancel(self) -> None:
        self._flag = True

    @property
    def cancelled(self) -> bool:
        return self._flag


@dataclass(frozen=True)
class PoolProgress:
    completed: int
    total: int
    succeeded: int
    failed: int

    @property
    def percent(self) -> float:
        return self.completed / self.total if self.total else 1.0


@dataclass
class PoolItem(Generic[T]):
    index: int
    payload: Any
    result: T | None = None
    error: Exception | None = None
    attempts: int = 0
    status: str = "queued"


@dataclass
class RetryPolicy:
    max_attempts: int = 1
    delay_seconds: float = 0.0
    backoff: float = 1.0
    max_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        self.max_attempts = max(1, int(self.max_attempts))
        self.delay_seconds = max(0.0, float(self.delay_seconds))
        self.backoff = max(1.0, float(self.backoff))
        self.max_delay_seconds = max(self.delay_seconds, float(self.max_delay_seconds))


class _PoolSignals(QObject):
    started = Signal()
    progress = Signal(object)
    item_progress = Signal(int, object)
    item_done = Signal(object)
    item_failed = Signal(object)
    item_cancelled = Signal(int)
    finished = Signal(int)
    done = Signal(object)
    cancelled = Signal()


class _PoolRunnable(QRunnable):
    def __init__(
        self,
        index: int,
        payload: Any,
        job: Callable[[Any, Callable[[Any], None], CancelToken], T],
        token: CancelToken,
        retry: RetryPolicy,
        signals: _PoolSignals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self._index = index
        self._payload = payload
        self._job = job
        self._token = token
        self._retry = retry
        self._signals = signals

    def run(self) -> None:
        attempts = 0
        delay = self._retry.delay_seconds
        while True:
            attempts += 1
            if self._token.cancelled:
                self._signals.item_cancelled.emit(self._index)
                break
            try:
                result = self._job(
                    self._payload,
                    lambda p: self._signals.item_progress.emit(self._index, p),
                    self._token,
                )
                self._signals.item_done.emit(
                    PoolItem(
                        index=self._index,
                        payload=self._payload,
                        result=result,
                        attempts=attempts,
                        status="succeeded",
                    )
                )
                break
            except Cancelled:
                self._signals.item_cancelled.emit(self._index)
                break
            except Exception as exc:  # noqa: BLE001 -- surfaced through signals
                if attempts >= self._retry.max_attempts:
                    self._signals.item_failed.emit(
                        PoolItem(
                            index=self._index,
                            payload=self._payload,
                            error=exc,
                            attempts=attempts,
                            status="failed",
                        )
                    )
                    break
                time.sleep(min(delay, self._retry.max_delay_seconds))
                delay = min(self._retry.max_delay_seconds, delay * self._retry.backoff)
        self._signals.finished.emit(self._index)


class PySide6WorkerPool(QObject, Generic[T]):
    """Bounded pool that emits aggregate and per-item signals on the UI thread."""

    progress = Signal(object)
    item_progress = Signal(int, object)
    item_done = Signal(object)
    item_failed = Signal(object)
    item_cancelled = Signal(int)
    done = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        job: Callable[[Any, Callable[[Any], None], CancelToken], T],
        max_workers: int = 4,
        retry: RetryPolicy | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._job = job
        self._retry = retry or RetryPolicy()
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(max(1, max_workers))
        self._signals = _PoolSignals()
        self._signals.item_progress.connect(self.item_progress)
        self._signals.item_done.connect(self._on_item_done)
        self._signals.item_failed.connect(self._on_item_failed)
        self._signals.item_cancelled.connect(self._on_item_cancelled)
        self._signals.finished.connect(self._on_finished)

        self._runnables: list[_PoolRunnable] = []
        self._items: list[PoolItem[T]] = []
        self._token = CancelToken()
        self._completed = 0
        self._succeeded = 0
        self._failed = 0
        self._lock = threading.Lock()

    def start(self, payloads: Iterable[Any]) -> None:
        if self._runnables:
            raise RuntimeError("Pool already running")
        self._token = CancelToken()
        self._completed = 0
        self._succeeded = 0
        self._failed = 0
        self._items = [
            PoolItem(index=index, payload=payload) for index, payload in enumerate(payloads)
        ]
        self._signals.started.emit()
        for item in self._items:
            runnable = _PoolRunnable(
                item.index,
                item.payload,
                self._job,
                self._token,
                self._retry,
                self._signals,
            )
            self._runnables.append(runnable)
            self._thread_pool.start(runnable)

    def cancel(self) -> None:
        self._token.cancel()

    def is_running(self) -> bool:
        return bool(self._runnables)

    @Slot(object)
    def _on_item_done(self, item: PoolItem[T]) -> None:
        self._items[item.index] = item
        with self._lock:
            self._succeeded += 1
        self.item_done.emit(item)

    @Slot(object)
    def _on_item_failed(self, item: PoolItem[T]) -> None:
        self._items[item.index] = item
        with self._lock:
            self._failed += 1
        self.item_failed.emit(item)

    @Slot(int)
    def _on_item_cancelled(self, index: int) -> None:
        self._items[index].status = "cancelled"
        with self._lock:
            self._failed += 1
        self.item_cancelled.emit(index)

    @Slot(int)
    def _on_finished(self, index: int) -> None:
        del index
        with self._lock:
            self._completed += 1
            all_done = self._completed >= len(self._items)
        self.progress.emit(
            PoolProgress(
                completed=self._completed,
                total=len(self._items),
                succeeded=self._succeeded,
                failed=self._failed,
            )
        )
        if all_done:
            self._runnables.clear()
            if self._token.cancelled:
                self.cancelled.emit()
            self.done.emit(self._items)


if __name__ == "__main__":
    print("desktop-app-dev threading_pool_pyside6: import PySide6WorkerPool inside a Qt app.")
