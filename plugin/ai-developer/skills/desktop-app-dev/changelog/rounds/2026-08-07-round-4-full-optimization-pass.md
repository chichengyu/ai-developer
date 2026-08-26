# 2026-08-07 (round 4) -- Full optimization pass

### Added

- Randomized 50-150 ms jitter by default in every `sendinput_*` language
  template; pass an explicit positive `jitterMs` to force a fixed delay.
- Canonical `scripts/vk_table.json` reference comments in all language
  templates.
- `check_vk_tables.py` now validates all 10 Windows language templates
  against the canonical JSON, not just Python.
- `tests/fixtures/csharp-smoke/` and an optional `dotnet build` check in
  `smoke_windows.ps1`.

### Fixed

- `scripts/sendinput_macos.py` -- missing `c_uint16` import.
- `scripts/window_enum_macos.py` -- moved missing `c_uint32` / `c_void_p`
  imports to the top.
- Added missing special VK keys (`select`, `print`, `execute`,
  `snapshot`, `help`, numpad extras) to C, C#, Java, Rust, Go, Dart,
  Node, Kotlin, and Swift templates.
- Full `ruff check` cleanup (128 findings) and `mypy scripts/` cleanup
  (10 findings); both now pass locally.
