# 2026-08-10 (round 61) -- Cross-platform smoke parity

### Fixed

- `smoke_macos.sh` and `smoke_linux.sh` now run
  `test_pyside6_management.py` and `test_dependency_center.py` alongside
  the other Python structural tests, matching Windows smoke coverage.
- `test_docs.py` now verifies all three smoke suites invoke the same set
  of Python structural/media test files, so the suites cannot drift again.

### Verified

- Windows smoke: 138 / 138.
- Doc audit: 1048 checks; pytest: 110 passed.
- `ruff` + `ruff format` pass; `bash -n` passes for both shell smokes.
