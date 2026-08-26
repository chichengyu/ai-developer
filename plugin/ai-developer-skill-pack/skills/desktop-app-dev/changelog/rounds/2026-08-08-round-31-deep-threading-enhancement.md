# 2026-08-08 (round 31) -- Deep threading enhancement

### Added

- 15 new threading templates: WinForms, Avalonia, .NET MAUI, Electron
  (main + worker), Qt 6, Wails, Fyne, walk, egui, Slint, JavaFX, Compose,
  Flutter, and Win32 C. The `scripts/threading_*` set is now 22 files.
- `references/threading_playbook.md` -- worker contract, 22-template map,
  patterns (worker pools, sequential queues, fan-out, progress throttling,
  state handoff, COM apartments, dispatcher lifetime), anti-patterns, and a
  Step 6 checklist.
- `tests/test_threading_templates.py` -- source-level contract check for
  every threading template (cancel, progress, error, UI bridge); wired
  into the Windows / macOS / Linux smoke suites.
- `tests/test_docs.py` now enforces the playbook registration and the
  22-template count.

### Fixed

- `scripts/threading_dispatch.swift` -- rewritten to a clean
  `Task.detached` + `@MainActor` contract; the previous Task signature was
  not usable as a job bridge.
- WPF / WinUI templates now support `onCancel`, dispose the
  `CancellationTokenSource`, and reject starting without a UI dispatcher.
- PySide6 template now honors the `auto_delete` option.

### Docs

- `SKILL.md`, `README.md`, `INDEX.md`, `framework_matrix.md`, and
  `CONTRIBUTING.md` updated with the 22-template map and playbook pointer.

### Verified

- smoke_windows.ps1 -- 105 / 105
- test_docs.py -- 754 checks
- threading templates -- 22 / 22
- media pipeline -- 56 / 56
- test_no_bom.py -- 205 files, 0 BOM / U+FEFF
- arch awareness -- 16 / 16
- select_framework.py -- self-test pass
- ruff check / ruff format --check / mypy scripts/ -- all green
