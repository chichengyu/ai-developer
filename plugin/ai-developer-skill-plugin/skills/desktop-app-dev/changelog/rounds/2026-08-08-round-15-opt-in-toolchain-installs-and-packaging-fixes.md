# 2026-08-08 (round 15) -- Opt-in toolchain installs and packaging fixes

### Changed

- `build_python.ps1`, `build_tauri.ps1`, `build_electron.ps1`,
  `build_linux.ps1`, `build_macos.ps1`, `build_go_fyne.ps1`, and
  `build_go_wails.ps1` no longer auto-install missing CLIs. Each now
  takes `-Install`; without it, the script prints the exact install
  command and exits non-zero.
- `build_appimage.sh` now supports `aarch64` output and only downloads
  linuxdeploy with `--download`; the fallback rename no longer risks
  moving the linuxdeploy helper into the release artifact.
- `build_deb.sh` accepts an optional `amd64|arm64` package architecture.

### Fixed

- `auto_update_squirrel.ps1` now copies the main EXE into the release
  stage instead of moving (and losing) the original build artifact.
- `auto_update_winsparkle.cpp` converts the app name / version to narrow
  UTF-8 before passing them to WinSparkle, fixing a wide-string compile
  error.
- `build_go_wails.ps1` discovers the built EXE / NSIS installer instead
  of reporting a hardcoded `myapp` path, and `-Clean` also clears
  `build/darwin` as documented.
- `build_dotnet.ps1` reads the project's TFM for the publish-path
  fallback instead of hardcoding `net8.0`.

### Added

- `select_framework.py --self-test` validates the 24 x 27 scoring table,
  display/rationale/language maps, and `toolchain_map.json` coverage.
- `tests/test_docs.py` guards the new invariants: `-Install` gating,
  AppImage/deb architecture support, Squirrel copy semantics, and
  WinSparkle narrow-string API usage.
- `tests/test_media_pipeline.py` now verifies unauthenticated POSTs are
  rejected by the token-protected sidecar.
