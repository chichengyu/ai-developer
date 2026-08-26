"""Minimal TLBB-style game-automation demo.

This shows the canonical pattern for category-A apps from
references/task_decomposition.md (TLBB worked example):

    1. WindowFinder picks the game window.
    2. TkBackgroundTask runs blocking work on a daemon thread.
    3. sendinput_python sends SendInput keystrokes with jitter.

Run:
    python examples/game-automation/app/app.py

NEVER actually run this against a real game in CI -- the __main__ below
deliberately does not target any HWND.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

SKILL_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from sendinput_python import press_combo, send_key  # noqa: E402
from threading_tkinter import TkBackgroundTask, poll_cancel  # noqa: E402
from window_enum_python import WindowFinder  # noqa: E402


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Game automation demo (idle)")
        self.finder = WindowFinder(timeout_s=3.0)
        self.target_hwnd: int | None = None
        self.worker: TkBackgroundTask | None = None

        self.status = tk.StringVar(value="no target window")
        self.target_var = tk.StringVar(value="(none)")

        ttk.Label(self.root, text="Target window:").pack(anchor="w", padx=10)
        ttk.Entry(self.root, textvariable=self.target_var, width=40).pack(padx=10)
        ttk.Button(self.root, text="Refresh windows", command=self.refresh).pack(padx=10, pady=2)
        ttk.Label(self.root, textvariable=self.status).pack(padx=10, pady=4)

        btns = ttk.Frame(self.root)
        btns.pack(padx=10, pady=4)
        ttk.Button(btns, text="Send F5", command=lambda: self.send_key("f5")).pack(
            side="left", padx=2
        )
        ttk.Button(btns, text="Combo Ctrl+F1", command=lambda: self.send_combo("ctrl+f1")).pack(
            side="left", padx=2
        )
        ttk.Button(btns, text="Quit", command=self.root.destroy).pack(side="left", padx=2)

    def _run(self, job, on_done) -> None:
        if self.worker and self.worker.is_running():
            self.status.set("busy")
            return
        self.worker = TkBackgroundTask(
            job=job,
            on_done=on_done,
            on_error=lambda e: self.status.set(f"error: {e}"),
            root=self.root,
        )
        self.worker.start()

    def refresh(self) -> None:
        title = self.target_var.get().strip()
        if title:

            def job(cancel_evt, progress):
                poll_cancel(cancel_evt)
                return self.finder.find(class_name=None, title_substring=title)

            def on_done(hwnd):
                if hwnd:
                    self.target_hwnd = hwnd
                    self.status.set(f"target HWND={hwnd}")
                else:
                    self.status.set("not found")
        else:

            def job(cancel_evt, progress):
                poll_cancel(cancel_evt)
                return len(self.finder.list_windows())

            def on_done(count):
                self.status.set(f"{count} windows; type a title substring to pick one")

        self._run(job, on_done)

    def send_key(self, k: str) -> None:
        if not self.target_hwnd:
            self.status.set("no target HWND")
            return

        def job(cancel_evt, progress):
            poll_cancel(cancel_evt)
            send_key(self.target_hwnd, k, hold_ms=60)
            return f"sent {k}"

        self._run(job, self.status.set)

    def send_combo(self, combo: str) -> None:
        if not self.target_hwnd:
            self.status.set("no target HWND")
            return

        def job(cancel_evt, progress):
            poll_cancel(cancel_evt)
            press_combo(self.target_hwnd, combo)
            return f"sent {combo}"

        self._run(job, self.status.set)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
