---
name: desktop-app-dev
description: "Consultative Codex skill for shipping native cross-platform desktop GUI applications (Windows / macOS / Linux) via an 8-step workflow: deep requirements analysis, automated framework selection, task decomposition, UI responsiveness and hardware input, packaging, verification, and handoff. Ships with multi-language SendInput/window-enumeration templates, per-framework threading templates, build scripts, auto-update helpers, DPI manifest, requirements/task-card/release/security templates, and smoke-test fixtures across all three OSes."
---

# Desktop App Dev

A consultative Codex skill for shipping native cross-platform desktop GUI applications.
The agent that uses this skill behaves like a desktop-app architect: it
**first** digs past the literal request to surface hidden requirements,
**then** picks the right framework, **then** decomposes the work into
verifiable tasks, **then** builds, **then** verifies, **then** hands off.

## The 8-step workflow (apply in order)

| # | Step | Output |
|---|---|---|
| 0 | **Deep requirements analysis** | requirements.md |
| 1 | **Classify the app** | category (A/B/C/D) |
| 2 | **Pick the framework** | framework decision + rationale. Use `python scripts\select_framework.py brief.json` for an evidence-backed ranking across all 23 canonical frameworks |
| 3 | **Decompose into atomic tasks** | tasks.md (DAG with acceptance criteria) |
| 4 | **Apply core patterns** | project scaffold + core code |
| 5 | **Package** | installer / portable EXE |
| 6 | **Verify** | verification report |
| 7 | **Hand off** | user-facing README + comments |



## Scope and limits

### In scope

Native cross-platform desktop GUI applications. Each operating system
has its own build, packaging, signing, and input conventions; the
skill ships templates for all three.

| OS      | Versions                  | Default UI stack          | Input API                  | Window enum API                  | Code sign / notarize    |
|---------|---------------------------|---------------------------|----------------------------|----------------------------------|-------------------------|
| Windows | 10 1809+, 11              | WPF / WinUI 3 / Avalonia  | `SendInput` (user32)       | `EnumWindows` (user32)           | `signtool` + Authenticode |
| macOS   | 11+ (Big Sur), Apple Silicon preferred | SwiftUI / AppKit / Catalyst | `CGEventPost` (Quartz)      | `CGWindowListCopyWindowInfo` (Quartz) | `codesign` + `notarytool` |
| Linux   | glibc 2.31+ (Ubuntu 20.04+, RHEL 9+, Debian 11+, Fedora 36+) | GTK 4 / Qt 6 / Tauri / Electron | `XTestFakeInputEvent` (X11) or uinput (Wayland) | `XQueryTree` + `_NET_CLIENT_LIST` (X11) | per-distro (deb / rpm / AppImage signing) |

Per-architecture coverage across all three OSes:

- **win-x64**      (default; Intel / AMD 64-bit -- the common case)
- **win-arm64**    (Snapdragon X Elite, Surface Pro X, Windows Dev Kit 2023)
- **win-x86**      (legacy 32-bit Windows -- old hardware)
- **macos-x64**    (Intel Macs -- last supported by macOS 12; legacy)
- **macos-arm64**  (Apple Silicon M1/M2/M3/M4 -- the common case today)
- **linux-x64**    (Intel / AMD servers and desktops)
- **linux-arm64**  (Raspberry Pi 4/5, AWS Graviton, Snapdragon X Linux, Asahi Linux)

Per-architecture notes:

- All `build_*.ps1` scripts accept `-Arch` with platform-appropriate values.
- PyInstaller / dotnet publish / cargo all default to host architecture;
  cross-compile only via the documented per-tool recipe.
- `SendInput` / `EnumWindows` (Win) work identically across all Windows
  architectures (no Win32 ABI differences for these APIs).
- `CGEventPost` / `CGWindowListCopyWindowInfo` (macOS) work on both
  Intel and Apple Silicon -- they are part of the OS, not the ABI.
- `XTestFakeInputEvent` (X11) is arch-neutral. Wayland requires uinput
  which is kernel-bound and arch-neutral.
- NativeAOT (`-p:PublishAot=true`) currently only targets x64 on Windows.

### Out of scope

Explicitly **not** covered. Do not pretend these are part of this skill.

