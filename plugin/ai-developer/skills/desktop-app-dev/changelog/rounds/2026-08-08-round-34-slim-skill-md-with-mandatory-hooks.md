# 2026-08-08 (round 34) -- Slim SKILL.md with mandatory hooks

### Changed

- `SKILL.md` -- compressed from 25,529 to 16,264 bytes. UI-01..18 keep a
  compact ID/requirement table; full acceptance criteria stay in
  `references/ui_hard_requirements.md`. Media/web script lists became
  compact scenario indexes with all script paths retained.
- Mandatory application hooks kept: MUST open
  `references/ui_hard_requirements.md` before UI work, MUST open
  `references/minimal_change_requirements.md` before code changes, Step 0
  records UI-01..18 + CODE-01..05, Step 4.5 applies both, Step 6 verifies
  both.

### Tests

- `tests/test_docs.py` now guards the mandatory-open hooks and the
  Step 0 UI+CODE recording rule.

### Verified

- test_docs.py -- 789 checks
- test_no_bom.py -- 215 files, 0 BOM / U+FEFF
- smoke_windows.ps1 -- 110 / 110
- ruff check / ruff format --check -- green
- SKILL.md -- 16,264 bytes
