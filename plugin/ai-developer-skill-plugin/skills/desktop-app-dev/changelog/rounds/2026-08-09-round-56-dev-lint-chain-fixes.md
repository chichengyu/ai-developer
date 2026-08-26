# 2026-08-09 (round 56) -- Dev lint chain fixes

### Fixed

- `threading_pool_pyside6.py`: QRunnable has no `deleteLater`; the pool now
  relies on QRunnable auto-delete and clears its reference list after a
  successful shutdown.
- `threading_pyside6.py`: use `Qt.ConnectionType.DirectConnection` and
  optional `QThread` / worker annotations so dispose can null them safely.
- `builtin_dependency_manager.py`: accept `Sequence` specs and guard a
  missing pip URL in status checks.
- `select_framework.py`, `smart_fetch.py`, `browser_session.py`: mypy type
  fixes without behavior changes.
- `tests/test_docs.py`: ruff formatting drift fixed.
- `build_python.ps1`: `-InstallDeps` now discovers `requirements.txt` next
  to `-Entry` before falling back to the current directory.
- `requirements-dev.txt`: pin `types-requests` for reproducible CI/lint.
- `builtin_dependency_manager.py`: frozen EXEs now fail clearly when a pip
  dependency is missing instead of pretending the install succeeded.

### Verified

- `ruff check` + `ruff format --check`: 61 files pass.
- `mypy scripts/`: 49 source files pass.
- `tests/smoke_windows.ps1`: 135 / 135.
- `tests/test_arch_awareness.ps1`: 16 / 16.
- `types-requests` installed so `tests/run_lint.ps1` runs end to end.
- `test_dependency_center.py`: 3 / 3, including the frozen pip guard.
