# 2026-08-08 (round 13) -- Client endpoint parity and full PowerShell parse

### Added

- `clients/` -- every wrapper now exposes dependency status, dependency
  progress, and dependency install in addition to enqueue / task lookup:
  C#, Go, Rust, Kotlin, Swift, Java, C++ (TypeScript already had them).
- `tests/smoke_windows.ps1` -- parses every `.ps1` in the skill, including
  `examples/msix-packaging/build_msix.ps1`,
  `examples/winui3-threading/build_winui3.ps1`, and the test scripts.
- `tests/smoke_macos.sh` / `tests/smoke_linux.sh` -- parse every `.ps1`
  when PowerShell is installed instead of a small hand-picked subset.
- `tests/run_lint.ps1` -- only installs ruff / mypy when they are missing,
  and `ruff format --check` now covers scripts, tests, and examples.
- README layout and SKILL deep references now list all 11 reference docs;
  INDEX now covers the full canonical framework list and points macOS /
  Linux accessibility to `references/accessibility_cross_platform.md`.
- `tests/test_docs.py` -- checks reference completeness, INDEX framework
  rows, client endpoint parity, expanded CI format scope, and all-.ps1
  parse coverage.

### Fixed

- `.github/workflows/ci.yml` -- stale "Three jobs" comment now says four
  jobs, and the lint job checks formatting on tests / examples too.
- `clients/README.md` -- capability claim now matches the wrappers.
- `tests/test_docs.py` -- skips generated cache directories (`.mypy_cache`,
  `.ruff_cache`, `__pycache__`, build output) during the line-ending audit.
- `scripts/select_framework.py` -- strips a UTF-8 BOM before parsing the
  brief, so Windows editors that write BOM JSON no longer silently fall
  back to an empty requirements object.
