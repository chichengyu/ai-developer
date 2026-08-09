# 2026-08-09 (round 52) -- Dependency URLs are manifest-driven, never hard-coded

### Added

- `templates/dependency_manifest.example.json` -- generic dependency
  manifest template with `url`, `homepage`, `description`, and
  `manual_install` fields to fill in per project.

### Changed

- UI-19 now requires every dependency's official homepage to come from the
  project's `dependencies.json`; application code must not hard-code any
  dependency name or URL.
- `dependency_center.py` and the PySide6 app only read dependency URLs from
  the manifest.
- Tests now fail if `dependency_center.py` or `app.py` contain a hard-coded
  `https://` URL.

### Verified

- `tests/test_dependency_center.py` includes a no-hard-coded-URL check.
- `tests/test_pyside6_management.py` includes the same check for `app.py`.
- `tests/test_docs.py` 912 checks pass.
- Windows smoke suite remains green (135 / 135).
