# GUI framework decision tree (within one language)

This is the **second-level** decision: after Step 2 in the main SKILL.md
picks the *language* (Python, C#, Rust, etc.), pick the *UI toolkit* inside
that language. The matrix in `references/framework_matrix.md` covers
language choice. This document covers toolkit choice.

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
         │   └── WPF + LiveCharts2 + CommunityToolkit.Wpfdataload
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
- **Avalonia if the team already knows WPF.** Stay on WPF unless you need macOS/Linux.
