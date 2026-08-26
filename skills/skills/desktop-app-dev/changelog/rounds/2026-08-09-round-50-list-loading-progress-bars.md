# 2026-08-09 (round 50) -- List loading progress bars

### Changed

- PySide6 management example now renders list-loading progress bars as
  0-100% percent progress; the bar appears when a table job starts and is
  hidden after done / failed / cancelled.
- Every list / table page (tasks, dependencies, logs) keeps one visible
  progress bar and reflects the background job's progress signal.
- UI hard requirements and SKILL.md now require every list / table loading
  state to include a progress bar.

### Verified

- `tests/test_pyside6_management.py` checks every page has one table and
  one progress bar, and that the app connects `runner.on("progress")`.
- Windows smoke suite remains green (135 / 135).