| Domain                  | Why out of scope                                  | Use instead                                |
|-------------------------|---------------------------------------------------|--------------------------------------------|
| iOS / iPadOS / watchOS / visionOS apps | Different ABI (ARM64 only), no Win32 / Quartz / X11, App Store + TestFlight | the `mobile-app-dev-ios` skill |
| Android apps            | APK + Play Store, Java/Kotlin toolchain            | the `mobile-app-dev-ios` skill (Android half) |
| Web apps / SPAs         | Browser sandbox, no native window                  | a web framework skill                       |
| Browser extensions      | Different manifest, MV3 specifics                  | a web-extension skill                       |
| CLI tools / libraries   | No GUI main loop; hardware input not relevant      | a CLI-design skill                          |
| Server / headless       | No window, different observability                 | a backend skill                             |
| Windows services / drivers | No UI; kernel vs user mode                     | a separate sysdev skill                     |
| Browser / kiosk / locked-down endpoints | Different OS image lifecycle        | an embedded / MDM skill                     |

### Architecture support matrix

| Framework / script            | Win x64 | Win arm64 | Win x86 | macOS x64 | macOS arm64 | Linux x64 | Linux arm64 | Notes |
|-------------------------------|:-------:|:---------:|:-------:|:---------:|:-----------:|:---------:|:-----------:|-------|
| `build_dotnet.ps1`            |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | per-OS RID; default win-x64 |
| `build_dotnet_nativeaot.ps1`  |   Y     |    -      |    -    |     -     |     -       |     -     |     -       | NativeAOT is win-x64 only |
| `build_electron.ps1`          |   Y     |    Y      |    Y*   |     Y     |     Y       |     Y     |     Y       | `ia32` instead of `x86`     |
| `build_qt.ps1`                |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | needs matching Qt toolchain |
| `build_python.ps1`            |   Y     |    Y*     |    Y*   |     Y     |     Y*      |     Y     |     Y*      | PyInstaller is host-bound   |
| `build_tauri.ps1`             |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | uses Rust target triples    |
| `build_go_wails.ps1`          |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | `windows/{amd64,arm64,386}` |
| `build_go_fyne.ps1`           |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | sets `GOOS`+`GOARCH`       |
| `build_go_gio.ps1`            |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | sets `GOOS=...` + `GOARCH`  |
| `build_kotlin_compose.ps1`    |   Y     |    Y*     |    Y*   |     Y     |     Y*      |     Y     |     Y*      | Compose Desktop arch        |
| `build_swift.ps1`             |   Y     |    Y      |    -    |     Y     |     Y       |     Y*    |     Y*      | `--triple` per triple       |
| `build_neutralino.ps1`        |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | arch follows WebView runtime|
| `build_macos.ps1`             |   -     |    -      |    -    |     Y     |     Y       |     -     |     -       | macOS-only build helper     |
| `build_linux.ps1`             |   -     |    -      |    -    |     -     |     -       |     Y     |     Y       | Linux-only build helper     |
| `build_dmg.sh`                |   -     |    -      |    -    |     Y     |     Y       |     -     |     -       | DMG packaging               |
| `build_appimage.sh`           |   -     |    -      |    -    |     -     |     -       |     Y     |     Y       | AppImage packaging          |
| `build_deb.sh`                |   -     |    -      |    -    |     -     |     -       |     Y     |     Y       | .deb packaging              |

`*` = supported by the toolchain but not yet verified at run time in this skill.

Run the structural test: `powershell tests/test_arch_awareness.ps1`

---

---

If a request falls under any "Out of scope" row, **stop and tell the user**
rather than silently producing a Windows desktop answer.

---

## When NOT to use this skill

This skill is for shipping a native cross-platform desktop GUI
application. Do not
reach for it if any of the following is true:

- **The deliverable is a CLI tool, library, or server.** Use the
  CLI-building or API-design skill instead. SendInput / EnumWindows are
  not relevant.
- **The deliverable is a web app or SPA.** This skill is desktop-only.
  Reach for the web-app skill.
- **The deliverable is a mobile app.** Desktop-specific patterns
  (SendInput, EnumWindows, COM, MSIX) do not apply. Use the mobile skill.
- **The user only wants a single-purpose script under ~200 lines.**
  The 8-step workflow is overkill. Skip the skill and write the script.
- **The user is researching or comparing frameworks but is not ready
  to commit.** Send them `references/framework_matrix.md` as a
  standalone doc, do not start the workflow.
- **The target is a console-mode subsystem, Windows service, or driver.**
  Those need a different skill; this one assumes a GUI main window.
- **The user is locked into one framework by team / company policy.**
  Skip Step 2 and apply Steps 0, 3, 4, 5, 6, 7 directly.

If the request is ambiguous, ask one clarifying question (the
showstopper) before starting. Do not pretend the request is a desktop
app when it is not.

---

Do NOT skip Step 0 even if the user says "just build X fast". Hidden
requirements are the #1 cause of projects that look done but aren't.
Do NOT skip Step 3 even for small apps -- "build the GUI" is never one
task; it's at least scaffold, core data model, threading, UI, errors,
settings, packaging.

