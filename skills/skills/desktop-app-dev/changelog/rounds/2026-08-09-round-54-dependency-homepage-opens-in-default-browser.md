# 2026-08-09 (round 54) -- Dependency homepage opens in default browser

### Changed

- PySide6 dependency center now handles `anchorClicked` explicitly and
  opens the dependency `homepage` with `QDesktopServices.openUrl()`, which
  uses the system's default external browser.
- UI-19 and the release checklist require homepage links to open in the
  default external browser, not inside the app.

### Verified

- `tests/test_pyside6_management.py` checks `QDesktopServices`,
  `openUrl`, `anchorClicked`, and the handler wiring.
- Windows smoke suite remains green (135 / 135).
