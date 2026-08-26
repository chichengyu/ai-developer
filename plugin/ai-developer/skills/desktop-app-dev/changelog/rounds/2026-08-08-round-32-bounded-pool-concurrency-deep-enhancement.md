# 2026-08-08 (round 32) -- Bounded pool concurrency deep enhancement

### Added

- `scripts/threading_pool.py` -- runtime-safe Python worker pool with
  bounded concurrency, aggregate `BatchProgress`, per-item progress,
  `RetryPolicy`, fail-fast, and cooperative cancellation.
- 7 more pool templates: `threading_pool_tkinter.py`,
  `threading_pool_pyside6.py`, `threading_pool_csharp.cs`,
  `threading_pool_tauri.rs`, `threading_pool_kotlin_compose.kt`,
  `threading_pool_electron.ts`, and
  `threading_pool_electron_worker.ts`. The `scripts/threading_*` set is
  now 30 files (22 single-worker + 8 pool).
- `tests/test_threading_concurrency.py` -- runtime checks for bounds,
  retry, cancel, progress aggregation, per-item errors, and fail-fast;
  wired into the Windows / macOS / Linux smoke suites.
- `references/threading_playbook.md` and `framework_matrix.md` now carry
  pool-template tables, aggregate-progress rules, retry/backoff,
  backpressure, and cancellation fan-out guidance.

### Docs

- `SKILL.md`, `README.md`, `INDEX.md`, and `tests/README.md` updated with
  the 30-template map and pool-first guidance for batch work.

### Verified

- smoke_windows.ps1 -- 110 / 110
- test_docs.py -- 766 checks
- threading templates -- 22 / 22 single + 8 / 8 pool
- threading concurrency -- 5 / 5
- media pipeline -- 56 / 56
- test_no_bom.py -- 214 files, 0 BOM / U+FEFF
- arch awareness -- 16 / 16
- ruff check / ruff format --check / mypy scripts/ -- all green
