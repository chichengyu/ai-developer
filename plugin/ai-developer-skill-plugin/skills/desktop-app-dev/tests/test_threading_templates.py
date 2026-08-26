"""Structural regression test for the threading template set.

Every `scripts/threading_*` template must follow the worker contract:
cancellation, progress, an error/done path, and a framework-native UI
bridge. This test is source-level because CI does not install every
desktop framework toolchain.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = sorted((ROOT / "scripts").glob("threading_*"))

# One marker that proves the template routes UI work through the framework's
# safe bridge instead of touching controls from the worker thread.
EXPECTED_BRIDGE = {
    "threading_wpf.cs": "Dispatcher",
    "threading_winui.cs": "DispatcherQueue",
    "threading_winforms.cs": "BeginInvoke",
    "threading_avalonia.cs": "Dispatcher.UIThread",
    "threading_maui.cs": "MainThread",
    "threading_electron.ts": "webContents.send",
    "threading_electron_worker.ts": "parentPort",
    "threading_qt.cpp": "QThread",
    "threading_go_wails.go": "EventsEmit",
    "threading_go_fyne.go": "fyne.Do",
    "threading_go_walk.go": "RunSafe",
    "threading_rust_egui.rs": "request_repaint",
    "threading_rust_slint.rs": "upgrade_in_event_loop",
    "threading_javafx.java": "Platform.runLater",
    "threading_kotlin_compose.kt": "Dispatchers.Main",
    "threading_flutter.dart": "ReceivePort",
    "threading_win32.c": "PostMessage",
    "threading_tkinter.py": "root.after",
    "threading_pyside6.py": "Signal",
    "threading_glib.py": "idle_add",
    "threading_tauri.rs": "emit",
    "threading_dispatch.swift": "MainActor",
}

EXPECTED_POOL_BRIDGE = {
    "threading_pool.py": "framework bridge",
    "threading_pool_tkinter.py": "root.after",
    "threading_pool_pyside6.py": "Signal",
    "threading_pool_csharp.cs": "uiMarshaler",
    "threading_pool_tauri.rs": "emit",
    "threading_pool_kotlin_compose.kt": "Dispatchers.Main",
    "threading_pool_electron.ts": "webContents.send",
    "threading_pool_electron_worker.ts": "parentPort",
}


def main() -> int:
    failures: list[str] = []
    names = {path.name for path in TEMPLATES}
    if names != set(EXPECTED_BRIDGE) | set(EXPECTED_POOL_BRIDGE):
        failures.append(f"template set mismatch: {sorted(names)}")

    playbook = (ROOT / "references" / "threading_playbook.md").read_text(encoding="utf-8")
    single_count = 0
    pool_count = 0
    for path in TEMPLATES:
        text = path.read_text(encoding="utf-8")
        name = path.name
        lowered = text.lower()
        if name in EXPECTED_BRIDGE:
            single_count += 1
            if "cancel" not in lowered:
                failures.append(f"{name} missing cancel")
            if "progress" not in lowered:
                failures.append(f"{name} missing progress")
            if not any(token in lowered for token in ("error", "failed")):
                failures.append(f"{name} missing error path")
            if EXPECTED_BRIDGE[name] not in text:
                failures.append(f"{name} missing UI bridge {EXPECTED_BRIDGE[name]!r}")
            if re.search(r"\bTODO\b|\bFIXME\b", text, flags=re.IGNORECASE):
                failures.append(f"{name} contains TODO/FIXME")
        elif name in EXPECTED_POOL_BRIDGE:
            pool_count += 1
            if "cancel" not in lowered:
                failures.append(f"{name} missing cancel")
            if "progress" not in lowered:
                failures.append(f"{name} missing progress")
            if not any(token in lowered for token in ("error", "failed")):
                failures.append(f"{name} missing error path")
            if EXPECTED_POOL_BRIDGE[name] not in text:
                failures.append(f"{name} missing UI bridge {EXPECTED_POOL_BRIDGE[name]!r}")
            if name != "threading_pool_electron_worker.ts" and not any(
                token in lowered
                for token in (
                    "max_workers",
                    "maxworkers",
                    "maxconcurrency",
                    "concurr",
                    "parallel",
                    "qthreadpool",
                    "semaphore",
                    "joinset",
                )
            ):
                failures.append(f"{name} missing concurrency limit")
            if re.search(r"\bTODO\b|\bFIXME\b", text, flags=re.IGNORECASE):
                failures.append(f"{name} contains TODO/FIXME")
            if name == "threading_pool_pyside6.py" and "runnable.deleteLater()" in text:
                failures.append(f"{name} calls deleteLater on QRunnable")
        else:
            failures.append(f"{name} is not classified as single or pool template")
        if name not in playbook:
            failures.append(f"{name} not documented in threading_playbook.md")

    if failures:
        print("Threading template audit failed:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print(
        f"Threading templates: {single_count}/{single_count} single "
        f"+ {pool_count}/{pool_count} pool OK"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
