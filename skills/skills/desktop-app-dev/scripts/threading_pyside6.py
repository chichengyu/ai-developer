"""PySide6 background work using QThread + Signal/Slot.

QThread + a QObject worker is the canonical, race-free way to do background
work in Qt. Signals are auto-queued across threads, so the UI thread only
sees them as slot invocations on the main event loop. Never mutate widgets
from a non-Qt worker thread -- Qt will crash with "QObject: Cannot create
children for a parent that is in a different thread".

Usage:
    worker = JobRunner(long_job, parent=self)
    worker.progress.connect(self.update_progress)
    worker.done.connect(self.on_done)
    worker.failed.connect(self.on_error)
    worker.start()
    # later: worker.cancel()

Clean shutdown:
    jobs = JobRegistry(parent=window)
    jobs.register(JobRunner(job, parent=window, auto_delete=False))
    # on window close:
    jobs.shutdown_all(3000)
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

T = TypeVar("T")


class _JobSignals(QObject):
    started = Signal()
    progress = Signal(object)
    done = Signal(object)
    failed = Signal(object)  # carries the Exception
    cancelled = Signal()
    finished = Signal()


@dataclass
class JobRunner(Generic[T]):
    """Self-contained worker + thread. Drop into any Qt widget."""

    job: Callable[[JobRunner.CancelToken, Callable[[Any], None]], T]
    parent: QObject | None = None
    auto_delete: bool = True

    class CancelToken:
        def __init__(self) -> None:
            self._flag = False

        def cancel(self) -> None:
            self._flag = True

        @property
        def cancelled(self) -> bool:
            return self._flag

    def __post_init__(self) -> None:
        self.signals = _JobSignals()
        self._thread: QThread | None = QThread()
        self._worker: _Worker | None = _Worker(self.job, self.signals)
        assert self._thread is not None
        assert self._worker is not None
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        if self.auto_delete:
            self._worker.finished.connect(self._worker.deleteLater)
            self._thread.finished.connect(self._thread.deleteLater)
        self._token: JobRunner.CancelToken | None = None
        self._disposed = False

    def start(self) -> None:
        if self._disposed:
            raise RuntimeError("JobRunner has been disposed")
        if self._thread is None or self._worker is None:
            raise RuntimeError("JobRunner has been disposed")
        if self._thread.isRunning():
            raise RuntimeError("Job already running")
        self._token = JobRunner.CancelToken()
        self._worker.token = self._token
        self._thread.start()

    def cancel(self) -> None:
        if self._token:
            self._token.cancel()

    def is_running(self) -> bool:
        return not self._disposed and self._thread is not None and self._thread.isRunning()

    def wait(self, timeout_ms: int = 3000) -> bool:
        if self._disposed or self._thread is None:
            return True
        return self._thread.wait(max(1, int(timeout_ms)))

    def shutdown(self, timeout_ms: int = 3000) -> bool:
        """Cancel and wait for the worker with a bounded timeout."""
        self.cancel()
        return self.wait(timeout_ms)

    def dispose(self) -> None:
        """Release QThread/worker ownership after the runner finishes."""
        if self._disposed:
            return
        self._disposed = True
        if self._thread is not None:
            if self._thread.isRunning():
                self._thread.wait(3000)
            self._thread.deleteLater()
            self._thread = None
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    # convenience signal forwarders
    def on(self, name: str) -> Any:
        return getattr(self.signals, name)


class JobRegistry(QObject):
    """Track running JobRunners so the app can cancel and wait on exit."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._runners: list[JobRunner[Any]] = []
        self._lock = threading.Lock()

    def register(self, runner: JobRunner[Any]) -> None:
        with self._lock:
            self._runners.append(runner)
        runner.on("finished").connect(lambda: self._on_finished(runner))

    @property
    def running_count(self) -> int:
        with self._lock:
            return sum(1 for runner in self._runners if runner.is_running())

    def shutdown_all(self, timeout_ms: int = 3000) -> bool:
        """Cancel every runner, wait with a bounded budget, then release."""
        with self._lock:
            runners = list(self._runners)
        for runner in runners:
            runner.cancel()
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        for runner in runners:
            remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
            if runner.is_running():
                runner.wait(remaining_ms)
            if not runner.auto_delete:
                runner.dispose()
        with self._lock:
            self._runners.clear()
        return all(not runner.is_running() for runner in runners)

    def _on_finished(self, runner: JobRunner[Any]) -> None:
        with self._lock:
            for index, current in enumerate(self._runners):
                if current is runner:
                    self._runners.pop(index)
                    break
        if not runner.auto_delete:
            runner.dispose()


class _Worker(QObject):
    finished = Signal()

    def __init__(self, job, signals) -> None:
        super().__init__()
        self._job = job
        self.signals = signals
        self.token: JobRunner.CancelToken | None = None

    @Slot()
    def run(self) -> None:
        self.signals.started.emit()
        try:
            if self.token is None:
                self.token = JobRunner.CancelToken()
            result = self._job(self.token, lambda p: self.signals.progress.emit(p))
            if self.token.cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.done.emit(result)
        except _Cancelled:
            self.signals.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(exc)
        finally:
            self.signals.finished.emit()
            self.finished.emit()


class _Cancelled(Exception):
    """Raised inside the worker to abort cleanly."""


def cancelled() -> None:
    raise _Cancelled()


def poll_cancel(token: JobRunner.CancelToken, every: int = 16) -> None:
    if token.cancelled:
        raise _Cancelled()


# ---- Example ---------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import time

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QProgressBar,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    app = QApplication(sys.argv)
    w = QWidget()
    w.setWindowTitle("JobRunner demo")
    layout = QVBoxLayout(w)
    status = QLabel("idle")
    bar = QProgressBar()
    bar.setRange(0, 100)
    btn = QPushButton("Start 5s job")
    layout.addWidget(status)
    layout.addWidget(bar)
    layout.addWidget(btn)

    runner_holder: dict[str, Any] = {}

    def long_job(token, progress):
        for i in range(100):
            poll_cancel(token)
            time.sleep(0.05)
            progress(i + 1)
        return "ok"

    def start():
        if runner_holder.get("runner") and runner_holder["runner"].is_running():
            return
        runner = JobRunner(long_job, parent=w)
        runner.on("started").connect(lambda: status.setText("started"))
        runner.on("progress").connect(
            lambda p: (bar.setValue(int(p)), status.setText(f"{int(p)}%"))
        )
        runner.on("done").connect(lambda r: status.setText(f"done: {r}"))
        runner.on("failed").connect(lambda e: status.setText(f"error: {e}"))
        runner.on("cancelled").connect(lambda: status.setText("cancelled"))
        runner_holder["runner"] = runner
        btn.setText("Cancel")
        btn.disconnect()
        btn.clicked.connect(runner.cancel)
        QTimer.singleShot(
            5500,
            lambda: btn.setText("Start 5s job")
            or btn.clicked.disconnect()
            or btn.clicked.connect(start),
        )
        runner.start()

    btn.clicked.connect(start)
    w.resize(360, 140)
    w.show()
    sys.exit(app.exec())
