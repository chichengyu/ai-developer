# 2026-08-06 (round 4) -- Cross-platform Win + macOS + Linux

Scope change: the skill is now **cross-platform desktop** (Windows + macOS +
Linux). iOS / iPadOS / Android remain out of scope (use the
`mobile-app-dev-ios` skill).

### Added -- macOS primitives
- `scripts/sendinput_macos.py` -- Quartz `CGEventPost` via ctypes; no
  PyObjC dependency; USB HID keysym table.
- `scripts/window_enum_macos.py` -- `CGWindowListCopyWindowInfo` via ctypes;
  3 s EnumWindows-style timeout; EWMH-like session cache.
- `scripts/threading_dispatch.swift` -- `Task.detached` + `@MainActor` callback
  pattern with cooperative cancel.
- `scripts/auto_update_sparkle.swift` -- Sparkle 2.x integration.

### Added -- Linux primitives
- `scripts/sendinput_linux.py` -- X11 `XTestFakeKeyEvent` via ctypes; XK_
  keysym table; covers foreground-only X11 sessions.
- `scripts/window_enum_linux.py` -- X11 `XQueryTree` + EWMH `_NET_CLIENT_LIST`
  via ctypes; no python-xlib dependency.
- `scripts/threading_glib.py` -- GTK / GLib `idle_add` bridge pattern with
  lazy gi import.

### Added -- cross-platform packaging
- `scripts/build_macos.ps1` -- dotnet / cargo (Tauri) / xcodebuild wrapper
  with `-Arch x64|arm64` mapping to Apple target triples and RID.
- `scripts/build_linux.ps1` -- dotnet / cargo / go / python wrapper with
  `-Arch x64|arm64`.
- `scripts/build_dmg.sh` -- macOS DMG packaging with codesign + notarytool
  + stapler + hdiutil.
- `scripts/build_appimage.sh` -- Linux AppImage via linuxdeploy.
- `scripts/build_deb.sh` -- Debian .deb via dpkg-deb + fakeroot.
- `scripts/auto_update_appimage.md` -- AppImageUpdate / zsync flow for Linux
  portable distribution.

### Added -- Tier 1 #4 MSIX example (Windows packaging)
- `examples/msix-packaging/` -- complete WPF + WAP project with
  `Package.appxmanifest`, `build_msix.ps1` (dotnet publish + MakeAppx +
  signtool), and sideload instructions.

### Added -- Tier 1 #5 accessibility (R13 closure)
- `scripts/accessibility_uia.py` -- comtypes-based UI Automation client
  with tree walker + predicate filtering.
- `scripts/accessibility_msaa.py` -- no-deps ctypes MSAA reader.
- `references/win32_recipes.md` R13 -- rewritten with priority order
  (UIA > MSAA > SendInput > memory write) and a "when to pick what" table.

### Changed -- SKILL.md
- Scope section rewritten as 3-OS table (Windows / macOS / Linux) with
  versions, default UI stack, input / window-enum API, code-sign tool.
- Out-of-scope table trimmed to iOS / Android / Web / CLI / Server / drivers.
- Architecture support matrix expanded from 11 to 17 build scripts,
  now a 7-column matrix (Win x64/arm64/x86 + macOS x64/arm64 + Linux x64/arm64).
- Deep references unchanged.

### Changed -- tests
- `tests/test_arch_awareness.ps1` extended from 11 to 13 build scripts;
  covers `build_macos.ps1` and `build_linux.ps1`. All 13 pass.

### Verified
- 13 / 13 `build_*.ps1` parse cleanly + have ValidateSet covering x64 +
  arm64 (and x86 where applicable).
- All Python scripts are syntactically valid (no live Linux/macOS host
  available for runtime testing; the macOS/Linux SendInput and window
  enumeration code follows the same ctypes patterns as the Windows
  version which is runtime-tested).
- `tests/test_arch_awareness.ps1` exits 0 on success.
