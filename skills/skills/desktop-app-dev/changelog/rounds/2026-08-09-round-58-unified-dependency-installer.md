# 2026-08-09 (round 58) -- Unified dependency installer

### Added

- `scripts/ensure_all_dependencies.py` -- one-pass check/install for the
  web-fetch stack, media runtime, and an optional manifest-driven app
  dependency set:

  ```powershell
  python scripts/ensure_all_dependencies.py --check
  python scripts/ensure_all_dependencies.py --install --manifest dependencies.json
  ```

- Documented the unified installer in `README.md`, `INDEX.md`, the media
  acquisition playbook, and the web data pipeline playbook.
- Regression tests for unified status reporting and the frozen-mode install
  guard.

### Verified

- `ruff` + `ruff format` + `mypy` pass (62 files, 50 source files).
- Windows smoke: 136 / 136; media pipeline: 95 / 95; docs: 1029; BOM: 308.
