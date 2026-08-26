# 2026-08-08 (round 16) -- BOM regression, examples coverage, check-only lint

### Added

- `tests/test_no_bom.py` -- scans every text file for UTF-8 BOM / U+FEFF
  and is wired into all three smoke suites.
- Smoke tests now AST-parse every `.py` under `examples/` on Windows,
  macOS, and Linux.
- `smoke_windows.ps1` -- backup test now proves `mybuild` survives while
  `build` is excluded (exact-segment semantics).

### Fixed

- `run_lint.ps1` -- default is check-only: missing ruff / mypy now prints
  the install command and exits non-zero unless `-InstallDeps` is passed;
  PowerShell detection falls back from `pwsh` to `powershell`.
- `bootstrap_environment.ps1` -- successfully installed toolchains are
  removed from the missing list, and a failed pip install now exits
  non-zero instead of reporting success.
- `backup_source.ps1` -- exclude matching is exact path-segment based
  (`mybuild` no longer matches `build`), and a custom output directory
  under the source root is skipped automatically.
- `test_arch_awareness.ps1` -- host architecture detection falls back to
  `PROCESSOR_ARCHITECTURE` when `RuntimeInformation` is unavailable.

### Changed

- CI docs now consistently say `ubuntu-22.04` (README, tests README,
  SKILL, CONTRIBUTING).
- CONTRIBUTING fixed the stale 13 / 14 build count, `veloappck` typo,
  pre-commit hook description, and CI job count.
- Smoke count updated to 74 / 74.

### Verified

- `smoke_windows.ps1` -- 74 / 74
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 513 checks
- `test_no_bom.py` -- 172 files, 0 BOM / U+FEFF
- media pipeline -- 11 / 11; selector self-test -- 8 / 8; VK table --
  119 keys / 10 templates
