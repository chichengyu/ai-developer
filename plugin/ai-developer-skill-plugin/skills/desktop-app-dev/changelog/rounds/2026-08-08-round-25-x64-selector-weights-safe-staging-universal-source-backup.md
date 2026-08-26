# 2026-08-08 (round 25) -- x64 selector weights, safe staging, universal source backup

### Fixed

- `scripts/select_framework.py` -- architecture weighting now distinguishes
  `macos-x64` / `linux-x64` from arm64. `macos x64` no longer weights
  `macos_arm64_arch`, Linux x64 now scores per-arch instead of being
  ignored, and all seven architecture dimensions have human-readable labels.
- `scripts/build_qt.ps1` -- refuses to remove a staging directory that
  overlaps the project source, and supports `-BackupSource`.
- `scripts/build_appimage.sh` / `scripts/build_deb.sh` -- stage in a private
  `mktemp` directory instead of deleting user-visible `AppDir` / `stage_*`
  folders; the AppImage header no longer claims linuxdeploy is downloaded
  by default.
- `scripts/bootstrap_environment.ps1` -- dry-run only prints the pip command
  when Python is actually available, otherwise reports that Python must be
  installed first.

### Added

- `-BackupSource` is now supported by all 14 `scripts/build_*.ps1` helpers,
  not just `build_python.ps1` / `build_dotnet.ps1`.
- `tests/test_docs.py` -- duplicate `##` heading audit, selector x64
  dimension checks, all-build-script `-BackupSource` wiring checks,
  `build_qt.ps1` staging guard, and bootstrap dry-run consistency
  (623 checks).
- `tests/smoke_windows.ps1` -- checks every build helper exposes
  `-BackupSource` and that `build_qt.ps1` protects source staging (86 / 86).

### Verified

- `smoke_windows.ps1` -- 86 / 86
- `test_docs.py` -- 623 checks
- `test_no_bom.py` -- 181 files, 0 BOM / U+FEFF
- media pipeline -- 42 / 42; arch awareness -- 16 / 16
- selector self-test -- 8 / 8 canonical cases + arch-weight assertions
  (24 x 29)
- ruff check, ruff format --check, mypy scripts/ -- all green
