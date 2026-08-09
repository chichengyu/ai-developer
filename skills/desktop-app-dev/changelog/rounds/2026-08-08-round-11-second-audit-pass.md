# 2026-08-08 (round 11) -- Second audit pass

### Fixed

- `scripts/select_framework.py` -- the flat YAML loader now parses nested
  inline arrays correctly (`target_os: [["windows", "x64"]]`), and
  `--self-test` covers the YAML path.
- `references/win32_recipes.md` -- removed the duplicated R13 section and
  fixed an apostrophe typo.
- `references/framework_matrix.md` -- added the missing Python GTK section,
  matching the 23-framework count advertised by the selector.
- Repo line endings now match `.editorconfig`: `.ps1` / `.bat` / `.cmd` use
  CRLF; all other text files use LF.

### Added

- `tests/test_docs.py` -- line-ending audit for every text file, plus
  duplicate-heading checks for `win32_recipes.md` and a Python GTK
  presence check in the framework matrix.
- `templates/requirements_brief.md` / `references/framework_selection_engine.md`
  -- documented the supported flat YAML shape and the inline-list
  requirement.
