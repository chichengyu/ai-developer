# 2026-08-08 (round 17) -- Shared Python resolver, Linux PyInstaller gate, docs drift

### Added

- `scripts/find_python.ps1` -- single shared Python discovery used by
  `build_python.ps1`, `bootstrap_environment.ps1`,
  `setup_media_dependencies.ps1`, `tests/run_lint.ps1`, and
  `tests/smoke_windows.ps1`. Order: `-PythonExe` / `CODEX_PYTHON` /
  `PYTHON` / Codex runtime under `$HOME\.cache` / PATH.
- `smoke_windows.ps1` -- regression tests for the shared resolver,
  including `PYTHON` env-var preference.

### Fixed

- `bootstrap_environment.ps1`, `setup_media_dependencies.ps1`,
  `tests/run_lint.ps1`, and `tests/smoke_windows.ps1` now honor the
  `PYTHON` environment variable and no longer embed a hardcoded
  `C:\Users\xc` path (Codex runtime lookup uses `$HOME\.cache`).
- `build_linux.ps1` -- `-Tool python` now invokes PyInstaller through
  the resolved `python3` module and only installs missing PyInstaller
  when `-Install` is passed.
- `build_electron.ps1` -- `-Target` is now `[ValidateSet(...)]` so a
  typo fails fast instead of reaching electron-builder.

### Changed

- README / INDEX / SKILL clarified template file counts (12 files each
  for the SendInput and window-enum sets incl. Java) and made
  `media_dependencies.py` default-check-only explicit.
- Smoke count updated to 77 / 77.

### Verified

- `smoke_windows.ps1` -- 77 / 77
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 527 checks
- `test_no_bom.py` -- 173 files, 0 BOM / U+FEFF
- media pipeline -- 11 / 11; selector self-test -- 8 / 8; VK table --
  119 keys / 10 templates
