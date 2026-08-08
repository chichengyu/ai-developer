# INDEX -- find what you need by topic, not by path

This index is **topic-based**, not path-based. If you know the file you
need, use `SKILL.md` instead. If you know the task, use this.

---

## By use case

### Game automation / hardware input (Category A)

You are sending keystrokes (and, in the Windows Python template, mouse
input) to a specific window, possibly with anti-cheat present. Always use
the OS-native "hardware-level" API.

| OS      | Input file                              | Window enum                       |
|---------|------------------------------------------|------------------------------------|
| Windows | `scripts/sendinput_python.py` (or `.cs`, `.c`, `.rs`, `.go`, `.dart`, `.ts`, `.swift`, `.kt`, `.java`) | `scripts/window_enum_python.py` (and the matching `.cs/.rs/...` set) |
| macOS   | `scripts/sendinput_macos.py` (CGEventPost) | `scripts/window_enum_macos.py` (CGWindowListCopyWindowInfo) |
| Linux   | `scripts/sendinput_linux.py` (XTestFakeKeyEvent) | `scripts/window_enum_linux.py` (X11 XQueryTree + EWMH) |

Worked example: `references/task_decomposition.md` -- section "TLBB
game bot" (canonical 9-task DAG with anti-cheat spike).

End-to-end runnable demo: `examples/game-automation/app/app.py` -- a
tkinter GUI that wraps `send_key` + `press_combo` + `WindowFinder`.

### Productivity / business app (Category B)

Form, table, report, dashboard. Pick a framework from
`references/framework_matrix.md`. After picking the framework, see
"By framework" below. Apply `references/ui_hard_requirements.md`
(UI-01..UI-18) before declaring the UI done.

### System / DevOps tool (Category C)

Registry / service / driver / P/Invoke / COM. Start with
`references/win32_recipes.md` (R1-R13 Win32 patterns).

### Accessibility / UI testing (R13 closure)

| Need                                    | Pick                                |
|-----------------------------------------|--------------------------------------|
| Read + drive another app's UI           | `scripts/accessibility_uia.py`       |
| Legacy app without UIA                  | `scripts/accessibility_msaa.py`      |
| Hardware-level input (any Win32 app)    | `scripts/sendinput_python.py` (R1)   |

See `references/win32_recipes.md` R13 for the priority order.
Cross-platform deep dive: `references/accessibility_cross_platform.md`.

### Multimedia / GPU (Category D)

Step 3 variations in `SKILL.md` mention "GPU device enumeration" + "shader /
asset pipeline"; framework matrix lists Vulkan / OpenGL candidates. No
template files ship with the skill for this category -- it is too
domain-specific.

---

## By operating system

### Windows (10 1809+, 11)

- Build: any of 14 `scripts/build_*.ps1` (Tauri, dotnet, NativeAOT,
  Electron, Qt, Python, Go x3, Kotlin, Swift, Neutralino, macOS, Linux).
- SendInput / window: 10-language `sendinput_*` + 9-language
  `window_enum_*` sets (12 files each incl. Java), plus macOS / Linux
  Python variants.
- Threading: `scripts/threading_wpf.cs`, `threading_winui.cs`,
  `threading_tkinter.py`, `threading_pyside6.py`, `threading_tauri.rs`,
  `threading_glib.py`, `threading_dispatch.swift`.
- Packaging: `build_python.ps1`, `build_dotnet.ps1`, `build_electron.ps1`,
  `build_qt.ps1`, plus MSI / NSIS / MSIX / Velopack / Squirrel / WinSparkle.
- DPI: `templates/dpi_manifest.xml` (Per-monitor V2).
- Examples: `examples/{wpf,winui3,tkinter,pyside6,tauri,msix-packaging,nativeaot-winforms,game-automation}/`.

### macOS (11 Big Sur+, Apple Silicon preferred)

- Build: `scripts/build_macos.ps1` (dotnet / cargo / xcodebuild wrapper).
- Packaging: `scripts/build_dmg.sh` (codesign + notarytool + hdiutil).
- SendInput: `scripts/sendinput_macos.py` (CGEventPost via Quartz).
- Window enum: `scripts/window_enum_macos.py`.
- Threading: `scripts/threading_dispatch.swift` (Task.detached +
  @MainActor).
- Auto-update: `scripts/auto_update_sparkle.swift` (Sparkle 2.x).
- Accessibility: UIA is not available on macOS; use the target app's
  own AppleScript / accessibility API. See
  `references/accessibility_cross_platform.md`.

