# 2026-08-09 (round 53) -- Startup splash hard requirement

### Added

- `StartupSplash` in the PySide6 example: frameless startup window with a
  fade-in animation, status text, and a 0-100% progress bar before the main
  window opens.
- UI hard requirements now state that every packaged EXE must show a
  startup animation + progress bar; a blank/frozen startup window is a
  release blocker.

### Changed

- `SKILL.md`, `templates/release_checklist.md`, and
  `templates/requirements_checklist.md` record the startup-splash
  requirement.
- PySide6 `main()` shows the splash, animates progress, then opens the
  main window; `--smoke-test` still exits cleanly.

### Verified

- `tests/test_pyside6_management.py` checks `StartupSplash`,
  `QPropertyAnimation`, `set_progress`, and the splash startup path.
- Windows smoke suite remains green.
