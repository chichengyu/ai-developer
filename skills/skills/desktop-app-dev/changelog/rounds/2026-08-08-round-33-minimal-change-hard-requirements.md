# 2026-08-08 (round 33) -- Minimal-change hard requirements

### Added

- `SKILL.md` -- `代码开发硬性要求（minimal-change hard requirements）`
  compact rule set: keep working original logic, minimal diff, explicit
  waiver; full CODE-01..CODE-05 checklist moved to
  `references/minimal_change_requirements.md`.
- `references/minimal_change_requirements.md` -- canonical CODE-01..CODE-05
  rules with acceptance criteria and decision rules.
- `templates/requirements_checklist.md` and `templates/release_checklist.md`
  now carry CODE-01..CODE-05 record/waiver and release gates.
- `tests/test_docs.py` -- structural checks for the CODE-01..CODE-05
  heading, reference file, template wiring, and README/INDEX coverage.

### Docs

- `SKILL.md` Step 4.5 and Step 6 now apply CODE-01..CODE-05 to all code
  changes; `README.md` and `INDEX.md` document the minimal-change rules.

### Verified

- test_docs.py -- 786 checks
- test_no_bom.py -- 215 files, 0 BOM / U+FEFF
- SKILL.md size -- 25,529 bytes (<= 25 KiB)
