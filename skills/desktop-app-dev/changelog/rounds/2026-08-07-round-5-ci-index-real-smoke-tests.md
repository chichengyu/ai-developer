# 2026-08-07 (round 5) -- CI, INDEX, real smoke tests

### Added
- `INDEX.md` -- topic-based navigation (by use case / OS / framework /
  task) complementing the path-based `SKILL.md`.
- `tests/smoke_windows.ps1` -- 32-check smoke test for Windows. Runs
  PowerShell parse on every `build_*.ps1` + `auto_update_*.ps1`, Python
  imports, fixture validity, arch awareness, and Python AST parse for
  all scripts/*.py. Pass: 32 / 32.
- `tests/smoke_macos.sh` -- macOS smoke: bash syntax for `build_dmg.sh`
  (and others), PowerShell parse via brew pwsh, Python AST + const-table
  for `sendinput_macos.py` (validates `lcmd`, `f5`, etc.) and
  `window_enum_macos.py`, Swift `-parse` if toolchain present.
- `tests/smoke_linux.sh` -- Linux smoke: bash syntax for AppImage + deb
  scripts, PowerShell parse via apt pwsh, Python AST + const-table for
  `sendinput_linux.py` (validates `control_l`, `super_l`, etc.),
  `window_enum_linux.py`, `threading_glib.py`.
- `.github/workflows/ci.yml` -- three-job matrix on
  `windows-latest` / `macos-latest` / `ubuntu-latest`. Each job
  installs Python 3.12 + PowerShell, runs the matching smoke test,
  uploads logs on failure (7-day retention).

### Changed
- `tests/README.md` rewritten to document the new smoke tests, the
  arch-awareness test, and the CI matrix.
- `tests/test_arch_awareness.ps1` already covered `build_macos.ps1`
  and `build_linux.ps1`; no change.
- `SKILL.md` "Deep references" now lists `INDEX.md`.
- `SKILL.md` "Tests" section expanded to list all smoke scripts and
  the CI workflow.
- `README.md` adds "CI / continuous testing" + "Index" sections.

### Verified locally
- `pwsh tests/smoke_windows.ps1` -- 32 / 32 pass on Windows.
- `tests/test_arch_awareness.ps1` -- 13 / 13 pass.
- YAML parse -- `.github/workflows/ci.yml` has all required keys.

### Out of scope
- Live runtime testing of `sendinput_macos.py` /
  `window_enum_macos.py` / `sendinput_linux.py` / `window_enum_linux.py`
  still requires a GUI session on those hosts. Smoke tests verify AST
  + const-table + script import sanity, not actual Quartz / X11 calls.
