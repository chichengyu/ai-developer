# 2026-08-10 (round 60) -- Correct VK/F-key tables + macOS keycodes

### Fixed

- Windows `sendinput_*` templates and `vk_table.json` mapped F1-F24 one
  key too low (F1 was VK_DIVIDE 0x6F instead of VK_F1 0x70). Fixed Python,
  C#, Java, Rust, Go, Dart, Node, Swift, and Kotlin templates plus the
  canonical JSON; the C template already used `VK_F1 + n - 1`.
- `sendinput_macos.py` used USB HID usage codes with CGEventPost, which
  expects Carbon virtual keycodes. Replaced the table with `kVK_*` values
  for F1-F12, letters, digits, navigation, modifiers, and forward delete.
- `sendinput_linux.py` XK table flattened from dict comprehensions to a
  literal so smoke tests can assert exact keysym values.

### Added

- `check_vk_tables.py` now anchors F1=0x70 / F24=0x87 and verifies every
  Windows template starts its F-key mapping at VK_F1.
- `smoke_macos.sh` and `smoke_linux.sh` now assert representative keycode
  values (kVK_F1/left/delete/command/return; XK_F5/left/return/control_l).

### Verified

- Windows smoke: 138 / 138; media pipeline: 95 / 95.
- Doc audit: 1045 checks; pytest: 15 passed.
- `ruff` + `ruff format` + `mypy` pass; `bash -n` for both shell smokes.
