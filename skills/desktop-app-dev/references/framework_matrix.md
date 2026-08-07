# Framework matrix (deep dive)

Detailed pros, cons, project templates, and IDE setup for every framework
in the main SKILL.md matrix. This file is broader than the automated
selector: `scripts/select_framework.py` scores all 23 canonical frameworks,
which covers every framework in this matrix plus Python GTK. Read it when
the user has narrowed the choice to two or three candidates and needs to
commit.

---

## C# / WPF (.NET 8+)

- **Best for**: Windows-only line-of-business apps, data-heavy dashboards,
  enterprise UI where Windows 11 native look matters but cross-platform does not.
- **Pros**: mature, rich data binding + templating, MVVM pattern is well-understood,
  `dotnet publish -p:PublishSingleFile=true` produces a clean EXE, easy P/Invoke to Win32.
- **Cons**: Windows-only, XAML has a learning curve, designer is OK not great.
- **Cold start**: ~0.5 s on a modern machine for a simple window.
- **EXE size**: ~70 MB self-contained, ~5 MB framework-dependent.
- **Project template**: `dotnet new wpf -n MyApp`.
- **Recommended libs**: CommunityToolkit.Mvvm (MVVM helpers), LiveCharts2 / OxyPlot
  (charts), Microsoft.Extensions.DependencyInjection (DI), Serilog (logging).
- **P/Invoke tip**: prefer `LibraryImport` (.NET 7+) over `[DllImport]` for AOT safety.

## C# / WinUI 3

- **Best for**: Modern Windows 11 look, packaged MSIX apps, Microsoft Store.
- **Pros**: native Windows 11 widgets, Fluent design, integrates with Win32 APIs.
- **Cons**: Windows 10 1809+ only, MSIX packaging adds friction, tooling still maturing.
- **Cold start**: ~0.4 s.
- **EXE size**: similar to WPF.
- **Project template**: `dotnet new winui -n MyApp` (needs Windows App SDK workload).
- **Recommended libs**: CommunityToolkit.WinUI.Controls, Microsoft.UI.Xaml, MVVM Toolkit.

## .NET MAUI

- **Best for**: Cross-platform .NET apps where one codebase targets Windows + macOS + iOS + Android.
- **Pros**: single C# codebase, XAML reuse across platforms.
- **Cons**: desktop maturity is behind WPF; some Win32 interop quirks; large download.
- **EXE size**: ~80 MB self-contained Windows build.
- **Project template**: `dotnet new maui -n MyApp`.

## Avalonia (C# / XAML)

- **Best for**: Cross-platform desktop with XAML; strongest open-source .NET UI alternative.
- **Pros**: mature cross-platform XAML, good Linux support, smaller than MAUI.
- **Cons**: smaller ecosystem than WPF, some controls behind paid tier.
- **EXE size**: ~50 MB self-contained.
- **Project template**: `dotnet new avalonia.app -n MyApp`.

## C++ / Qt 6

- **Best for**: Cross-platform apps that need both UI and deep system access;
  embedded; long-lived codebases.
- **Pros**: comprehensive widgets, QML for declarative UI, mature tooling (Qt Creator,
  qmake/CMake), signals/slots model maps cleanly to UI responsiveness rules.
- **Cons**: GPL or paid license, large dependency if dynamically linked, learning curve.
- **Cold start**: ~0.2 s with QML, ~0.4 s with QWidgets.
- **EXE size**: ~20 MB static, ~5 MB + Qt DLLs dynamic.
- **Project template**: `qtcreator` -> "Qt Widgets Application" or "Qt Quick Application".
- **Recommended libs**: QtConcurrent (worker pool), QSettings, QSerialPort, Qt Multimedia.
- **Packaging**: `windeployqt` collects Qt DLLs; `cpack -G NSIS` or `cpack -G WIX` produces installers.

## C++ / Win32 / MFC

- **Best for**: Legacy interop (ActiveX, COM, custom Win32 controls), minimal deps,
  smallest possible EXE on Windows.
- **Pros**: full control, smallest EXE, no UI framework layer between you and the OS.
- **Cons**: significant boilerplate, no designer-quality UI out of the box (unless MFC).
- **Pick MFC** when you must host ActiveX/OLE, talk to legacy Office automation,
  or extend an existing MFC codebase.
- **Pick raw Win32** only for system tools, services, or when EXE size is a hard constraint.

## Tauri (Rust + WebView)

- **Best for**: Cross-platform desktop with a web frontend (React/Vue/Svelte/SolidJS),
  small EXE, modern security model.
- **Pros**: ~5-10 MB EXE, uses system WebView2 on Windows (already installed on Win 10+),
  Rust sidecar gives full OS access, IPC between frontend and Rust is clean.
