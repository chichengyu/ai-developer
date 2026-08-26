# 2026-08-08 (round 30) -- Library entry points and doc drift fixes

### Added

- Every Python script under `scripts/` now ships a `__main__` block; 16
  library modules gained a no-I/O import/usage entry point so the README
  convention is fully met.
- `tests/test_docs.py` now enforces the `__main__` convention for every
  Python script under `scripts/`.

### Fixed

- `SKILL.md` Step 2.5 no longer claims every build helper supports
  `-Install`; only helpers with a safe installer (PyInstaller / tauri-cli /
  electron-builder / fyne / wails) install on `-Install`, and the rest fail
  with the exact install command.
- `README.md` and `INDEX.md` arch wording now says the structural test
  reports 16 / 16 checks (14 build scripts + 2 auto-update parse checks).
- `tests/test_media_pipeline.py` suppresses the expected stderr message
  from the deliberate 404 fetch in `test_web_data_pipeline_deep_crawl`, so
  the final verification summary is clean.

### Verified

- smoke_windows.ps1 -- 103 / 103
- test_docs.py -- 720 checks
- media pipeline -- 56 / 56
- test_no_bom.py -- 188 files, 0 BOM / U+FEFF
- arch awareness -- 16 / 16
- select_framework.py -- self-test pass
- ruff check / ruff format --check / mypy scripts/ -- all green
