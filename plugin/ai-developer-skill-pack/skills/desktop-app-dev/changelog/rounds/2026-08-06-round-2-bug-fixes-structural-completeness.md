# 2026-08-06 (round 2) -- Bug fixes + structural completeness

### Fixed -- Round 1 (4 real bugs that earlier "perfect" claim missed)

- `scripts/auto_update_winsparkle.cpp` -- WinSparkle takes **narrow** URL
  strings. Replaced `feedUrl.c_str()` (wide) with `to_narrow(feedUrl)`
  using `WideCharToMultiByte(CP_UTF8, ...)`.
- `scripts/window_enum_node.ts` -- Worker branch referenced `shimFuncs!`
  without ever loading the shim in the worker context. Added the same
  shim-load logic inside the worker before calling `enum`.
- `scripts/sendinput_kotlin.kt` -- `cbSize` was computed by
  `Input::class.java.superclass.let { 40 }` (coincidentally right on x64
  but semantically wrong). Replaced with `Native.getNativeSize(Input::class.java)`.
- `scripts/window_enum_swift.swift` -- Cancellation flag was non-atomic
  `NSMutableData.isEmpty`, callback ran on a worker thread. Replaced with
  a `Holder` class exposing `var snapshot: Bool` protected by `NSLock`,
  and added `resultsLock` for the `results` array.

### Added -- Round 2 (structural completeness)

- SKILL.md -- new "When NOT to use this skill" section with 7 explicit
  anti-triggers (CLI / web / mobile / single-purpose script / framework
  comparison / console subsystem / framework locked-in).
- `examples/` -- 5 minimal runnable projects:
  - `wpf-threading/`  (C# WPF, links `scripts/threading_wpf.cs`)
  - `tkinter-threading/`  (Python, imports `scripts/threading_tkinter.py`)
  - `pyside6-threading/`  (Python, imports `scripts/threading_pyside6.py`)
  - `tauri-threading/`  (Rust + Web, real `src-tauri/` + `src/`)
  - `game-automation/`  (TLBB-style: window + SendInput + threading)
- `.gitignore` -- PyInstaller / Cargo / .NET / Node / IDE artefacts.
- `LICENSE` -- MIT.
- `pyproject.toml` -- ruff + mypy config; selectable rules
  E/W/F/I/B/UP/SIM; per-file ignores for the dynamic-import parts.
