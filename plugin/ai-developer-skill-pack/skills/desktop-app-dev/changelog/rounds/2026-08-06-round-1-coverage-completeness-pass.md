# 2026-08-06 (round 1) -- Coverage completeness pass

Filled every gap called out in the skill self-audit.

### Added -- build scripts
- `scripts/build_qt.ps1` -- C++/Qt 6 + windeployqt + cpack NSIS/WIX.
- `scripts/build_electron.ps1` -- electron-builder NSIS / MSI / portable.
- `scripts/build_python.ps1` -- auto-resolves Python from `-PythonExe`,
  `CODEX_PYTHON` / `PYTHON` env vars, Codex primary runtime, or PATH.

### Added -- threading templates
- `scripts/threading_tkinter.py`, `threading_pyside6.py`,
  `threading_tauri.rs`.

### Added -- SendInput / window enumeration
- `scripts/sendinput_swift.swift`, `scripts/sendinput_kotlin.kt`,
  matching `window_enum_*` pair, plus `window_enum_node_shim.cc` and a
  rewritten `window_enum_node.ts`.

### Added -- auto-update implementations
- `scripts/auto_update_velopack.ps1`,
  `scripts/auto_update_squirrel.ps1`,
  `scripts/auto_update_winsparkle.cpp`.

### Added -- templates + tests
- `templates/dpi_manifest.xml`,
  `templates/gui_framework_decision_tree.md`,
  `tests/README.md`,
  `tests/fixtures/{sample.md, sample_config.json, AppxManifest.xml}`.

### Changed
- `SKILL.md` -- description, build-script list, threading line, auto-update
  cross-references, "Templates" + "Deep references" + new "Tests" sections.
- `references/framework_matrix.md` -- removed duplicate
  "Quick verdict by user persona" block at the tail.
