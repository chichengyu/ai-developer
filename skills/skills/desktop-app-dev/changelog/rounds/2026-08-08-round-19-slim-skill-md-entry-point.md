# 2026-08-08 (round 19) -- Slim SKILL.md entry point

### Changed

- `SKILL.md` reduced from 40 KB / 723 lines to 21 KB / 301 lines. The
  workflow, scope gates, UI-01..UI-18, step rules, references, templates,
  examples, and tests remain in the entry point.
- Quick decision tree, threading bridge table, and resource embedding
  table moved to `references/framework_matrix.md`.
- Distribution-first override and the full architecture support matrix
  moved to `references/distribution_playbook.md`.
- `tests/test_docs.py` now excludes utility sections from the
  framework-matrix heading count so the 24 framework sections stay
  structurally verified.
- README / CONTRIBUTING document the "SKILL.md stays slim; details live
  in references" convention.
- `tests/test_docs.py` now fails if `SKILL.md` grows above 25 KB, keeping
  the entry point context-light.
- Fixed stale "matrix in SKILL.md" wording in
  `references/framework_matrix.md`, `references/framework_selection_engine.md`,
  `INDEX.md`, and `CONTRIBUTING.md`.

### Verified

- `smoke_windows.ps1` -- 77 / 77
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 530 checks
- `test_no_bom.py` -- 173 files, 0 BOM / U+FEFF
- media pipeline -- 15 / 15; selector self-test -- 8 / 8; VK table --
  119 keys / 10 templates