---

## Step 0 -- Deep requirements analysis

Copy `templates/requirements_checklist.md`, fill it in. Do not paraphrase
the user back to themselves; dig deeper.

**Six buckets to interrogate:**

1. **Functional (literal)** -- what they explicitly asked for.
2. **Functional (implicit)** -- what they need but did not say:
   settings persistence, error handling, logging, crash reporting,
   localization, accessibility (screen reader, high contrast,
   keyboard-only), undo/redo, auto-save.
3. **Non-functional** -- cold start budget, memory ceiling, CPU at idle
   vs peak, network assumptions (online / offline / both), reliability
   targets, security classification of any data handled.
4. **Distribution** -- portable EXE vs MSI vs MSIX vs Store; code-signing
   cert available? auto-update yes/no and channel; per-user vs
   per-machine install; elevation needed?
5. **Integration** -- local (file system, registry, services, drivers,
   COM, hardware: USB/serial/Bluetooth), remote (HTTP, gRPC, sockets,
   message queue), databases, auth, other apps (IPC, WebView2 host).
6. **Failure modes to design for** -- target process missing, network
   down, disk full, permission denied, concurrent modification, corrupt
   config file, recipient running the wrong runtime version.

**Three questions to always ask the user** (and accept that the answer
"don't care" is a valid answer that should be recorded):

- "What is the smallest thing this app must NOT do wrong?" (the
  showstopper; everything else is negotiable)
- "How will recipients get updates?" (forces an answer about distribution)
- "What does this app look like when nothing is happening?" (idle
  behavior -- background work, tray icon, scheduled tasks)

**Common omissions to flag explicitly** when the user did not mention
them: logging destination, settings migration between versions, AV
false-positive handling, Windows version skew (10 vs 11), DPI scaling
(multi-monitor with mixed DPI), backup of user data, opt-in telemetry.

If any of these cannot be resolved before coding starts, they become
**explicit assumptions** recorded in requirements.md, not surprises later.

Deep dive in `references/task_decomposition.md` -- section "Requirements
deep dive".

---

## Step 1 -- Classify the app

Pick the one category whose hardest constraint would force a different
framework. Mixed requests are normal; resolve by the binding constraint.

| Category | Typical signals | Hardest constraint |
|---|---|---|
| **A. Game automation / hardware input** | "send keys", "anti-cheat", "SendInput", game name | Hardware-level input even when not focused; anti-cheat safe |
| **B. Productivity / business** | "form", "table", "report", "dashboard", "SQL", "Excel" | Fast UI development, data-grid performance, native Windows 11 look |
| **C. System / DevOps** | "registry", "service", "driver", "P/Invoke", "COM", "ETW" | Deep OS access; Windows-only usually acceptable |
| **D. Multimedia / creative** | "GPU", "render", "OpenGL", "DirectX", "camera", "audio" | GPU access, frame budget, low-latency I/O |

If the user mentions multiple categories, list each constraint and pick
the framework that satisfies all of them. If none of the popular
frameworks satisfies all, recommend splitting the project (e.g. a Tauri
UI talking to a Rust sidecar that does the heavy lifting).

---

## Step 2 -- Pick the framework

Use the matrix below. Pick the framework that scores "best" on the user's
binding constraint, not the framework you know best. **Always document the
rejection reasons for the next two candidates** -- the user will ask.

### Quick decision tree

```
Need WPF/WinUI look on Windows-only?           -> C# / .NET (WPF or WinUI 3)
Need cross-platform desktop, modern UI?        -> Tauri (Rust+Web) or .NET MAUI
Need cross-platform + JS team only?            -> Electron or Tauri
Need max performance + small EXE?              -> C++/Qt or Rust+Slint/egui
Need fastest prototype, Python team?           -> Python (tkinter or PySide6)
Need single portable EXE?                      -> .NET NativeAOT, Tauri, Rust+Slint, PyInstaller
Need legacy Win32/MFC/ActiveX interop?         -> C#/.NET + P/Invoke, or C++/Qt
Need GPU rendering (3D, shaders)?              -> C++/Qt Quick, Rust+wgpu, or C# + Vortice.Windows
Need cross-platform + Go team?                 -> Wails (Go+Web) or Fyne
Need Windows-only native Go UI?                -> walk (Win32 bindings for Go)
Need cross-platform + Kotlin team?              -> Compose Multiplatform (Desktop)
Need JVM desktop with declarative UI?            -> TornadoFX (Kotlin/JavaFX DSL)
Need macOS-first, Swift-only codebase?           -> SwiftUI + AppKit
Want Electron-like TypeScript, tiny EXE?        -> Neutralino.js (no Chromium bundled)
```

