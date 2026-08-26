# 2026-08-07 (round 2) -- Full audit fixes

### Fixed

- Unified key-hold, foreground-check, and single-side modifier semantics
  across all 10 Windows `sendinput_*` language templates.
- `scripts/sendinput_win32.c` -- removed undefined `holdMs` reference in
  `pressCombo()`.
- `scripts/SendInput.java` -- removed undefined `pair` reference in
  `pressCombo()`.
- `scripts/sendinput_go.go` -- `pressOne()` now passes `nInputs=1` instead
  of `2`.
- Replaced remaining UTF-8 em dashes in PowerShell build scripts.
- Added a source-level regression check to `smoke_windows.ps1` that rejects
  down/up events batched into a single `SendInput` call.
- Aligned CI job counts and lint commands in `tests/README.md` and
  `README.md`.
