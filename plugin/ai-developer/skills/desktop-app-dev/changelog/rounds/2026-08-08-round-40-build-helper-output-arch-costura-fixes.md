# 2026-08-08 (round 40) -- Build helper output/arch/Costura fixes

### Fixed

- `scripts/build_linux.ps1` now honors `-OutputDir` for both Go and
  PyInstaller branches; Go creates the output directory before building,
  and PyInstaller writes through `--distpath` / `--workpath` / `--specpath`
  instead of dumping into `./dist`.
- `scripts/build_electron.ps1` now passes
  `-c.directories.output=$OutputDir` to electron-builder and scans the
  configured directory instead of hardcoded `dist`.
- `scripts/build_dotnet.ps1` no longer treats `-Costura` as a silent
  no-op: it validates the project references `Costura.Fody` and has
  `FodyWeavers.xml`, and explains the requirement when missing.
- `scripts/build_kotlin_compose.ps1` warns when `-Arch` differs from the
  host because Compose Desktop packaging is host-bound.
- `scripts/build_macos.ps1` no longer uses PowerShell-7-only
  `Split-Path -LeafBase`; scheme names now resolve with
  `GetFileNameWithoutExtension()`.

### Docs

- `references/ui_hard_requirements.md` adds heavy desktop data /
  performance rules under UI-18: virtualization or paging for long
  lists/grids, data-layer filtering, layered architecture, and 100k-row
  verification before release.

### Tests

- `tests/smoke_windows.ps1` adds 5 static regression checks for the fixes
  above and `tests/test_docs.py` locks the new heavy-desktop terms;
  119/119 pass.
