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
(UI-01..UI-19) before declaring the UI done.

### Heavy desktop / data-dense app (Category B/C/D)

Data-heavy, multi-window, long-lived, or enterprise apps start with
`references/heavy_desktop_playbook.md`: layered architecture + DI,
virtualization or paging, persistent long-running jobs, startup/memory
profiling, stability, and 100k-row acceptance. Copy
`templates/heavy_desktop_acceptance.md` into requirements.md and measure
with `scripts/heavy_desktop_verify.ps1 -AppPath <exe> -SampleSeconds 60`.

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
asset pipeline"; framework matrix lists Vulkan / OpenGL candidates. For
media download / transcode / conversion work, the media pipeline ships
ready templates: `media_session.py`, `media_downloader.py`,
`hls_downloader.py`, `ffmpeg_transcoder.py`, `media_formats.py`, and
`file_converter.py` (see "I need a media downloader / republisher").

---

## By operating system

### Windows (10 1809+, 11)

- Build: any of 14 `scripts/build_*.ps1` (Tauri, dotnet, NativeAOT,
  Electron, Qt, Python, Go x3, Kotlin, Swift, Neutralino, macOS, Linux).
- SendInput / window: 10-language `sendinput_*` + 9-language
  `window_enum_*` sets (12 files each incl. Java), plus macOS / Linux
  Python variants.
- Threading: 30 `scripts/threading_*` files (22 single-worker + 8 bounded
  pool templates) covering WPF, WinUI 3, WinForms, Avalonia, MAUI, Qt,
  Tauri, Electron, tkinter, PySide6, GTK, SwiftUI, JavaFX, Compose,
  Flutter, Go, Rust, and Win32. Full mapping:
  `references/threading_playbook.md`.
- Packaging: `build_python.ps1`, `build_dotnet.ps1`, `build_electron.ps1`,
  `build_qt.ps1`, plus MSI / NSIS / MSIX / Velopack / Squirrel / WinSparkle.
- DPI: `templates/dpi_manifest.xml` (Per-monitor V2).
- Examples: `examples/{wpf,winui3,tkinter,pyside6,tauri,msix-packaging,nativeaot-winforms,game-automation,media-toolkit}/`.

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
| Avalonia             | `scripts/build_dotnet.ps1` | `scripts/threading_avalonia.cs` | -- |
| .NET MAUI            | `scripts/build_dotnet.ps1` | `scripts/threading_maui.cs`    | -- |
| Python tkinter       | `scripts/build_python.ps1` | `scripts/threading_tkinter.py` | `examples/tkinter-threading/` |
| Python PySide6       | `scripts/build_python.ps1` | `scripts/threading_pyside6.py` | `examples/pyside6-threading/` |
| Python GTK           | `scripts/build_python.ps1` | `scripts/threading_glib.py`   | -- |
| Tauri (Rust + Web)   | `scripts/build_tauri.ps1` | `scripts/threading_tauri.rs`   | `examples/tauri-threading/` |
| Electron             | `scripts/build_electron.ps1` | `scripts/threading_electron.ts` + worker | -- |
| Qt 6 (C++)           | `scripts/build_qt.ps1`    | `scripts/threading_qt.cpp`      | -- |
| C++/MFC raw          | -- (uses system CMake)    | `scripts/threading_win32.c`     | -- |
| Go Wails             | `scripts/build_go_wails.ps1` | `scripts/threading_go_wails.go` | -- |
| Go Fyne              | `scripts/build_go_fyne.ps1` | `scripts/threading_go_fyne.go`  | -- |
| Go Gio               | `scripts/build_go_gio.ps1`  | goroutine + channel (see playbook) | -- |
| Rust + Slint         | `cargo build --release`      | `scripts/threading_rust_slint.rs` | -- |
| Rust + egui          | `cargo build --release`      | `scripts/threading_rust_egui.rs` | -- |
| Flutter Desktop      | Flutter SDK (no build script) | `scripts/threading_flutter.dart` | -- |
| JavaFX               | JDK / Gradle (no build script) | `scripts/threading_javafx.java` | -- |
| TornadoFX            | JDK / Gradle (no build script) | `scripts/threading_javafx.java` | -- |
| walk (Go, Win32)     | `go build -ldflags "-H windowsgui"` | `scripts/threading_go_walk.go` | -- |
| Compose Multiplatform (Kotlin) | `scripts/build_kotlin_compose.ps1` | `scripts/threading_kotlin_compose.kt` | -- |
| Swift / SwiftUI      | `scripts/build_swift.ps1` | `scripts/threading_dispatch.swift` | -- |
| Neutralino.js        | `scripts/build_neutralino.ps1` | (N/A, JS event loop)           | -- |