- **Cons**: requires Rust toolchain to build, WebView2 is Windows-only distribution story,
  advanced UI animations are clumsier than native.
- **Cold start**: ~0.2 s.
- **Project template**: `cargo create-tauri-app`.
- **Recommended libs**: `tauri-plugin-dialog`, `tauri-plugin-fs`, `tauri-plugin-http`,
  `tauri-plugin-store`, `tokio` for async work.
- **Packaging**: `cargo tauri build` produces NSIS + MSI in one step.

## Electron (JS/TS)

- **Best for**: Cross-platform desktop when the team is JS-only and shipping speed beats binary size.
- **Pros**: ubiquitous, huge ecosystem, hot reload, easy web tech reuse.
- **Cons**: ~150 MB installer, cold start ~1-2 s, memory hog, browser engine attacks surface.
- **Cold start**: ~1.5 s typical.
- **EXE size**: ~150 MB unpacked, ~80 MB compressed.
- **Project template**: `npm create electron-app`.
- **Recommended libs**: electron-builder (packaging), electron-updater (auto-update),
  electron-store (settings), React/Vue/Svelte for UI.
- **Note**: if your team is JS-strong and you care about size, prefer Tauri.

## Rust + Slint

- **Best for**: Embedded-style UIs, small EXE, projects that are already Rust.
- **Pros**: very small EXE (~3 MB), declarative UI markup, Rust-native event loop.
- **Cons**: smaller ecosystem than Qt, no web tech for UI.

## Rust + egui

- **Best for**: Dev tools, debug UIs, immediate-mode UIs that don't need pixel-perfect design.
- **Pros**: easy to embed, fast to iterate, small EXE.
- **Cons**: immediate-mode look is distinctive; not for polished consumer apps.

## Python / tkinter

- **Best for**: Internal tools, admin UIs, fastest prototype with zero install for the dev.
- **Pros**: stdlib (no `pip install`), instant feedback loop.
- **Cons**: looks dated without `ttk` themes, no rich widgets.
- **Recommended libs**: customtkinter (modern themed widgets), pywin32 (Win32 access),
  pystray (system tray), keyboard (global hotkeys).
- **Packaging**: PyInstaller `--onefile --windowed`.

## Python / PySide6 (Qt for Python)

- **Best for**: Python apps that need modern widgets without rewriting in C++.
- **Pros**: full Qt 6 from Python, LGPL, signals/slots model.
- **Cons**: large dependency, cold start slower than tkinter, PyInstaller bundle is big.
- **Packaging**: PyInstaller with `--hidden-import PySide6.QtCore --hidden-import PySide6.QtWidgets`.

## Flutter Desktop

- **Best for**: Cross-platform desktop with mobile parity, custom branded UI.
- **Pros**: single Dart codebase to desktop + mobile + web, expressive UI.
- **Cons**: desktop maturity still catching up to mobile; file I/O and OS APIs less mature.

## Java / JavaFX

- **Best for**: Enterprise Java shops that need cross-platform desktop.
- **Pros**: mature, free, OpenJFX is healthy.
- **Cons**: cold start ~1 s; needs JRE or `jlink` + `jpackage` for distribution.
- **Packaging**: `jpackage --type msi` (Windows) / `--type deb` / `--type dmg`.

---



## Wails v2 (Go + WebView)

- **Best for**: Cross-platform desktop with a Go backend and web frontend
  (React/Vue/Svelte/SolidJS); the Go analog of Tauri.
- **Pros**: ~5-15 MB EXE on Windows (uses system WebView2 like Tauri),
  strong Go concurrency model maps cleanly to UI responsiveness rules,
  built-in IPC (`runtime.EventsEmit` / `runtime.EventsOn`), rich plugin
  ecosystem, simpler build chain than Tauri (no Rust toolchain).
- **Cons**: WebView2 distribution story is Windows-only (WKWebView on mac,
  WebKitGTK on Linux), requires `npm` for the frontend, smaller ecosystem
  than Tauri.
- **Cold start**: ~0.3 s.
- **Project template**: `wails init -n myapp -t vanilla` (or `-t svelte`,
  `-t react`, etc.).
- **Recommended libs**: `wails-plugin-*` for dialogs/fs/store/log,
  `gorilla/websocket` for real-time, `golang.org/x/image` for image work.
- **Packaging**: `wails build` produces NSIS installer + raw EXE in
  `build/bin/`. See `scripts/build_go_wails.ps1`.
- **Auto-update**: use `wails-plugin-updater` or roll your own with
  Velopack's Go SDK.

## Fyne (Go, native widgets)

- **Best for**: Cross-platform Go apps that want a single-binary install
  with no web frontend; internal tools, simple GUIs.
