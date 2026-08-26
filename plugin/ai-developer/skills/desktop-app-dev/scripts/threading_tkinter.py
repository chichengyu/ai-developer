"""Tkinter background work with cancellation + progress + safe UI bridge.

Usage:
    worker = TkBackgroundTask(
        job=lambda token, progress: do_long_work(token, progress),
        on_progress=lambda p: status_var.set(f"progress: {p}"),
        on_done=lambda r:    status_var.set(f"done: {r}"),
        on_error=lambda e:   status_var.set(f"error: {e}"),
    )
    worker.start()
    # later: worker.cancel()

Never call time.sleep, requests.get(...), open(bigfile), or any blocking call
directly inside a Tk callback -- it freezes the window. This wrapper ensures
all long work runs in a daemon thread and the UI thread only sees the results.
"""

import threading
import tkinter as tk
from collections.abc import Callable
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class TkBackgroundTask(Generic[T]):
    """Run a long job in a background thread, post results back to the Tk UI thread."""

    def __init__(
        self,
        job: Callable[["threading.Event", Callable[[Any], None]], T],
        on_progress: Callable[[Any], None] | None = None,
        on_done: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        root: tk.Misc | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self._job = job
        self._on_progress = on_progress
        self._on_done = on_done
        self._on_error = on_error
        self._on_cancel = on_cancel
        self._root = root  # if None, inferred from any Tk widget at start() time
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Task already running")
        root = self._root or _find_root()
        if root is None:
            raise RuntimeError("No Tk root window known; pass root= explicitly")
        self._cancel = threading.Event()
        t = threading.Thread(target=self._run, args=(root,), name="TkBackgroundTask", daemon=True)
        self._thread = t
        t.start()

    def cancel(self) -> None:
        self._cancel.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self, root: tk.Misc) -> None:
        def progress(p: Any) -> None:
            if self._on_progress:
                root.after(0, self._on_progress, p)

        try:
            result = self._job(self._cancel, progress)
        except _Cancelled:
            if self._on_cancel:
                root.after(0, self._on_cancel)
            return
        except Exception as exc:  # noqa: BLE001 -- propagate to UI thread
            if self._on_error:
                root.after(0, self._on_error, exc)
            return
        if self._on_done:
            root.after(0, self._on_done, result)


class _Cancelled(Exception):
    """Raised inside the worker to abort cleanly."""


def cancelled() -> None:
    """Call from inside the job to abort (checked at the next yield point)."""
    raise _Cancelled()


def poll_cancel(event: threading.Event, every: int = 16) -> None:
    """Cheap cooperative cancel check; call periodically from CPU loops."""
    if event.is_set():
        raise _Cancelled()


def _find_root() -> tk.Misc | None:
    try:
        return tk._default_root  # type: ignore[attr-defined]
    except AttributeError:
        return None


# ---- Example ---------------------------------------------------------------
if __name__ == "__main__":
    import time

    root = tk.Tk()
    root.title("TkBackgroundTask demo")
    status = tk.StringVar(value="idle")
    pb = tk.DoubleVar(value=0.0)

    tk.Label(root, textvariable=status).pack(padx=10, pady=4)
    ttk_progress = None
    try:
        from tkinter import ttk

        ttk_progress = ttk.Progressbar(root, length=300, variable=pb, maximum=100)
        ttk_progress.pack(padx=10, pady=4)
    except ImportError:
        pass

    def long_job(cancel_evt, progress):
        for i in range(100):
            poll_cancel(cancel_evt)
            time.sleep(0.05)
            progress(i + 1)
        return "ok"

    def start():
        TkBackgroundTask(
            job=long_job,
            on_progress=lambda p: (pb.set(p), status.set(f"working {p:.0f}%")),
            on_done=lambda r: status.set(f"done: {r}"),
            on_error=lambda e: status.set(f"error: {e}"),
            on_cancel=lambda: status.set("cancelled"),
            root=root,
        ).start()

    tk.Button(root, text="Start (5s job)", command=start).pack(padx=10, pady=4)
    tk.Button(root, text="Quit", command=root.destroy).pack(padx=10, pady=4)
    root.mainloop()