For independent batch jobs, use the matching `scripts/threading_pool_*`
template (Python, C#, Tauri, Compose, Electron) instead of N single
workers; they add aggregate progress, retry, and one `cancel()`.

For tool picker *inside* one language (tkinter vs PySide6, WPF vs
WinUI 3 vs Avalonia), see `templates/gui_framework_decision_tree.md`.

---

## By task

### I need to set up the dev environment

Run `scripts/bootstrap_environment.ps1` with `-Brief brief.json` for
auto framework selection, or `-Framework <key>` for a fixed framework.
Use `-DryRun` first, then `-Install` to install via winget / pip. The
framework-to-toolchain mapping is in `scripts/toolchain_map.json`.
Build helpers never auto-install; helpers with a safe installer accept
the same `-Install` opt-in, and the rest fail with the exact install
command.

### I need UI / theme consistency

Open `references/ui_hard_requirements.md` -- canonical UI-01..UI-19
checklist, Codex-like default palette, semantic colors, theme library
URLs, settings persistence, log center, and auto-refresh rules.

### I need a heavy desktop / data-dense app

Open `references/heavy_desktop_playbook.md` for layered architecture,
dependency injection, grid virtualization / paging, long-running job
persistence, startup and memory profiling, single instance, crash
reporting, and plugin isolation. Copy
`templates/heavy_desktop_acceptance.md` into requirements.md and run
`scripts/heavy_desktop_verify.ps1` in Step 6.

### I need deep desktop UI / theming / controls

Open `references/desktop_ui_playbook.md` for design tokens, runtime theme
switching, control catalog, data grids, keyboard interaction, state
management, accessibility, and UI performance. Copy
`templates/desktop_ui_tokens.json` as the token source and close with
`templates/desktop_ui_checklist.md`.

### I need to modify existing code safely

Apply `SKILL.md` CODE-01..CODE-05 (`references/minimal_change_requirements.md`):
keep working original logic, keep the diff scoped, prefer incremental
extensions, record intentional behavior changes, and regression-verify
original features.

### I need a media downloader / republisher

Start at `references/media_acquisition_playbook.md`. Use
`scripts/task_queue.py` for SQLite task persistence, then wire in
`media_session.py`, `media_parser.py`, `page_data_parser.py` (deep
page/API/data parse + CLI), `scrape_guard.py` (rate limit / retry /
robots / adaptive throttle), `media_downloader.py`, `hls_downloader.py`,
`captcha_solver.py` (auto-detect / auto-solve), `browser_session.py`
(fingerprint + runtime network capture), `ffmpeg_transcoder.py`, and
`platform_publisher.py`. The unified format catalog lives in
`media_formats.py`; `file_converter.py` converts single files or folders
across video / audio / image / subtitle / document / data / archive
categories with aggregate byte-based progress.
For any other desktop UI language, run `scripts/media_pipeline_service.py`
and use `clients/` wrappers or `references/media_pipeline_clients.md`
to call it over HTTP.
Install the runtime with the app's built-in dependency center (UI-19):
the user clicks `安装依赖`, and the app calls `POST /deps/install` or
uses `scripts/builtin_dependency_manager.py` to download / install /
configure app-local binaries automatically. The CLI equivalent is
`scripts/setup_media_dependencies.ps1 -Install`.
Live UI progress comes from `GET /tasks/<id>/progress` and
`GET /tasks/<id>/events?after=N&timeout=0..30` (long-poll); snapshots
include total file size, downloaded/output bytes, percent, speed, ETA, and
chunk/merge counts. `GET /formats` returns the full target catalog;
enqueue `kind: "convert"` / `kind: "batch-convert"` for single-file or
folder conversion.

### I need to collect API data / process it by user rules

Start at `references/web_data_pipeline_playbook.md`. Use
`scripts/browser_session.py` for a stable fingerprint browser with cookies /
storage state and runtime network capture, `scripts/captcha_solver.py` for
auto CAPTCHA detection / local OCR / third-party solving, and
`scripts/page_data_parser.py` for static page/API analysis. Then
`scripts/api_client.py` replays captured API specs, `scripts/data_processor.py`
filters / sorts / aggregates records, and `scripts/web_data_pipeline.py`
runs the whole flow from one JSON config. `scripts/api_analyzer.py` produces
an API manifest with auth header names, endpoint scores, data paths, and
inferred pagination. `scripts/security_detector.py` classifies
Cloudflare / WAF / rate-limit / CAPTCHA / login / geo blocks and picks a
non-interactive action; `scripts/deep_crawler.py` recursively discovers
pages via links and sitemaps with robots and rate-limit protection. The
sidecar accepts `kind: "webdata"` tasks for any desktop UI language and
exposes per-task progress/events.

### I need deep crawling / automatic anti-bot handling

Run `scripts/deep_crawler.py` for BFS link + sitemap crawling with
`--max-depth`, `--max-pages`, `--include`, `--exclude`, `--same-host`,
`--no-sitemap`, and `--no-robots`. Every fetched page is classified by
`scripts/security_detector.py`; blocked pages are recorded and skipped so
one Cloudflare / WAF / CAPTCHA page cannot stop the job. In
`web_data_pipeline.py`, enable it with a `crawl` section and control
automatic handling with a `security` section
(`skip_blocked`, `escalate_to_browser`, `auto_handle`). For Cloudflare
managed challenges / Turnstile, add a `cloudflare` section backed by
`scripts/cloudflare_challenge.py`: it waits for `cf_clearance`, clicks the
widget, injects a third-party token when configured, and reuses the cleared
UA + proxy for API calls.

### I need a tiny single-file EXE

| Priority                         | Script                                | Result |
|----------------------------------|----------------------------------------|--------|
| Smallest, no runtime             | `scripts/build_dotnet_nativeaot.ps1`   | NativeAOT single EXE |
| Python quick + no runtime        | `scripts/build_python.ps1`             | PyInstaller onefile |
| Go single static binary          | `scripts/build_go_gio.ps1` / `build_go_fyne.ps1` | stripped GUI EXE |
| One installer, small size        | `scripts/build_tauri.ps1` / `build_qt.ps1` | NSIS setup EXE with bundled runtime |

All size-lean helpers default to symbols off, compression on, and print the
artifact size. Avoid Electron / Compose with default JBR when size or idle
RAM is a hard budget.

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
`scripts/backup_source.ps1`, or pass `-BackupSource` to any
`scripts/build_*.ps1` helper so the backup runs automatically.

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

### I need proxy pool / dynamic IP rotation

Use `scripts/proxy_pool.py` (`ProxyPool` / `ProxyPoolStore`) and pass
`proxy_pool` in task payloads or `web_data_pipeline` config. Sidecar
endpoints: `GET/POST/DELETE /proxy-pools`, `GET /proxy-pools/<name>`.

### I need multi-account session management

Use `scripts/account_manager.py` and sidecar endpoints
`GET/POST/DELETE /accounts` plus `POST /accounts/<name>/acquire|release`.
Set `"account": "<name>"` on a task payload to lease one session per worker.

### I need scheduled tasks / recurring runs

Use `scripts/task_scheduler.py` (interval / daily / cron) through
`POST /schedules`, `GET /schedules`, `DELETE /schedules/<id>`, and
`POST /schedules/<id>/pause|resume`.

### I need task completion notifications

Configure `scripts/notifier.py` through the sidecar startup file; channels
are desktop toast, SMTP email, and webhook. Check status with
`GET /notifications/status` and send a test with `POST /notifications/test`.

### I need to work without internet

Start at `references/restricted_network_playbook.md` (vendoring /
local mirrors / offline caches / single-file fallback).

### I need to enforce multi-architecture builds

Run `tests/test_arch_awareness.ps1` -- verifies every `build_*.ps1`
declares `-Arch` / `-Rid` with the right `ValidateSet`, plus parses the
two `auto_update_*.ps1` helpers. Currently 16 / 16 checks pass on
Windows x64 (Electron uses `ia32`, NativeAOT is `win-x64`).

---

## Quick "I want X" finder

```
I want to send keystrokes to another app
    --> scripts/sendinput_<your-os>.py
        (Windows: sendinput_python.py / sendinput_win32.c / sendinput_dotnet.cs / ...)

I want to enumerate windows on screen
    --> scripts/window_enum_<your-os>.py
        (Windows: window_enum_python.py / window_enum_dotnet.cs / ...)

I want to deeply analyze a page's APIs / embedded data
    --> scripts/page_data_parser.py (analyze_page)
        + scripts/browser_session.py (capture_page_data)

I want a stable browser fingerprint / account profile
    --> scripts/browser_session.py (FingerprintOptions.generate + save/load)

I want to analyze a page and its APIs, fetch API data, and process it
    --> references/web_data_pipeline_playbook.md
        + scripts/api_analyzer.py
        + scripts/api_client.py
        + scripts/data_processor.py
        + scripts/web_data_pipeline.py

I want polite rate-limited crawling
    --> scripts/scrape_guard.py + media_session.py
        (min_interval / max_retries / robots_text / adaptive_throttle)

I want a runnable demo I can adapt
    --> examples/<closest framework>/

I want background work without freezing the UI
    --> references/threading_playbook.md
        (30 scripts/threading_* files: single-worker + pool templates)

I want a heavy desktop / data-dense app
    --> references/heavy_desktop_playbook.md
        + templates/heavy_desktop_acceptance.md
        + scripts/heavy_desktop_verify.ps1

I want deep desktop UI theming / controls / accessibility
    --> references/desktop_ui_playbook.md
        + templates/desktop_ui_tokens.json
        + templates/desktop_ui_checklist.md

I want to convert audio / video / images / documents / archives
    --> scripts/file_converter.py + scripts/media_formats.py
        (or enqueue convert / batch-convert tasks through the sidecar)

I want app-local one-click dependency install
    --> scripts/builtin_dependency_manager.py + UI-19
        (user clicks install; app downloads/configures into its runtime)

I want to package as EXE / .app / .AppImage
    --> scripts/build_<your-target>.ps1 (or .sh)

I want to keep a source backup before packaging
    --> scripts/backup_source.ps1
        (or -BackupSource on any scripts/build_*.ps1 helper)

I want rotating proxies / account pools / schedules / notifications
    --> scripts/proxy_pool.py + scripts/account_manager.py
        + scripts/task_scheduler.py + scripts/notifier.py

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
