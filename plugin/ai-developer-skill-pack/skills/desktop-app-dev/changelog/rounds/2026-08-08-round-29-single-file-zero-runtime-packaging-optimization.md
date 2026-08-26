# 2026-08-08 (round 29) -- Single-file zero-runtime packaging optimization

### Added

- `scripts/build_python.ps1` -- `--noupx` and safe `-ExcludeModules`
  defaults, plus a printed EXE size report.
- `scripts/build_dotnet.ps1` -- compression on / symbols off by default,
  ReadyToRun and trimming are now opt-in, invariant globalization default.
- `scripts/build_dotnet_nativeaot.ps1` -- invariant globalization and no
  debug symbols, keeping NativeAOT as the smallest .NET path.
- `scripts/build_qt.ps1` -- minimal `windeployqt` flags
  (`--no-translations --no-system-d3d-compiler --no-opengl-sw
  --no-compiler-runtime`) and portable-folder size report.
- `scripts/build_tauri.ps1` -- NSIS single-installer default and automatic
  size-lean Rust release profile via Cargo env vars, with artifact size
  reporting.
- `scripts/build_electron.ps1` -- `compression=maximum`, `asar`, and a
  clear warning that Electron is the wrong default for small size / RAM.
- Go helpers (`build_go_wails.ps1`, `build_go_fyne.ps1`,
  `build_go_gio.ps1`) -- stripped binaries, hidden console, and
  `-trimpath -buildvcs=false` by default.
- `scripts/build_swift.ps1` -- `-Osize` default and EXE size report.
- `scripts/build_macos.ps1` / `build_linux.ps1` -- same compression /
  symbol / Rust-profile defaults for dotnet, cargo, go, and python paths.
- Docs: `references/distribution_playbook.md` size / memory table and
  per-framework flags; SKILL.md Step 5/6 single-file and idle-memory gates;
  README / INDEX quick recipes; `templates/release_checklist.md` gates.
- Tests: 10 new packaging-optimization regression checks in
  `tests/smoke_windows.ps1` plus matching doc-audit terms.

### Verified

- smoke_windows.ps1 -- 103 / 103
- test_docs.py -- 683 checks
- media pipeline -- 56 / 56
- test_no_bom.py -- 188 files, 0 BOM / U+FEFF
- select_framework.py -- self-test pass
- ruff check / ruff format --check / mypy scripts/ -- all green
