# 2026-08-09 (round 48) -- Dependency center: list all deps, one-click install

### Added

- `scripts/dependency_center.py` -- manifest-driven dependency center:
  reads `dependencies.json`, lists every runtime dependency as menu rows,
  checks status, and installs all missing items with chunked / resumable
  downloads and live progress.
- `examples/pyside6-management/assets/dependencies.json` -- canonical
  dependency manifest used by the PySide6 dependency center page.
- `tests/test_dependency_center.py` -- local HTTP regression that lists a
  missing dependency and installs it with checksum verification.

### Changed

- PySide6 example dependency page now reads the manifest and lists all
  runtime dependencies; the user only clicks `安装依赖`.
- UI-19 hard requirement now states that every shipped app must show all
  runtime dependencies in a dependency center menu and auto-download /
  install / configure them with chunked, resumable downloads.
- `SKILL.md`, `README.md`, `INDEX.md`, release/requirements checklists,
  and `references/media_acquisition_playbook.md` document the new flow.

### Verified

- `tests/test_dependency_center.py` 1 / 1 passes (manifest list + install).
- `select_framework.py --self-test`, `test_docs.py`, and the Windows
  smoke suite pass with the dependency-center additions.
- `tests/test_docs.py` 911 checks pass.
- `tests/smoke_windows.ps1` 135 / 135 pass.
