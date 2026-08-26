# 2026-08-09 (round 46) -- PySide6 management template + fast-start packaging

### Added

- `examples/pyside6-management/` -- PySide6 `.ui` management shell with
  left nav + one table per page, per-button/table loading states,
  `QUiLoader`, lazy `openpyxl` import/export, dependency center, and clean
  shutdown on close.
- `scripts/lazy_python_dependency.py` -- check/install optional Python
  packages only on first use; source mode uses `pip --target` into the
  app-local runtime, frozen EXEs expect build-time bundling.
- `tests/test_pyside6_management.py` -- structural checks plus an optional
  offscreen launch/shutdown regression.

### Changed

- `scripts/threading_pyside6.py` adds `finished` signal, `JobRunner.shutdown()`
  / `dispose()`, and `JobRegistry.shutdown_all()` for process/thread cleanup.
- `scripts/threading_pool_pyside6.py` adds `shutdown(timeout_ms)`.
- `scripts/builtin_dependency_manager.py` supports app-local `pip_target`
  installs and module-based pip status.
- `scripts/build_python.ps1` adds `-Mode OneDir`, `-FastStart`,
  `-InstallDeps`, `-Requirements`, and lean PySide6 exclusions.
- Docs updated: `SKILL.md`, `README.md`, `INDEX.md`,
  `references/threading_playbook.md`, `references/distribution_playbook.md`,
  `references/ui_hard_requirements.md`, `examples/README.md`.

### Verified

- PySide6 management example: 6 / 6 structural + offscreen runtime checks.
- App loads `app.ui`, runs tasks/deps/logs, exports XLSX, and exits with
  zero running jobs/threads.
- `build_python.ps1 -FastStart -InstallDeps -Paths scripts` produced a
  OneDir EXE; `PySide6Management.exe --smoke-test` exits 0 with zero
  leftover processes.
