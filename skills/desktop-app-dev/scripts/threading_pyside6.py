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
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from PySide6.QtCore import QObject, QThread, Signal, Slot

T = TypeVar("T")


class _JobSignals(QObject):
    started = Signal()
    progress = Signal(object)
    done = Signal(object)
    failed = Signal(object)  # carries the Exception
    cancelled = Signal()


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
        self._thread = QThread()
        self._worker = _Worker(self.job, self.signals, self.auto_delete)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._token: JobRunner.CancelToken | None = None

    def start(self) -> None:
        if self._thread.isRunning():
            raise RuntimeError("Job already running")
        self._token = JobRunner.CancelToken()
        self._worker.token = self._token
        self._thread.start()

    def cancel(self) -> None:
        if self._token:
            self._token.cancel()

    def is_running(self) -> bool:
        return self._thread.isRunning()

    # convenience signal forwarders
    def on(self, name: str) -> Any:
        return getattr(self.signals, name)


class _Worker(QObject):
    def __init__(self, job, signals, auto_delete: bool) -> None:
        super().__init__()
        self._job = job
        self.signals = signals
        self._auto_delete = auto_delete
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
