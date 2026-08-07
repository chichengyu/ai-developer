"""Tkinter threading demo using the canonical threading_tkinter template.

Run:
    python examples/tkinter-threading/app.py
"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

# Make the skill's scripts/ importable.
SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from threading_tkinter import TkBackgroundTask, poll_cancel  # noqa: E402


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("TkBackgroundTask demo")
        self.status = tk.StringVar(value="idle")
        self.progress = tk.DoubleVar(value=0.0)

        ttk.Label(self.root, textvariable=self.status).pack(padx=10, pady=4)
        ttk.Progressbar(self.root, length=300, variable=self.progress, maximum=100).pack(
            padx=10, pady=4
        )
        btns = ttk.Frame(self.root)
        btns.pack(padx=10, pady=4)
        ttk.Button(btns, text="Start 3s job", command=self.start).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self.cancel).pack(side="left", padx=4)
        ttk.Button(btns, text="Quit", command=self.root.destroy).pack(side="left", padx=4)

        self.worker = None  # type: ignore[assignment]

    def start(self) -> None:
        if self.worker and self.worker.is_running():
            return
        self.worker = TkBackgroundTask(
            job=self.long_job,
            on_progress=self.on_progress,
            on_done=self.on_done,
            on_error=self.on_error,
            on_cancel=lambda: self.status.set("cancelled"),
            root=self.root,
        )
        self.worker.start()

    def cancel(self) -> None:
        if self.worker:
            self.worker.cancel()

    def long_job(self, cancel_evt, progress):
        for i in range(100):
            poll_cancel(cancel_evt)
            time.sleep(0.03)
            progress(i + 1)
        return "ok"

    def on_progress(self, p):
        self.progress.set(p)
        self.status.set(f"progress {p:.0f}%")

    def on_done(self, r):
        self.status.set(f"done: {r}")

    def on_error(self, e):
        self.status.set(f"error: {e}")

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
