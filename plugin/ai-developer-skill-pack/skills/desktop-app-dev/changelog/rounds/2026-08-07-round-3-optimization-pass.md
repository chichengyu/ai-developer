# 2026-08-07 (round 3) -- Optimization pass

### Added

- `scripts/select_framework.py --self-test` now runs inside
  `tests/smoke_windows.ps1`.
- `tests/test_docs.py` -- structural doc audit for frontmatter, duplicate
  sections, relative references, and advertised file counts.
- `scripts/vk_table.json` + `scripts/check_vk_tables.py` -- canonical key
  table with an automated Python reference check.
- Mouse helpers (`move_mouse`, `click`, `scroll`) in
  `scripts/sendinput_python.py`.
- Flutter, Slint, egui, and TornadoFX entries in `select_framework.py`,
  bringing the selector to 23 canonical frameworks.
- `scripts/sign_windows.ps1` and `scripts/sign_macos.sh` code-signing
  helpers.

### Changed

- `tests/smoke_windows.ps1` and `tests/run_lint.ps1` now honor
  `CODEX_PYTHON` before falling back to the bundled Codex runtime.
- Docs now distinguish randomized Python jitter from fixed jitter in the
  other language templates.
- Removed generated Python `__pycache__` cache files from `scripts/`.

### Fixed

- `examples/game-automation/app/app.py` -- corrected `SKILL_ROOT` parents
  depth so the example can actually import `scripts/`.
