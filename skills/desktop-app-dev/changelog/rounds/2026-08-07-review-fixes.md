# 2026-08-07 -- Review fixes

### Fixed

- `SKILL.md` frontmatter and tail corruption; restored the framework
  selection engine section and removed duplicated test lists.
- `scripts/sendinput_python.py` -- real key hold semantics, foreground
  failure raises instead of sending to the wrong window, randomized
  jitter range, and single-side modifier aliases.
- `scripts/sendinput_macos.py` / `sendinput_linux.py` -- randomized jitter
  range and keyboard-only docs (mouse is not implemented).
- `scripts/window_enum_python.py` -- `HWND` / `LPARAM` callback types and
  explicit argtypes for 64-bit correctness.
- `examples/game-automation/` -- enumeration and key sends now run on
  `TkBackgroundTask`; unused imports removed.
- `tests/test_arch_awareness.ps1` -- now covers `build_dotnet_nativeaot.ps1`
  and Electron's `ia32` architecture value.
- Aligned framework/language/example counts across `SKILL.md`, `README.md`,
  `INDEX.md`, `examples/`, and `tests/`.
- Removed UTF-8 BOM from 58 files.