- **Pros**: pure Go rendering (no WebView), single static binary, clean
  Material-style widgets, easy to bundle resources via `bundle` command,
  cross-platform out of the box.
- **Cons**: looks distinctive but not pixel-perfect Windows 11; smaller
  ecosystem than Qt/GTK; cold start slower than Tauri because it draws
  its own widgets.
- **Cold start**: ~0.5 s.
- **EXE size**: ~15-30 MB static.
- **Project template**: `go run fyne.io/fyne/v2/cmd/fyne init myapp` then
  `cd myapp && go run .`.
- **Recommended libs**: `fyne.io/fyne/v2` (core), `fyne.io/fyne/v2/dialog`,
  `fyne.io/fyne/v2/widget`, `fyne.io/fyne/v2/canvas` (custom drawing),
  `fyne.io/fyne/v2/layout`.
- **Packaging**: `fyne package -os windows -icon icon.png` produces a
  signed-or-unsigned installer. See `scripts/build_go_fyne.ps1`.
- **Resources**: `fyne bundle image.png > bundled.go`, then
  `fyne bundle -append ...` for more, build with `-tags no_bindata` to
  reduce binary size.

## Gio (Go, GPU-accelerated immediate mode)

- **Best for**: Custom-drawn UIs, GPU rendering, creative tools,
  cross-platform apps where you want to control every pixel.
- **Pros**: tiny EXE (~5 MB), GPU-accelerated (Vulkan/Metal/D3D11/OpenGL),
  immediate-mode like egui but more flexible layout, layout system that
  adapts to window size.
- **Cons**: low-level; you build widgets yourself; small ecosystem.
- **Cold start**: ~0.2 s.
- **Project template**: `gioui.org/example` for starter code; no official
  scaffold tool.
- **Recommended libs**: `gioui.org/app`, `gioui.org/layout`, `gioui.org/widget`,
  `gioui.org/font/gofont`, `gioui.org/x/*` (colorpicker, richtext,
  preferences, etc.).

## walk (Go, Win32 native)

- **Best for**: Windows-only Go apps that need native Win32 look and
  deep OS access.
- **Pros**: native Windows widgets (ListView, TreeView, TabView,
  DateTimePicker, etc.), direct access to Win32 APIs from Go, single
  static binary.
- **Cons**: Windows-only by definition; maintained by one developer;
  visual style is classic Win32 (not Fluent/Windows 11).
- **Cold start**: ~0.3 s.
- **EXE size**: ~8-15 MB static.
- **Project template**: `go get github.com/lxn/walk`, then start from
  the examples in the repo (`walk/declarative` for declarative UI).
- **Recommended libs**: `github.com/lxn/walk` (core), `github.com/lxn/win`
  (raw Win32 bindings), `github.com/lxn/walk/declarative` (XML-style UI).
- **Packaging**: `go build -ldflags "-H windowsgui -s -w" -o myapp.exe`
  for a console-less, stripped binary. No separate packaging step needed
  for portable EXE.
- **Hardware access**: `walk.Window.RunSafe(func(){...})` is the UI
  bridge from a `go func()` worker; `walk.MsgBox` for error dialogs.

---

## Quick verdict by user persona (updated)

- **Solo indie, fastest prototype**: Python tkinter or Python PySide6
- **Windows-only line-of-business**: C# WPF
- **Windows 11 modern UI, MSIX**: C# WinUI 3
- **Cross-platform + .NET team**: .NET MAUI or Avalonia
- **Cross-platform + C++ team**: Qt 6
- **Cross-platform + Rust team**: Tauri
- **Cross-platform + Rust team**: Tauri
- **Cross-platform + Go team**: Wails (web frontend) or Fyne (native widgets)
- **Windows-only + Go team**: walk (Win32 bindings)
- **Cross-platform + Go team**: Wails (web frontend) or Fyne (native widgets)
- **Windows-only + Go team**: walk (Win32 bindings)
- **Game automation**: C# or C++ (P/Invoke to Win32, SendInput)
- **Embedded / minimal EXE**: Rust + Slint or Gio (Go)
- **Data-heavy dashboards**: C# WPF + LiveCharts2, or C++ Qt + KD Chart
- **Enterprise with existing Java**: JavaFX

- **Cross-platform + Kotlin team**: Compose Multiplatform
- **Cross-platform + TS team, want tiny EXE**: Neutralino.js
- **Apple-first, want Windows too**: Swift + SwiftUI/AppKit
- **Enterprise with existing Java**: JavaFX or TornadoFX (Kotlin)

The matrix in SKILL.md is the deciding tool. This document is the
justification for the entries in that matrix when the user pushes back.

---



