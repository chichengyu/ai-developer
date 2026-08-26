"""PySide6 demo using the JobRunner from scripts/threading_pyside6.py.

Install PySide6 first:
    pip install PySide6

Run:
    python examples/pyside6-threading/app.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from threading_pyside6 import JobRunner, poll_cancel  # noqa: E402


class Window(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("JobRunner demo")
        self.status = QLabel("idle")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.btn = QPushButton("Start 3s job")
        self.cancel = QPushButton("Cancel")
        self.btn.clicked.connect(self.start)
        self.cancel.clicked.connect(self.do_cancel)
        self.cancel.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.bar)
        layout.addWidget(self.btn)
        layout.addWidget(self.cancel)

        self.runner = None  # type: ignore[assignment]

    def start(self) -> None:
        if self.runner and self.runner.is_running():
            return
        self.btn.setEnabled(False)
        self.cancel.setEnabled(True)
        self.runner = JobRunner(self.long_job, parent=self)
        self.runner.on("started").connect(lambda: self.status.setText("started"))
        self.runner.on("progress").connect(
            lambda p: (self.bar.setValue(int(p)), self.status.setText(f"{int(p)}%"))
        )
        self.runner.on("done").connect(self.on_done)
        self.runner.on("failed").connect(self.on_error)
        self.runner.on("cancelled").connect(lambda: self.status.setText("cancelled"))
        self.runner.start()

    def do_cancel(self) -> None:
        if self.runner:
            self.runner.cancel()

    def long_job(self, token, progress):
        for i in range(100):
            poll_cancel(token)
            time.sleep(0.03)
            progress(i + 1)
        return "ok"

    def on_done(self, r):
        self.status.setText(f"done: {r}")
        self.btn.setEnabled(True)
        self.cancel.setEnabled(False)

    def on_error(self, e):
        self.status.setText(f"error: {e}")
        self.btn.setEnabled(True)
        self.cancel.setEnabled(False)


def main() -> int:
    app = QApplication(sys.argv)
    w = Window()
    w.resize(360, 160)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
