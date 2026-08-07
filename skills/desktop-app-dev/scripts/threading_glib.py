"""GLib main-loop background work on Linux GTK apps.

GTK is single-threaded: every UI update must run on the main thread. Long
work runs on a worker thread and the result is posted back via
GLib.idle_add / GObject.idle_add. Cancellation via threading.Event,
checked cooperatively.

If you use PyGObject (GTK 3 / GTK 4) you typically have a Gio.Application
running its own main loop -- call this wrapper from inside a Gtk.Window
or Gtk.Application. If you use Tkinter or Qt instead, prefer those
templates; this one is only for GTK/GObject apps.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class GtkBackgroundTask(Generic[T]):
    """Run a long job on a worker thread; deliver results back to GTK main loop.

    Requires PyGObject at runtime (gi.repository.GLib). Importing this
    module does NOT import gi -- it is imported lazily inside start().
    """

    def __init__(
        self,
        job: Callable[[threading.Event, Callable[[Any], None]], T],
        on_progress: Callable[[Any], None] | None = None,
        on_done: Callable[[T], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self._job = job
        self._on_progress = on_progress
        self._on_done = on_done
        self._on_error = on_error
        self._on_cancel = on_cancel
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Task already running")
        # Lazy import: do not force gi at module load time.
        from gi.repository import GLib

        self._cancel = threading.Event()
        cancel = self._cancel
        on_progress = self._on_progress
        on_done = self._on_done
        on_error = self._on_error
        on_cancel = self._on_cancel

        def post(callback, *args):
            GLib.idle_add(callback, *args)

        def progress_cb(p):
            if on_progress:
                post(on_progress, p)

        def run():
            try:
                result = self._job(cancel, progress_cb)
            except _Cancelled:
                if on_cancel:
                    post(on_cancel)
                return
            except Exception as exc:
                if on_error:
                    post(on_error, exc)
                return
            if cancel.is_set():
                if on_cancel:
                    post(on_cancel)
                return
            if on_done:
                post(on_done, result)

        self._thread = threading.Thread(target=run, name="GtkBackgroundTask", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


class _Cancelled(Exception):
    """Raised inside the worker to abort cleanly."""


def cancelled() -> None:
    raise _Cancelled()


def poll_cancel(event: threading.Event, every: int = 16) -> None:
    if event.is_set():
        raise _Cancelled()