### Linux (glibc 2.31+)

- Build: `scripts/build_linux.ps1` (dotnet / cargo / go / python).
- Packaging: `scripts/build_appimage.sh`, `scripts/build_deb.sh`.
- SendInput: `scripts/sendinput_linux.py` (XTestFakeKeyEvent, X11 only).
- Window enum: `scripts/window_enum_linux.py` (X11 XQueryTree + EWMH).
- Threading: `scripts/threading_glib.py` (GTK / GLib idle_add).
- Auto-update: `scripts/auto_update_appimage.md` (AppImageUpdate / zsync).
- Accessibility: AT-SPI2 (GNOME / KDE). See
  `references/accessibility_cross_platform.md`.

---

## By framework (after language choice)

See `references/framework_matrix.md` for the canonical pros/cons. Once
you have picked one:

| Framework / tool     | Build script              | Threading template           | Example project |
|----------------------|---------------------------|-------------------------------|-----------------|
| WPF (.NET 8)         | `scripts/build_dotnet.ps1` | `scripts/threading_wpf.cs`    | `examples/wpf-threading/` |
| WinForms             | `scripts/build_dotnet.ps1` | `this.Invoke` / `Control.BeginInvoke` | `examples/nativeaot-winforms/` |
| WinUI 3              | `scripts/build_dotnet.ps1` + MSIX | `scripts/threading_winui.cs` | `examples/winui3-threading/` |
| Avalonia / MAUI      | `scripts/build_dotnet.ps1` | `scripts/threading_wpf.cs`    | -- |
| Python tkinter       | `scripts/build_python.ps1` | `scripts/threading_tkinter.py` | `examples/tkinter-threading/` |
| Python PySide6       | `scripts/build_python.ps1` | `scripts/threading_pyside6.py` | `examples/pyside6-threading/` |
| Python GTK           | `scripts/build_python.ps1` | `scripts/threading_glib.py`   | -- |
| Tauri (Rust + Web)   | `scripts/build_tauri.ps1` | `scripts/threading_tauri.rs`   | `examples/tauri-threading/` |
| Electron             | `scripts/build_electron.ps1` | NodeJS worker_threads        | -- |
| Qt 6 (C++)           | `scripts/build_qt.ps1`    | QThread + signals             | -- |
| C++/MFC raw          | -- (uses system CMake)    | std::thread + PostMessage     | -- |
| Go Wails             | `scripts/build_go_wails.ps1` | go func() + RunSafe          | -- |
| Go Fyne              | `scripts/build_go_fyne.ps1` | go func() + fyne.Do           | -- |
| Go Gio               | `scripts/build_go_gio.ps1`  | go func()                     | -- |
| Rust + Slint         | `cargo build --release`      | `std::thread` + channel       | -- |
| Rust + egui          | `cargo build --release`      | `std::thread` + channel       | -- |
| Flutter Desktop      | Flutter SDK (no build script) | `Isolate.spawn` + Stream    | -- |
| JavaFX               | JDK / Gradle (no build script) | `Task` + `Platform.runLater` | -- |
| TornadoFX            | JDK / Gradle (no build script) | `runAsync` + JavaFX thread | -- |
| walk (Go, Win32)     | `go build -ldflags "-H windowsgui"` | `walk.Window.RunSafe` | -- |
| Compose Multiplatform (Kotlin) | `scripts/build_kotlin_compose.ps1` | launch + Dispatchers.Main | -- |
| Swift / SwiftUI      | `scripts/build_swift.ps1` | Task + MainActor              | -- |
| Neutralino.js        | `scripts/build_neutralino.ps1` | (N/A, JS event loop)       | -- |

For tool picker *inside* one language (tkinter vs PySide6, WPF vs
WinUI 3 vs Avalonia), see `templates/gui_framework_decision_tree.md`.

---

## By task

### I need to set up the dev environment

Run `scripts/bootstrap_environment.ps1` with `-Brief brief.json` for
auto framework selection, or `-Framework <key>` for a fixed framework.
Use `-DryRun` first, then `-Install` to install via winget / pip. The
framework-to-toolchain mapping is in `scripts/toolchain_map.json`.
Build helpers accept the same `-Install` opt-in for missing CLIs.

### I need UI / theme consistency

Open `references/ui_hard_requirements.md` -- canonical UI-01..UI-18
checklist, Codex-like default palette, semantic colors, theme library
URLs, settings persistence, log center, and auto-refresh rules.

### I need a media downloader / republisher