## Compose Multiplatform (Kotlin)

- **Best for**: Cross-platform desktop + mobile with a single Kotlin codebase
  and Jetpack Compose UI. The Kotlin analog of Flutter, but with first-class
  native interop.
- **Pros**: Modern declarative UI (same composables run on Android, iOS,
  desktop, web), strong Kotlin language (null safety, coroutines), easy
  IPC with native code via JNI, growing ecosystem.
- **Cons**: Desktop maturity is behind Android; some Compose APIs still
  mobile-first; distribution is more complex than Tauri/Electron because
  you ship a JBR (JetBrains Runtime).
- **Cold start**: ~1.5 s (heavier than Tauri/Rust because of the JBR).
- **EXE size**: ~150 MB unpacked (includes JBR); ~50 MB with custom
  JLink + JPackage bundle.
- **Project template**: `gradle init` from a Compose Multiplatform
  template, or use the IntelliJ IDEA wizard.
- **Recommended libs**: `androidx.compose.material3`, `kotlinx.coroutines`,
  `kotlinx.serialization`, `kotlinx-datetime`, `compose-multiplatform-resource`,
  Ktor client/server.
- **Packaging**: `gradle packageDistributionForCurrentOS` produces an
  MSI (Windows) / DMG (macOS) / deb+rpm (Linux). See `scripts/build_kotlin_compose.ps1`.
- **Auto-update**: roll your own (the framework is new enough that no
  dominant library exists yet); or use Velopack.

## TornadoFX (Kotlin/JavaFX DSL)

- **Best for**: JVM desktop apps that want a Kotlin DSL on top of JavaFX;
  enterprise Java shops adopting Kotlin gradually.
- **Pros**: Mature JavaFX underneath (charts, 3D, WebView), clean Kotlin
  type-safe DSL for views and binding, easier than raw JavaFX.
- **Cons**: JavaFX look is dated; smaller community than Compose
  Multiplatform; tied to the JVM.
- **Cold start**: ~1 s.
- **EXE size**: ~80 MB with JBR bundled.
- **Project template**: `gradle init` from a TornadoFX template.
- **Recommended libs**: TornadoFX core, `kotlinx.coroutines`, `kotlinx.serialization`,
  ControlsFX (extra JavaFX controls).
- **Packaging**: `jpackage --type msi --module-path ... --main-module ...`
  or TornadoFX's `gradle package` task.

## Swift / SwiftUI (Apple-first, Win is improving)

- **Best for**: macOS-first projects that want to ship to Windows too.
  Apple ecosystem (iOS / macOS / watchOS / tvOS) codebases that occasionally
  need a Windows companion build.
- **Pros**: First-class on Apple (SwiftUI is native, beautiful, declarative),
  strong type system, growing Swift on Windows toolchain.
- **Cons**: Windows support is functional but second-class; SwiftUI for
  Windows is limited (you mostly use AppKit/UWP bridges). Community and
  third-party libs on Windows are thin.
- **Cold start**: ~0.3 s on macOS.
- **EXE size**: ~5-15 MB on Windows (smaller than Compose Multiplatform).
- **Project template**: `swift package init --type executable` (cross-platform
  SwiftPM) or Xcode wizard on macOS.
- **Recommended libs**: `swift-collections`, `swift-argument-parser`,
  `swift-log`, `GRDB` (database), `Vapor` (server, for IPC).
- **Packaging**: `swift build -c release` produces an EXE. For installer,
  use `MSIX` or WiX. See `scripts/build_swift.ps1`.
- **Apple ecosystem**: Xcode, TestFlight, App Store — none apply on Windows.

## Neutralino.js (TypeScript, no Chromium bundled)

- **Best for**: TypeScript apps that want Electron-like developer experience
  but with a tiny EXE (no Chromium — uses system WebView2 / WKWebView /
  WebKitGTK).
- **Pros**: ~5 MB EXE vs Electron's ~150 MB; same Web tech (TS/JS/React/Vue);
  cold start ~0.5 s; familiar Node-like API for filesystem, OS, etc.
- **Cons**: Smaller ecosystem than Electron; some npm packages don't work
  in the browser sandbox; less mature tooling.
- **Cold start**: ~0.5 s.
- **EXE size**: ~5 MB on Windows (uses WebView2 if installed; bundles
  fallback otherwise).
- **Project template**: `npm init neutralino@latest my-app`.
- **Recommended libs**: `@neutralinojs/lib` (built-in), any framework
  (React/Vue/Svelte) for the UI, `esbuild` or `vite` for bundling.
- **Packaging**: `neu build` produces a portable folder; `neu build
  --release` for the release-mode bundle. See `scripts/build_neutralino.ps1`.

---

