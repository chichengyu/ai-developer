"""Tkinter bounded worker pool with UI-thread callbacks.

Wraps ``threading_pool.WorkerPool`` so every aggregate callback is posted
through ``root.after(0, ...)``. Jobs keep the same signature:
``job(payload, progress, cancel_event)`` and should call
``check_cancel(cancel_event)`` at loop boundaries.

Usage:
    pool = TkWorkerPool(
        job=download_many,
        max_workers=4,
        root=root,
        on_progress=lambda p: status_var.set(f"{p.percent:.0%}"),
        on_done=lambda items: status_var.set(f"done {len(items)}"),
    )
    pool.submit_many(urls)
    pool.start()
    # later: pool.cancel()
"""

from __future__ import annotations

import contextlib
import threading
import tkinter as tk
from collections.abc import Callable, Iterable
from typing import Any, Generic, TypeVar

from threading_pool import (  # noqa: F401
    BatchItem,
    BatchProgress,
    Cancelled,
    RetryPolicy,
    WorkerPool,
    check_cancel,
)

T = TypeVar("T")


class TkWorkerPool(Generic[T]):
    """Bounded pool whose callbacks are marshalled to the Tk UI thread."""

    def __init__(
        self,
        job: Callable[[Any, Callable[[Any], None], threading.Event], T],
        max_workers: int = 4,
        root: tk.Misc | None = None,
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
        resolved_root = root or _find_root()
        if resolved_root is None:
            raise RuntimeError("No Tk root window known; pass root= explicitly")
        self._root: tk.Misc = resolved_root
        self._pool = WorkerPool(
            job=job,
            max_workers=max_workers,
            retry=retry,
            fail_fast=fail_fast,
            progress_throttle=progress_throttle,
            on_progress=self._marshal(on_progress),
            on_item_progress=self._marshal(on_item_progress),
            on_item_done=self._marshal(on_item_done),
            on_error=self._marshal(on_error),
            on_done=self._marshal(on_done),
            on_cancel=self._marshal(on_cancel),
        )

    def submit(self, payload: Any) -> int:
        return self._pool.submit(payload)

    def submit_many(self, payloads: Iterable[Any]) -> list[int]:
        return self._pool.submit_many(payloads)

    def start(self) -> None:
        self._pool.start()

    def cancel(self) -> None:
        self._pool.cancel()

    def wait(self, timeout: float | None = None) -> bool:
        return self._pool.wait(timeout)

    def is_running(self) -> bool:
        return self._pool.is_running()

    def items(self) -> list[BatchItem[T]]:
        return self._pool.items()

    def results(self) -> list[T]:
        return self._pool.results()

    def _marshal(self, callback: Callable[..., None] | None) -> Callable[..., None] | None:
        if callback is None:
            return None

        def wrapper(*args: Any) -> None:
            with contextlib.suppress(tk.TclError):
                self._root.after(0, callback, *args)

        return wrapper


def _find_root() -> tk.Misc | None:
    try:
        return tk._default_root  # type: ignore[attr-defined]
    except AttributeError:
        return None


if __name__ == "__main__":
    print("desktop-app-dev threading_pool_tkinter: import TkWorkerPool inside a Tk app.")