### Framework matrix

Columns are the dimensions users actually ask about. A "1" is best in
class, a "5" is worst.

| Framework | Cold start | EXE size | Native look | Hardware access | Distribution ease | Learning curve | Cross-platform |
|---|---|---|---|---|---|---|---|
| C# / WPF (.NET 8+) | 2 | 3 | 2 | 2 | 1 | 2 | No |
| C# / WinUI 3 | 2 | 3 | 1 | 2 | 2 | 3 | No |
| .NET MAUI | 3 | 3 | 3 | 2 | 2 | 3 | Yes |
| Avalonia | 2 | 2 | 2 | 2 | 2 | 2 | Yes |
| C++ / Qt 6 | 1 | 2 | 2 | 1 | 2 | 3 | Yes |
| C++ / Win32 / MFC | 1 | 1 | 2 | 1 | 4 | 5 | No |
| Tauri (Rust+Web) | 1 | 1 | 3 | 1 | 1 | 3 | Yes |
| Electron | 4 | 5 | 4 | 3 | 2 | 2 | Yes |
| Rust + Slint | 1 | 1 | 3 | 1 | 2 | 3 | Yes |
| Rust + egui | 1 | 1 | 4 | 1 | 2 | 2 | Yes |
| Python / tkinter | 2 | 4 | 4 | 2 | 2 | 1 | Yes |
| Python / PySide6 | 3 | 5 | 2 | 2 | 2 | 3 | Yes |
| Flutter Desktop | 2 | 3 | 3 | 3 | 2 | 3 | Yes |
| Java / JavaFX | 3 | 3 | 4 | 2 | 3 | 2 | Yes |
| Wails (Go+Web) | 1 | 2 | 3 | 1 | 1 | 2 | Yes |
| Fyne (Go) | 2 | 3 | 3 | 2 | 2 | 2 | Yes |
| Gio (Go, GPU) | 1 | 1 | 4 | 1 | 2 | 3 | Yes |
| walk (Go, Win32) | 1 | 1 | 2 | 1 | 3 | 4 | No |
| Compose Multiplatform (Kotlin) | 2 | 4 | 3 | 2 | 2 | 2 | Yes |
| TornadoFX (Kotlin/JavaFX) | 3 | 4 | 4 | 2 | 3 | 3 | Yes |
| Swift / SwiftUI (Apple) | 1 | 2 | 1 | 1 | 2 | 3 | Yes |
| Neutralino.js (TS, WebView) | 2 | 1 | 4 | 3 | 1 | 1 | Yes |

### Distribution-first override

If the user specifies a hard distribution constraint, narrow the matrix first:

