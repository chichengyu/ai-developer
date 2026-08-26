# GUI framework decision tree (within one language)

This is the **second-level** decision: after Step 2 in the main SKILL.md
picks the *language* (Python, C#, Rust, etc.), pick the *UI toolkit* inside
that language. The matrix in `references/framework_matrix.md` covers
language choice. This document covers toolkit choice.

Do not silently default to the language's native UI framework. First run:

```powershell
python scripts/select_framework.py --language python
python scripts/select_framework.py --language csharp
```

The selector lists the recommended best overall first, then alternatives
with pros / cons / performance. The user makes the final call.

## Language-first candidate list

| Language | UI framework | Best for | Cons | Performance |
|---|---|---|---|---|
| Python | **PySide6** | modern widgets, grids, charts | larger EXE, slower cold start | cold ~0.6s; EXE ~70-180MB |
| Python | tkinter | zero-install tools, fastest prototype | dated look, weak 100k-row grids | cold ~0.3s; EXE ~10-40MB |
| Python | PyGObject | native GNOME/Adwaita on Linux | Windows/macOS packaging fragile | cold ~0.5s; EXE ~60MB+ |
| C# | **WPF** | Windows LOB, MVVM, Win32 interop | Windows-only | cold ~0.5s; EXE ~70MB |
| C# | WinUI 3 | Windows 11 Fluent, Store | Win10 1809+, MSIX friction | cold ~0.4s |
| C# | Avalonia | cross-platform XAML | smaller ecosystem | cold ~0.5s; EXE ~50MB |
| C# | WinForms | fastest .NET tool UI, NativeAOT | dated look, weaker grids | cold ~0.4s; EXE ~5MB |
| C# | MAUI | one codebase incl. mobile | desktop maturity behind WPF | cold ~0.5s; EXE ~80MB |
| Rust | **Tauri** | tiny EXE, web frontend | needs Rust + WebView2 story | cold ~0.2s; EXE ~5-10MB |
| Rust | Slint | true native widgets, tiny EXE | smaller ecosystem | cold ~0.2s; EXE ~3MB |
| Rust | egui | immediate-mode tools/debug UI | distinctive look | cold ~0.2s; EXE ~3-8MB |
| Go | **Wails** | Go backend + web frontend | WebView2 story, npm needed | cold ~0.3s; EXE ~5-15MB |
| Go | Fyne | pure-Go native widgets | custom look | cold ~0.3s; EXE ~10-20MB |
| Go | Gio | GPU immediate-mode | lower-level | cold ~0.2s; EXE ~5-15MB |
| Go | walk | Windows-only Win32 | Windows-only | cold ~0.2s; EXE ~5-10MB |
| C++ | **Qt 6** | cross-platform + deep OS access | GPL/paid license, large | cold ~0.2-0.4s; EXE ~20MB static |
| C++ | Win32/MFC | smallest EXE, ActiveX/OLE | boilerplate, Windows-only | cold ~0.1s; EXE ~0.5-3MB |
| TypeScript/JS | **Tauri** | tiny EXE, web UI | needs Rust backend | cold ~0.2s; EXE ~5-10MB |
| TypeScript/JS | Electron | huge ecosystem, JS-only | 150MB, 1-2s cold start | cold ~1.5s; EXE ~80-150MB |
| TypeScript/JS | Neutralino | tiny EXE, no Chromium | smaller ecosystem | cold ~0.3s; EXE ~2-5MB |
| Kotlin | **Compose Multiplatform** | modern declarative UI, mobile parity | desktop still maturing | cold ~0.6s; EXE ~80-150MB |
| Kotlin | TornadoFX | Kotlin DSL on JavaFX | JVM/JRE, less active | cold ~1s; EXE ~50-100MB |
| Java | **JavaFX** | mature JVM desktop, charts | JRE/jpackage, cold start | cold ~1s; EXE ~50-100MB |
| Swift | **SwiftUI** | Apple-first native | Windows second-class | cold ~0.2s; EXE ~5-15MB |
| Dart | **Flutter** | desktop + mobile + web parity | desktop APIs less mature | cold ~0.4s; EXE ~40-80MB |

---

## Python

```
Will the app look like a native Windows 11 app?
├── Yes, modern Fluent-style, with charts / animations
│   └── PySide6 (Qt 6 bindings)        → see scripts/threading_pyside6.py
├── Yes, modern, but I want a Qt DSL and quicker scaffolding
│   └── PyQt6 (same widget set, GPL or commercial license)
├── No, just a control panel with a few buttons + log pane
│   └── tkinter (stdlib, no install)   → see scripts/threading_tkinter.py
└── I want a web frontend (React/Vue/Svelte) inside a small wrapper
    └── Tauri (Rust) or Neutralino.js (TS); not Python
```

**Defaults**:
- Solo indie, fastest path: **tkinter**.
- Cross-platform LOB / dashboard / chart-heavy: **PySide6**.
- Internal tool with a few buttons + log pane: **tkinter** (avoid adding 80 MB of Qt for a 200-line panel).

---

## C# / .NET

```
Do I want Windows 11 Fluent design (rounded corners, mica)?
├── Yes → WinUI 3 (need Windows App SDK; MSIX-friendly)
└── No → WPF (mature, designer works, 90% of LOB apps)
         │
         ├── Is the app data-heavy (grid, charts)?
         │   └── WPF + LiveCharts2 + CommunityToolkit.Mvvm
         ├── Need full Win32 interop?
         │   └── WPF + LibraryImport (P/Invoke)
         └── Need cross-platform later?
             └── Avalonia (WPF-like XAML, runs on macOS/Linux too)
```

**Defaults**:
- Windows-only enterprise: **WPF**.
- Windows 11 modern + Store: **WinUI 3**.
- Cross-platform later: **Avalonia**.

---

## Rust

```
Is the UI a web stack (React/Vue/Svelte/SolidJS)?
├── Yes → Tauri (smallest EXE, uses system WebView2)
└── No, native widgets
    ├── True native, very small EXE, no web layer → Slint
    └── Immediate-mode, fast iteration → egui
```

**Defaults**:
- Smallest EXE + web frontend: **Tauri**.
- True native widget look: **Slint**.
- Internal tools / debug overlays: **egui**.

---

## Go

```
Is the UI a web stack?
├── Yes → Wails (v2) (Vugu/React/Vue/Svelte inside Go backend)
└── No, native widgets
    ├── General-purpose, cross-platform → Fyne
    ├── GPU-accelerated, immediate mode → Gio
    └── Windows-only with Win32 fidelity → walk
```

**Defaults**:
- Web UI + tiny EXE: **Wails**.
- Cross-platform native: **Fyne**.

---

## C++

```
Existing Qt 5/6 codebase?  → Qt 6 (Widgets or QML).
Need minimal EXE for embedded? → Qt 6 static build + windeployqt --no-translations.
Must host ActiveX / OLE?  → MFC (or Qt 5 ActiveX).
Pure system tool, no UI?  → Raw Win32 + a tiny dialog resource.
```

---

## TypeScript / JavaScript

```
Bundle size matters (< 10 MB EXE)?
├── Yes → Neutralino.js (uses WebView2 / WKWebView / WebKitGTK)
└── No, ecosystem breadth matters → Electron
```

---

## Kotlin

```
Need shared UI with Android / iOS?
├── Yes → Compose Multiplatform (Material 3, declarative)
└── No, JVM desktop only
    ├── Enterprise Java shop → TornadoFX (Kotlin DSL on JavaFX)
    └── Pure JVM with charts → JavaFX + TornadoFX
```

---

## Swift

```
Apple-first, occasional Windows port?
├── Yes → SwiftUI on macOS, AppKit bridges on Windows
└── Windows-first → SwiftPM executable + WinSDK directly (see scripts/sendinput_swift.swift)
```

---

## Quick anti-patterns

- **Electron for a 3-button panel.** You are paying 150 MB for a window with one input.
- **WinUI 3 for a server admin tool that runs on Windows Server 2019.** WinUI 3 needs Win10 1809+.
- **tkinter for a data grid with 100k rows.** Use PySide6 + QTableView with a model.
- **Tauri for a CLI tool.** It's a desktop framework; for CLI use clap or argh.
- **Compose Multiplatform on Windows in 2026.** Still maturing; expect rough edges.
- **Avalonia for a Windows-only app.** Stay on WPF unless you need macOS/Linux.
