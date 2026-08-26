# 2026-08-08 (round 24) -- Lint version pinning, CI cache, cleanup

### Changed

- `tests/run_lint.ps1` -- `Ensure-Tool` now reads the exact version from
  `requirements-dev.txt` and compares it with `pip show` output instead
  of only checking that the module imports. Check-only mode reports a
  version mismatch; `-InstallDeps` installs the pinned version.
- `.github/workflows/ci.yml` -- the lint job now enables the
  `setup-python` pip cache, matching the Windows smoke job.
- `tests/test_docs.py` -- verifies the pre-commit ruff/mypy revisions
  stay in sync with `requirements-dev.txt` (571 checks).

### Housekeeping

- Removed the empty stray `app/` directory from the skill root.

### Verified

- `smoke_windows.ps1` -- 84 / 84
- `test_docs.py` -- 571 checks
- `test_no_bom.py` -- 181 files, 0 BOM / U+FEFF
- media pipeline -- 42 / 42; arch awareness -- 16 / 16
- selector self-test -- 8 / 8; VK table -- 119 keys / 10 templates
- ruff check, ruff format --check, mypy scripts/ -- all green