| Distribution | Viable frameworks |
|---|---|
| **Single-file portable EXE** (< 50 MB, no install) | Tauri, Rust+Slint, .NET 8 self-contained + R2R, NativeAOT, C++/Qt static, PyInstaller, Fyne, Gio, walk, Neutralino.js (TS+WebView2), Kotlin/Native (limited desktop UI) |
| **MSI installer** | C#/.NET (WiX), C++/Qt (windeployqt + WiX), Tauri, Electron (electron-builder MSI) |
| **MSIX** | C#/WinUI 3, C#/WPF (WAP), Tauri (MSIX target) |
| **Microsoft Store** | C#/WinUI 3, C#/WPF (packaged), Electron, Tauri |
| **Auto-update channel** | Velopack (any), Squirrel (Electron, C#), WinSparkle (C++/Qt) |
| **Cross-platform + single codebase** | Tauri, .NET MAUI, Avalonia, Electron, Flutter Desktop, Qt, Wails, Fyne, Gio, Compose Multiplatform, Neutralino.js |

### Step 2.5 -- Bootstrap the toolchain (optional)

After the framework is selected, install the matching SDK / toolchain:

```powershell
powershell -File scripts/bootstrap_environment.ps1 -Brief brief.json -DryRun
powershell -File scripts/bootstrap_environment.ps1 -Brief brief.json -Install
powershell -File scripts/bootstrap_environment.ps1 -Framework python -Install
```

`-Brief` auto-selects the framework with `scripts/select_framework.py`;
`-Framework` accepts a framework or language key directly. The
framework-to-toolchain mapping lives in `scripts/toolchain_map.json`.
Install actions use winget and pip, so they require network access and
user approval.

---

## Step 3 -- Decompose into atomic tasks

"Build me X" is never one task. Decompose until each task is:
- Completable in one focused work session (<= a few hours).
- Independently verifiable against an acceptance criterion.
- Has zero or few dependencies on other tasks.

Use the task card at `templates/task_card.md` -- one card per task.

**Standard decomposition order** (left-to-right; later tasks depend on earlier):

```
T1  Project scaffold (repo, build, CI, signing cert procurement)
T2  Core data model / persistence (settings, file formats, DB schema)
T3  Core services (threading, IPC, file watcher, DB access, HTTP client)
T4  UI shell (main window, navigation, theming, DPI handling)
T5  Feature tasks (one per user-visible feature, each with own acceptance test)
T6  Polish (logging, error UI, settings migration, accessibility)
T7  Integration (auto-update channel, telemetry, crash reporter)
T8  Packaging (EXE/installer build, code-sign, hash pinning)
T9  Documentation (README, build instructions, troubleshooting)
```

**Variations:**
- Game automation: insert T3.5 "anti-cheat research spike" before T5
  features; if anti-cheat blocks standard approaches, T5 changes shape.
- System tool: T3 starts with "Win32 capability survey" because some
  admin APIs require elevation.
- Multimedia: T4 includes "GPU device enumeration" + "shader/asset
  pipeline".

**For each task card fill in:**
- Title, description, category (scaffold / model / service / UI / polish / pkg)
- Acceptance criteria -- concrete, testable ("Ctrl+S saves to %APPDATA%\app\config.json",
  not "settings work").
- Dependencies -- list of task IDs that must complete first.
- Estimated effort -- S/M/L.
- Risk + mitigation.
- Verification method -- unit test, manual smoke, automated UI test.

**Identify parallel vs sequential work.** Tasks with no inter-dependency
can be done in parallel; mark them `[P]` in the task list.

**Identify the showstopper.** Tag the single task whose failure kills the
project as `[showstopper]` and verify it early.

Deep dive + worked examples in `references/task_decomposition.md`.

---

## Step 4 -- Apply core patterns

### 4.1 UI responsiveness (the universal rule)

Every desktop framework runs UI callbacks on a single UI thread. Any
blocking call (sleep, sync socket, subprocess wait, large file read,
COM call, DB query) freezes the window. Wrap every blocking call in a
background worker and post results back to the UI thread using the
framework's safe bridge.

| Framework | Background primitive | UI bridge |
|---|---|---|
| C# / WPF, WinUI 3 | `Task.Run(...)` | `await` + `DispatcherQueue.TryEnqueue` / `Dispatcher.InvokeAsync` |
| C# / WinForms | `Task.Run` | `this.Invoke(...)` |
| Avalonia | `Task.Run` | `Dispatcher.UIThread.Post(...)` |
| C++ / Qt | `QThread`, `QtConcurrent::run` | `QMetaObject::invokeMethod(target, ..., Qt::QueuedConnection)` |
| Tauri (Rust) | `tokio::spawn` / `tauri::async_runtime::spawn` | `window.emit("event", payload)` |
| Electron | `worker_threads` or child process | `mainWindow.webContents.send("event", payload)` |
| Python / tkinter | `threading.Thread(daemon=True)` | `root.after(0, callback)` |
| Python / PySide6 | `QThread` or `QThreadPool` | Signal/slot (auto-queued) |
| Flutter Desktop | `Isolate.spawn` / `compute` | Stream / Completer |
| Go (Fyne) | `go func()` | `fyne.Do(func(){...})` or channel |
| Go (Wails) | `go func()` | `runtime.EventsEmit(ctx, "event", payload)` |
| Go (walk) | `go func()` | `walk.Window.RunSafe(func(){...})` |
| Kotlin (Compose Desktop) | `launch { ... }` (coroutine) | `withContext(Dispatchers.Main) { ... }` |
| Kotlin (TornadoFX) | `runAsync { ... }` | UI thread auto (JavaFX Application Thread) |
| Swift (SwiftUI) | `Task { ... }` | `@MainActor` or `await MainActor.run { ... }` |
| Java / JavaFX | `Task` + `Service` | `Platform.runLater(...)` |

NEVER mutate UI from the worker. The bridge is the ONLY safe path back.

Templates: `scripts/threading_wpf.cs`, `scripts/threading_winui.cs`,
`scripts/threading_tkinter.py`, `scripts/threading_pyside6.py`,
`scripts/threading_tauri.rs`, `scripts/threading_glib.py`,
`scripts/threading_dispatch.swift`, plus the `sendinput_*` and matching
`window_enum_*` templates for each language.

### 4.2 Hardware-level input (SendInput, anti-cheat safe)

For input that must reach a specific window even when it is not focused --
including games with anti-cheat -- use `user32.SendInput` (Win),
`CGEventPost` (mac), `XTestFakeInputEvent` (X11), `uinput` (Linux).
Do NOT use `PostMessage`, `SendMessage`, `keybd_event` (deprecated),
memory write, or auto-hotkey-style scripts. These are detected or
ignored by modern anti-cheat and most EDR products.

Mandatory order on Windows:
1. Find the target HWND (4.3).
2. Restore + foreground: `ShowWindow(hwnd, SW_RESTORE)` then
   `SetForegroundWindow(hwnd)`.
3. Build an `INPUT` struct with `type=INPUT_KEYBOARD`, `ki.wVk` =
   virtual key code, `ki.dwFlags = 0` for press or `KEYEVENTF_KEYUP`
   for release.
4. Call `SendInput(2, [press, release], sizeof(INPUT))` with 30-80 ms
   between halves.
5. Add 50-150 ms jitter between key events when targeting a game. All
   templates randomize this range by default; pass an explicit positive
   `jitterMs` / `jitter_range_ms` value to force a fixed delay.

Templates in **10 languages**:
- `scripts/sendinput_python.py` (ctypes)
- `scripts/sendinput_dotnet.cs` (P/Invoke)
- `scripts/sendinput_win32.c` (Win32)
- `scripts/sendinput_rust.rs` (windows crate)
- `scripts/sendinput_go.go` (golang.org/x/sys/windows)
- `scripts/SendInput.java` (JNA)
- `scripts/sendinput_dart.dart` (dart:ffi)
- `scripts/sendinput_node.ts` (koffi)
- `scripts/sendinput_swift.swift` (WinSDK)
- `scripts/sendinput_kotlin.kt` (Win32 FFI)

OS-specific analogues: `scripts/sendinput_macos.py` (CGEventPost) and
`scripts/sendinput_linux.py` (XTestFakeKeyEvent).

The Python Windows template additionally ships `move_mouse`, `click`, and
`scroll`; the other language templates are keyboard-only.

The canonical key table lives in `scripts/vk_table.json`;
`scripts/check_vk_tables.py` verifies that the Python reference template
matches it exactly.

### 4.3 Window enumeration (timeout + cache, always)

Default flow on Windows:
1. Try `user32.FindWindowW(class_name, window_title)` -- O(1), no
   allocation.
2. If title is partial or class is unknown, fall back to `EnumWindows`.
3. **Always run `EnumWindows` inside a thread guarded by a 3-second
   timeout.** An owner-drawn window can block `EnumWindows`
   indefinitely and spike the UI lag to several seconds.
4. Cache results by `(class_name or None, title_substring)` for the
   current session. Invalidate on a "Refresh" click.

Templates in **9 languages**:
- `scripts/window_enum_python.py` (ctypes)
- `scripts/window_enum_dotnet.cs` (P/Invoke)
- `scripts/window_enum_rust.rs` (windows crate)
- `scripts/window_enum_go.go` (golang.org/x/sys/windows)
- `scripts/WindowEnum.java` (JNA)
- `scripts/window_enum_dart.dart` (package:win32)
- `scripts/window_enum_node.ts` (koffi; EnumWindows needs a C++ shim -- see file comments)
- `scripts/window_enum_swift.swift` (WinSDK)
- `scripts/window_enum_kotlin.kt` (Win32 FFI)

OS-specific analogues: `scripts/window_enum_macos.py`
(CGWindowListCopyWindowInfo) and `scripts/window_enum_linux.py`
(X11 XQueryTree + EWMH).

### 4.4 Resource embedding (per framework)

| Framework | How to embed and locate assets at runtime |
|---|---|
| C# / .NET | Mark files as `Resource` or `Content` in csproj; access via `Properties.Resources` or `AppContext.BaseDirectory + "Assets/..."` |
| C++ / Qt | `.qrc` resource file; `:/icons/foo.png` at runtime |
| Tauri | `tauri.conf.json` -> `bundle.resources`; access via `app.path().resource_dir()` |
| Electron | `electron-builder` `extraResources`; access via `process.resourcesPath` |
| Python (PyInstaller) | `--add-data "src;dest"`; locate via `sys._MEIPASS` |

---

## Step 5 -- Package

### 5.1 Pick the right packaging tool

| Need | Tool |
|---|---|
| Python single-file EXE | PyInstaller `--onefile --windowed` |
| Python folder + assets | PyInstaller `--onedir` + Inno Setup / NSIS |
| .NET single-file, fast | `dotnet publish -c Release -r win-x64 --self-contained -p:PublishSingleFile=true -p:PublishReadyToRun=true` |
| .NET NativeAOT (smallest) | `dotnet publish -p:PublishAot=true` (.NET 8+) |
| .NET with bundled DLLs | `Costura.Fody` NuGet + `PublishSingleFile=true` |
| Tauri | `cargo tauri build` (NSIS + MSI + DMG + deb) |
| Electron | `electron-builder` (NSIS, MSI, AppX, deb, rpm, dmg) |
| C++ / Qt | `windeployqt` + `cpack` or NSIS |
| MSI in general | WiX Toolset v3/v4 |
| MSIX | Visual Studio MSIX Packaging Project, or `msbuild` + `MakeAppx.exe` |
| Auto-update | Velopack (multi-framework), Squirrel (Electron, C#), WinSparkle (C++/Qt), Sparkle (macOS), AppImageUpdate (Linux) |

Build scripts in **14 PowerShell helpers**:
- `scripts/build_python.ps1` (PyInstaller; auto-resolves Python from `-PythonExe`, `CODEX_PYTHON`/`PYTHON` env, Codex runtime, or PATH)
- `scripts/build_dotnet.ps1` (dotnet publish self-contained)
- `scripts/build_dotnet_nativeaot.ps1` (NativeAOT single-file EXE, win-x64)
- `scripts/build_tauri.ps1` (Tauri NSIS + MSI)
- `scripts/build_qt.ps1` (C++/Qt 6 + windeployqt + cpack NSIS/WIX)
- `scripts/build_electron.ps1` (electron-builder NSIS/MSI/portable)
- `scripts/build_go_wails.ps1` (Wails v2 NSIS)
- `scripts/build_go_fyne.ps1` (Fyne package)
- `scripts/build_go_gio.ps1` (Gio, go build with -H windowsgui + strip)
- `scripts/build_kotlin_compose.ps1` (Compose Multiplatform gradle)
- `scripts/build_swift.ps1` (Swift on Windows swift build)
- `scripts/build_neutralino.ps1` (Neutralino.js neu build)
- `scripts/build_macos.ps1` (macOS dotnet / cargo / xcodebuild wrapper)
- `scripts/build_linux.ps1` (Linux dotnet / cargo / go / python wrapper)

Shell packaging helpers: `scripts/build_dmg.sh`, `scripts/build_appimage.sh`,
`scripts/build_deb.sh`.

Auto-update helpers:
- `scripts/auto_update_velopack.ps1` (Velopack pack + upload; .NET / Rust / Python / Electron)
- `scripts/auto_update_squirrel.ps1` (Squirrel.Windows for .NET / Electron)
- `scripts/auto_update_winsparkle.cpp` (WinSparkle drop-in for C++/Qt/wxWidgets/MFC)
- `scripts/auto_update_sparkle.swift` (Sparkle 2.x for macOS)
- `scripts/auto_update_appimage.md` (AppImageUpdate / zsync for Linux)


Deep dive in `references/distribution_playbook.md`.

### 5.2 Signing and antivirus

- Sign with `signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a MyApp.exe`
  before distribution. Unsigned binaries trigger SmartScreen and most EDRs.
  Or use the packaged helper: `powershell -File scripts/sign_windows.ps1 -File MyApp.exe`.
- macOS: use `scripts/sign_macos.sh` for codesign + notarytool + stapler.
- Submit false-positive reports to Microsoft, CrowdStrike, SentinelOne if
  AV still flags a signed binary.
- Never instruct the recipient to disable AV.

### 5.3 Auto-update

Velopack (C#, Rust, anything): `vpk pack` + `vpk install`, delta updates,
Windows installer + portable bundles. https://velopack.io -- see `scripts/auto_update_velopack.ps1`.

Squirrel.Windows (C#, Electron): git-diff updates; Windows-only -- see `scripts/auto_update_squirrel.ps1`.

WinSparkle (C++): drop-in DLL, works with Qt/wxWidgets/MFC -- see `scripts/auto_update_winsparkle.cpp`.

Electron autoUpdater: built into electron-builder; needs a release server -- pair with `scripts/build_electron.ps1`.

Sparkle (macOS): Sparkle 2.x integration -- see `scripts/auto_update_sparkle.swift`.

AppImageUpdate (Linux): self-update for AppImages -- see `scripts/auto_update_appimage.md`.

---

## Step 6 -- Verify

The universal checklist -- run before handing back:

- [ ] No clickable handler blocks the UI thread.
- [ ] All workers use the framework's correct cancellation primitive.
- [ ] Input simulation uses `SendInput` (Win) / `CGEventPost` (mac) / `XTestFakeInputEvent` (X11); never `PostMessage`, memory write, or AHK scripts.
- [ ] `EnumWindows` / equivalent runs in a thread with a 3 s timeout and a session cache.
- [ ] Every keyboard key the recipient might need is wired to a real VK / keycode constant.
- [ ] Single-file EXE launches on a clean Windows VM without the framework's runtime installed.
- [ ] Source code is bundled inside the EXE (where applicable) and self-extractable on first run.
- [ ] EXE is code-signed; AV false-positive notes are prepared if needed.
- [ ] Recipients need zero installs (no .NET SDK, no Python, no Node, no admin).
- [ ] Auto-update channel verified end-to-end (install v1 -> publish v2 -> app picks up update).
- [ ] All requirements from Step 0 are met; any deferred items are recorded with a reason.

---

## Step 7 -- Hand off

Produce a user-facing README that includes:
- What the app does (1 paragraph)
- How to install and run (exact commands)
- How to build from source (for any maintainer)
- Where logs and config live
- How to report a bug
- Known limitations and the showstopper assumption recorded in Step 0

---

## Deep references (read on demand)

- `references/task_decomposition.md` -- Step 0 + Step 3 deep dive with worked examples
- `references/framework_matrix.md` -- detailed pros/cons and IDE setup for every framework
- `references/distribution_playbook.md` -- per-framework packaging, signing, auto-update
- `references/win32_recipes.md` -- 13 common Win32 patterns
- `references/restricted_network_playbook.md` -- offline builds, vendoring, mirrors (Python / .NET / Node / Cargo / Qt)
- `INDEX.md` -- topic-based navigation: by use case, OS, framework, task

## Templates (copy-paste starting points)

- `templates/requirements_checklist.md` -- fill in during Step 0
- `templates/requirements_brief.md` -- JSON/YAML brief schema for `scripts/select_framework.py`
- `templates/task_card.md` -- one per task in Step 3
- `templates/dpi_manifest.xml` -- Per-monitor V2 awareness manifest snippet
- `templates/gui_framework_decision_tree.md` -- second-level tool picker after language choice
- `templates/release_checklist.md` -- release gate checklist
- `templates/security_checklist.md` -- security review checklist

## Examples (minimal runnable projects)

- `examples/wpf-threading/` -- C# WPF + `threading_wpf.cs`
- `examples/winui3-threading/` -- C# WinUI 3 + `threading_winui.cs`
- `examples/tkinter-threading/` -- Python tkinter + `threading_tkinter.py`
- `examples/pyside6-threading/` -- Python PySide6 + `threading_pyside6.py`
- `examples/tauri-threading/` -- Rust + Web + `threading_tauri.rs`
- `examples/msix-packaging/` -- WPF + Windows App SDK packaged as MSIX
- `examples/nativeaot-winforms/` -- WinForms NativeAOT single-file EXE
- `examples/game-automation/` -- TLBB-style: window + SendInput + threading


## Framework selection engine

`scripts/select_framework.py` scores every canonical framework against a
JSON/YAML requirements brief (schema: `templates/requirements_brief.md`)
and returns the top 3 with rationale. The selector covers all 23 canonical
frameworks in `references/framework_matrix.md` (plus Python GTK); the
matrix provides deeper pros/cons for the same options. See
`references/framework_selection_engine.md` for the scoring algorithm and
how to add a new framework.

Run `--self-test` after every change to `scripts/select_framework.py` to
confirm the 8 canonical cases still produce the expected winner.

## Tests (fixtures + smoke tests + CI)

- `tests/smoke_windows.ps1` -- PowerShell parse, Python imports,
  fixtures, arch check (45 / 45 currently pass on Windows).
- `tests/smoke_macos.sh` -- bash syntax, PowerShell parse, Python AST +
  const table, Swift `-parse` (skipped if toolchain absent).
- `tests/smoke_linux.sh` -- bash syntax, Python AST + const table for the
  Linux-side scripts (X11 + GTK).
- `tests/test_arch_awareness.ps1` -- verifies every `build_*.ps1` declares
  `-Arch` or `-Rid` with a `ValidateSet` covering the framework's
  platform-appropriate values.
- `tests/README.md` -- how to run the smoke tests locally + what CI runs.
- `tests/fixtures/sample.md` -- Markdown input for T5.3-style converter tasks.
- `tests/fixtures/sample_config.json` -- default settings for a fresh app.
- `tests/fixtures/AppxManifest.xml` -- minimal packaged-app manifest for MSIX.
- `.github/workflows/ci.yml` -- lint job plus a three-job smoke matrix on
  `windows-latest` / `macos-latest` / `ubuntu-latest`.

