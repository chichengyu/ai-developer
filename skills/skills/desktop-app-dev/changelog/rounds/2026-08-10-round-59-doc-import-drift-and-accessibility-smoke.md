# 2026-08-10 (round 59) -- Doc import drift + accessibility import smoke

### Added

- `test_docs.py` now scans Markdown `from <script> import <name>` snippets
  and verifies each imported symbol exists in the local script, preventing
  recipes that point at nonexistent APIs.
- Added a `test_main_passes()` pytest entry point so `test_docs.py` is
  collectible by pytest as well as runnable as a script.
- Windows smoke now imports `accessibility_uia.py` and
  `accessibility_msaa.py` (previously AST-only), catching module-level
  import failures. The shared `Test-Import` helper registers modules in
  `sys.modules`, which dataclass-backed templates require.

### Fixed

- `references/accessibility_cross_platform.md` Windows recipe used a
  nonexistent `enumerate_clickable()` helper; it now uses `UIAClient` +
  `walk_tree`.
- Windows smoke count synced to 138 / 138.

### Verified

- `ruff` + `ruff format` + `mypy` pass.
- Windows smoke: 138 / 138.
- Doc audit: 1043 checks; pytest: 15 passed.
- Media pipeline: 95 / 95.
