# Contributing

This skill is meant to be extensible: any Codex agent should be able to
add a new SendInput language, a new framework wrapper, a new example
project, or a new build script. This document is the how-to.

## Repo layout

```
SKILL.md              entry point (8-step workflow)
README.md             quick orientation
CHANGELOG.md          what changed and when
INDEX.md              topic-based navigation
LICENSE               MIT
pyproject.toml        ruff + mypy config
.editorconfig         editor formatting
.gitignore            skill-internal ignores
.pre-commit-config.yaml  pre-commit hooks
.github/workflows/    CI

references/           deep references (read on demand)
templates/            copy-paste starting points
scripts/              SendInput / window_enum / threading / build helpers
examples/             minimal runnable projects (import from ../scripts/)
tests/                smoke tests + fixtures
```

## Adding a new SendInput language

1. Create `scripts/sendinput_<lang>.<ext>` that exports:
   - `send_key(target_id, key_name, hold_ms=50)` -- press + release one key
   - `press_combo(target_id, combo_str, jitter_ms=80)` -- modifier + trigger
   - a `VK` (or equivalent) const-table mapping key names to native codes
2. The signature must match the Windows / macOS / Linux versions in
   `scripts/sendinput_*.py` so the same calling code works on any OS.
3. Honour the 30-80 ms hold and 50-150 ms jitter guidance documented in
   `references/win32_recipes.md` R1.
4. Add a `__main__` block that prints the VK count and a couple of
   sample entries without doing any hardware I/O.
5. Add the new file to `pyproject.toml` `[tool.ruff.lint.per-file-ignores]`
   if your style choices are non-default (e.g. unused `VK` entries).
6. Add a row to the architecture support matrix in
   `references/distribution_playbook.md`.

Smoke coverage is automatic: `tests/smoke_windows.ps1`,
`tests/smoke_macos.sh`, and `tests/smoke_linux.sh` run
`python -c "import ast; ast.parse(...)"` on every `.py` in `scripts/` and
`examples/`. `tests/test_no_bom.py` rejects BOM / U+FEFF bytes.

## Adding a new window-enumeration language

Same pattern as SendInput but export:
- `WindowInfo` dataclass with `hwnd`, `title`, `class_name` (or equivalent)
- `WindowFinder` class with `find(class_name, title_substring)`,
  `list_windows(class_name)`, `invalidate()`
- 3-second timeout (note: this is a **soft** timeout on macOS and Linux
  because the underlying C API is synchronous -- see the timeout caveat
  in the module docstring)
- Session cache keyed by `(class_name, title_substring)`

## Adding a new framework

1. Add a `scripts/build_<framework>.ps1` (or `.sh`) that accepts
   `-Arch x64|arm64|x86` (or the framework's native equivalent) with
   a `[ValidateSet(...)]`. See the existing 14 `build_*.ps1` files.
2. If the framework uses a threading model not covered by the existing
   `threading_*` templates, add a new
   `scripts/threading_<framework>.<ext>`.
3. Add a deep-dive section to `references/framework_matrix.md` and a
   canonical framework entry to `scripts/select_framework.py`.
4. Add the script to `tests/test_arch_awareness.ps1` so the
   `-Arch` / `-Rid` parameter is structurally verified on every PR.
5. Optionally add `examples/<framework>-threading/` so users have a
   runnable starting point.

## Adding a new example project

1. Create `examples/<purpose>-<framework>/`.
2. The example must import from `../../scripts/` (or `../../` then
   `scripts/`) -- do NOT duplicate SendInput / WindowFinder / threading
   templates. The single source of truth lives in `scripts/`.
3. Include a `README.md` with: prerequisites, run command, package
   command (referencing `scripts/build_*.ps1`).
4. Python examples get automatic AST smoke coverage; add a behavioral
   smoke-test entry only when the example needs runtime checks.

## Adding a new packaging format

1. Add a `scripts/build_<format>.ps1` or `.sh`.
2. Reference it from the "Packaging" section of `INDEX.md` (By task
   -> "I need to package for distribution").
3. If the format is OS-specific, add a row to the architecture support
   matrix in `references/distribution_playbook.md`.

## Adding a new auto-update channel

1. Add a `scripts/auto_update_<channel>.{ps1,cpp,swift,...}` that
   matches the existing `auto_update_velopack.ps1` /
   `auto_update_squirrel.ps1` / `auto_update_winsparkle.cpp` /
   `auto_update_sparkle.swift` / `auto_update_appimage.md` API surface
   (init, check, shutdown, apply).
2. Add a row to the INDEX "By task -> I need to add auto-update".
3. If the channel covers an OS not already covered, ensure the channel
   is referenced from `SKILL.md` step 5.3.

## Pre-commit checks

```bash
pip install ruff pre-commit
pre-commit install
pre-commit run --all-files
```

The hooks run:
- trailing-whitespace / end-of-file / merge-conflict checks
- YAML, JSON, TOML, and XML validity
- `ruff check` and `ruff format --check`
- `mypy scripts/`
- PowerShell parse for every `.ps1`

Smoke tests are not a pre-commit hook. Run `tests/run_lint.ps1`
(check-only by default) or the CI jobs after changes.

## CI

Every push to `main` and every PR runs `.github/workflows/ci.yml`,
which has four jobs (lint plus three smoke jobs):

- `lint` on `ubuntu-22.04`
- `test-windows` on `windows-latest`
- `test-macos` on `macos-latest`
- `test-linux` on `ubuntu-22.04`

Smoke jobs install Python 3.12 + PowerShell where needed, then run the
matching smoke test (`tests/smoke_windows.ps1` / `smoke_macos.sh` /
`smoke_linux.sh`). Failure artifacts upload for 7 days.

## Versioning

This skill does not currently use semantic versioning. Each meaningful
change is recorded in `CHANGELOG.md` with a "round" header (Round 1,
Round 2, ...). When the skill reaches 1.0, we will switch to SemVer
tags.

## Coding style

- Python: ruff config in `pyproject.toml`. Target Python 3.10+ (matches
  the Codex runtime).
- SKILL.md is the only file auto-loaded into context. Keep it slim:
  put detailed tables, recipes, and matrices in `references/`, then add
  a one-line pointer from SKILL.md.
- PowerShell: target Windows PowerShell 5.1 AND PowerShell 7+ (no
  ternary operator from PS7 only). Use `[CmdletBinding()]`,
  `[Parameter(Mandatory)]`, `[ValidateSet(...)]` for new scripts.
- C#: target .NET 8. Use nullable reference types.
- Bash: `set -euo pipefail` at the top of every new `.sh`.
- Swift: Swift 5.9+, target SwiftUI on macOS where possible.
- Rust: edition 2021.

## Reporting issues

Open an issue against the repo and tag:
- `[bug]` -- something that used to work
- `[new-framework]` -- a framework you want supported
- `[docs]` -- unclear / outdated docs
- `[rfc]` -- significant design change
