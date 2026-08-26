# 2026-08-09 (round 51) -- Clickable dependency URLs + list progress bars

### Added

- Dependency manifests now support an official `homepage` field per dependency.
- Dependency center help panel is a `QTextBrowser` with external links:
  the official website URL is clickable and opens in the browser.
- `DependencyCenter` includes `homepage` in status/install results and
  `help_text()` renders `官网：<homepage>` for every dependency.

### Changed

- UI-19 requires every dependency entry to show its official website URL
  as a clickable link.
- Every list / table page keeps a loading progress bar; tests now assert
  the number of tables equals the number of progress bars.
- PySide6 example help panel and manual-install text use clickable links.

### Verified

- `tests/test_dependency_center.py` covers `homepage` and clickable help text.
- `tests/test_pyside6_management.py` checks `QTextBrowser`,
  `openExternalLinks`, and one progress bar per table.
- Windows smoke suite remains green (135 / 135).
