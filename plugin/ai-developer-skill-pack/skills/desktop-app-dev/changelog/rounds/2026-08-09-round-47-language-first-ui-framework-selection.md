# 2026-08-09 (round 47) -- Language-first UI framework selection

### Added

- `scripts/select_framework.py --language <lang>` lists the recommended
  best UI framework first, then alternatives with pros / cons and
  representative performance for every supported language.
- `templates/gui_framework_decision_tree.md` gains a language-first
  candidate table so users can compare options instead of being forced
  into a language's native UI toolkit.

### Changed

- `SKILL.md` Step 2 now separates "pick language" from "pick UI framework"
  and requires presenting candidates with pros/cons/performance.
- `README.md`, `INDEX.md`, `references/framework_selection_engine.md`, and
  tests document and cover the new `--language` mode.

### Verified

- `select_framework.py --self-test` passes all 8 canonical cases plus
  language-candidate checks.
- `tests/test_docs.py` 905 checks pass.
- `tests/smoke_windows.ps1` 132 / 132 pass.
