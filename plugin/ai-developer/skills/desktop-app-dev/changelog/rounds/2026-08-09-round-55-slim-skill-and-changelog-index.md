# 2026-08-09 (round 55) -- Slim SKILL + changelog index

### Changed

- `CHANGELOG.md` is now a short index; the full index lives in
  `changelog/INDEX.md` and each round in `changelog/rounds/`.
- `SKILL.md` reduced from ~20 KB to ~12 KB by moving details into
  references and keeping only the compact workflow index.
- `test_docs.py` now requires SKILL.md to point to the UI reference
  instead of embedding the full UI table.

### Verified

- `SKILL.md` ~12 KB (~3k tokens); `CHANGELOG.md` ~2.5 KB.
- `tests/test_docs.py` 1022 checks pass.
- Windows smoke suite remains green (135 / 135).
