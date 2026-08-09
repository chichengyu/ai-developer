# 2026-08-09 (round 57) -- Frozen install guards + single-file EXE

### Added

- `ensure_web_fetch_dependencies.py` and `media_dependencies.py` now fail
  with a clear "not bundled in this EXE" message when run from a frozen
  PyInstaller app, instead of trying to invoke pip / Playwright inside the
  packaged process.
- Regression tests for both frozen install paths.
- Single-file `dist/PySide6Management.exe` built with `-Mode OneFile` for
  portable distribution; the OneDir folder is kept for faster cold start.

### Verified

- `ruff` + `ruff format` + `mypy` pass.
- Media pipeline: 93 / 93; dependency center: 3 / 3; PySide6 management:
  6 / 6; docs: 1024; BOM: 306.
- OneDir build: 173 MB; OneFile build: 68.8 MB; both launch smoke passed
  and bundle the dependency-center / threading / openpyxl chain.
