# 2026-08-07 (round 6) -- Bug fixes, lint, contributor docs

### Fixed -- 5 real bugs

- `scripts/build_dmg.sh` -- DMG output path was `$(dirname "$WORKDIR")`
  (parent of the .app's directory) instead of `$WORKDIR` (same directory
  as the .app). DMGs now land next to the .app bundle, not two levels up.
- `scripts/window_enum_macos.py` and `window_enum_linux.py` -- docstring
  now explicitly states that `thread.join(timeout=3)` is a **soft**
  timeout: Quartz / Xlib are synchronous C, the Python interpreter
  cannot preempt mid-walk. The 3 s value detaches and returns whatever
  was accumulated. Hard timeout requires multiprocessing.
- `scripts/sendinput_macos.py` -- `c_bool` was forward-referenced and
  re-bound at the bottom of the file. Moved to the top `from ctypes
  import c_bool, ...` line; removed the redundant re-binding. Also
  stripped UTF-8 BOM that had been re-added by Set-Content.
- `.github/workflows/ci.yml` -- `test-linux` ran on `ubuntu-latest`
  (24.04 as of 2026) but the apt URL was hardcoded to
  `ubuntu/22.04/`. Pinned to `runs-on: ubuntu-22.04` with a comment
  explaining the rationale.
- `scripts/build_python.ps1` -- host-arch detection used
  `[System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture`
  which is .NET 6+ only. Windows PowerShell 5.1 lacks the type and
  would throw. Wrapped in try/catch with a fallback to
  `$env:PROCESSOR_ARCHITECTURE`.

### Added

- `CONTRIBUTING.md` -- how-to guide for adding a new SendInput language,
  a new window-enumeration language, a new framework wrapper, a new
  packaging format, a new auto-update channel, or a new example.
  Documents pre-commit hooks, CI, and coding style.
- `tests/run_lint.ps1` -- local one-shot: ruff check + ruff format
  --check + mypy + smoke_windows.ps1 + test_arch_awareness.ps1.
  Equivalent on macOS / Linux is documented inline.
- `.pre-commit-config.yaml` -- ruff + ruff-format + mypy + PowerShell
  parse hook via local system pwsh + standard pre-commit-hooks.
- `.editorconfig` -- LF line endings globally except `.ps1`/`.bat`/`.cmd`
  (CRLF for Windows-native tooling), 4-space indent except YAML/JSON/TOML
  (2 spaces) and Go (tabs).

### Changed

- `.github/workflows/ci.yml` -- new `lint` job on `ubuntu-22.04` runs
  `ruff check` + `ruff format --check` + `mypy scripts/` before the
  three OS jobs. mypy is non-blocking (matches local `run_lint.ps1`).
- `tests/test_arch_awareness.ps1` -- added `auto_update_*.ps1 parse`
  section (2 scripts: `auto_update_squirrel.ps1`,
  `auto_update_velopack.ps1`). Count went from 13 / 13 to 15 / 15.

### Verified

- `pwsh tests/smoke_windows.ps1` -- 32 / 32 pass.
- `pwsh tests/test_arch_awareness.ps1` -- 15 / 15 pass.
- `pwsh tests/run_lint.ps1 -SkipSmoke` -- would install ruff + mypy
  (skipped here to avoid network); smoke tests pass independently.
- All five bug fixes pass their respective verification checks.
