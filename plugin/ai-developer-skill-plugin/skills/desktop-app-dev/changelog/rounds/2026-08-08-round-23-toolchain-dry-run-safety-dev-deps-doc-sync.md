# 2026-08-08 (round 23) -- Toolchain dry-run safety, dev deps, doc sync

### Fixed

- `scripts/bootstrap_environment.ps1` -- `-DryRun` now always wins over
  `-Install`. Previously `-DryRun -Install` executed winget/pip installs
  and then printed "no changes were made"; dry-run now skips every
  install action and prints the pip command it would run.
- `SKILL.md` -- SendInput / window-enum template counts no longer double
  count Java; Step 1 Category C no longer lists service/driver delivery
  as in scope while "Out of scope" forbids it.
- `scripts/select_framework.py` -- self-test case lines use `[OK]`
  consistently instead of `[OK  ]`.

### Added

- `requirements-dev.txt` -- shared pin file for `ruff==0.6.9`,
  `mypy==1.13.0`, and `types-requests`. CI and `tests/run_lint.ps1` now
  consume the same file, and `run_lint.ps1` checks `types-requests`
  alongside ruff/mypy.
- `tests/smoke_windows.ps1` -- regression test proving
  `bootstrap_environment.ps1 -DryRun -Install` never runs an install,
  plus a doc-count sync check that fails when README/SKILL smoke counts
  drift from the real total.
- `tests/test_docs.py` -- Windows smoke count checks now compare
  README/SKILL dynamically instead of hard-coding `83`, and verify
  `requirements-dev.txt` is referenced by CI, run_lint, and README.

### Verified

- `smoke_windows.ps1` -- 84 / 84
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 570 checks
- `test_no_bom.py` -- 181 files, 0 BOM / U+FEFF
- media pipeline -- 42 / 42
- selector self-test -- 8 / 8; VK table -- 119 keys / 10 templates
- ruff check, ruff format --check, mypy scripts/ -- all green
