# 2026-08-09 (round 49) -- Dependency center help + manual install instructions

### Added

- `dependencies.json` manifests now support `help`, `description`, and
  `manual_install` fields.
- `DependencyCenter.help_text()` returns overall help plus per-dependency
  manual download / install steps.
- PySide6 dependency center adds a read-only `depHelp` panel; selecting a
  row shows that dependency's description and exact manual install steps.

### Changed

- UI-19 and the release checklist require the dependency center to explain
  every dependency and show manual install instructions (download URL,
  target path, restart behavior).
- `tests/test_dependency_center.py` and `test_pyside6_management.py` cover
  the help / manual-install fields.

### Verified

- `tests/test_dependency_center.py` passes.
- `tests/test_pyside6_management.py` 6 / 6 passes.
- Windows smoke suite remains green after the dependency-help additions.