Start at `references/media_acquisition_playbook.md`. Use
`scripts/task_queue.py` for SQLite task persistence, then wire in
`media_session.py`, `media_parser.py`, `media_downloader.py`,
`hls_downloader.py`, `captcha_solver.py`, `browser_session.py`,
`ffmpeg_transcoder.py`, and `platform_publisher.py`.
For any other desktop UI language, run `scripts/media_pipeline_service.py`
and use `clients/` wrappers or `references/media_pipeline_clients.md`
to call it over HTTP.
Install the runtime with `scripts/setup_media_dependencies.ps1 -Install`
or `POST /deps/install`.

### I need to package for distribution

| Target            | Script                          |
|-------------------|----------------------------------|
| Windows single-file EXE   | `scripts/build_python.ps1`     |
| Windows .NET single-file  | `scripts/build_dotnet.ps1`     |
| Windows NativeAOT single-file | `scripts/build_dotnet_nativeaot.ps1` |
| Windows installer (NSIS/MSI) | `scripts/build_electron.ps1`, `build_tauri.ps1` |
| Windows MSIX (Store) | `examples/msix-packaging/build_msix.ps1` |
| macOS .app / .dmg   | `scripts/build_macos.ps1` + `scripts/build_dmg.sh` |
| Linux AppImage     | `scripts/build_appimage.sh`      |
| Linux .deb         | `scripts/build_deb.sh`           |

Before any packaging run, create a timestamped source zip with
`scripts/backup_source.ps1`, or pass `-BackupSource` to
`scripts/build_python.ps1` / `scripts/build_dotnet.ps1` so the backup runs
automatically.

### I need to code-sign

| Target    | Tool                                 |
|-----------|--------------------------------------|
| Windows   | `scripts/sign_windows.ps1` or `signtool sign /fd SHA256 ...` |
| macOS     | `scripts/sign_macos.sh` (codesign + notarytool + stapler) |
| Linux deb | `debsigs` (system-installed)         |
| Linux AppImage | per-distro; AppImageUpdate can self-update but the AppImage itself is unsigned |

### I need to add auto-update

| Target    | Channel                                       |
|-----------|-----------------------------------------------|
| Windows   | `scripts/auto_update_velopack.ps1` (any), `auto_update_squirrel.ps1` (.NET/Electron), `auto_update_winsparkle.cpp` (C++/Qt) |
| macOS     | `scripts/auto_update_sparkle.swift`           |
| Linux AppImage | `scripts/auto_update_appimage.md`        |
| Linux deb / rpm | rely on the system package manager      |

### I need to work without internet

Start at `references/restricted_network_playbook.md` (vendoring /
local mirrors / offline caches / single-file fallback).

### I need to enforce multi-architecture builds

Run `tests/test_arch_awareness.ps1` -- verifies every `build_*.ps1`
declares `-Arch` / `-Rid` with the right `ValidateSet`. Currently
14 / 14 pass on Windows x64 (Electron uses `ia32`, NativeAOT is `win-x64`).

---

## Quick "I want X" finder

```
I want to send keystrokes to another app
    --> scripts/sendinput_<your-os>.py
        (Windows: sendinput_python.py / sendinput_win32.c / sendinput_dotnet.cs / ...)

I want to enumerate windows on screen
    --> scripts/window_enum_<your-os>.py
        (Windows: window_enum_python.py / window_enum_dotnet.cs / ...)

I want a runnable demo I can adapt
    --> examples/<closest framework>/

I want to package as EXE / .app / .AppImage
    --> scripts/build_<your-target>.ps1 (or .sh)

I want to keep a source backup before packaging
    --> scripts/backup_source.ps1
        (or -BackupSource on build_python.ps1 / build_dotnet.ps1)

I want offline / no-internet builds
    --> references/restricted_network_playbook.md

I want multi-arch (x64 / arm64 / x86)
    --> -Arch parameter on every build_*.ps1
        (verified by tests/test_arch_awareness.ps1)
        (Electron: ia32; NativeAOT: win-x64 only)

I want CI that runs on all 3 OSes
    --> .github/workflows/ci.yml
        (windows-latest / macos-latest / ubuntu-22.04)

I want to know if I should NOT use this skill
    --> SKILL.md -> "When NOT to use this skill"
        + "Scope and limits" -> Out of scope

I want to extend the skill (add a new framework / language)
    --> INDEX.md (this file) for what to add + tests/test_arch_awareness.ps1
        for the structural check + examples/<new-framework>/ for the
        canonical runnable sample
```
