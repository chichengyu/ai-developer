---
name: desktop-app-dev
description: "Consultative Codex skill for shipping native cross-platform desktop GUI applications (Windows / macOS / Linux) via an 8-step workflow: requirements analysis, framework selection, task decomposition, UI responsiveness, hardware input, packaging, verification, handoff. Ships SendInput/window-enum/threading templates, build scripts, auto-update helpers, DPI manifest, templates, and smoke tests."
---

# Desktop App Dev

A consultative skill for shipping native desktop GUI applications. Use
this file as a compact workflow index; read the linked references on demand
instead of loading their details up front.

## The 8-step workflow (apply in order)

0. `requirements.md` -- six-bucket interview; record showstopper, update
   method, idle behavior; copy `templates/requirements_checklist.md`.
1. Category A/B/C/D -- bind to the hardest constraint.
2. Language, then UI framework -- `python scripts/select_framework.py
   brief.json`; list UI candidates with `--language <lang>`.
3. `tasks.md` DAG -- one card per task via `templates/task_card.md`.
4. Scaffold + core code -- threading, SendInput, window enum, resources,
   UI-01..UI-19, media/web pipelines.
5. Installer / portable EXE -- source backup first, then build, sign,
   auto-update.
6. Verification report -- run the Step 6 release gates.
7. User-facing README + comments -- install/build/log/bug/limitations.

Do NOT skip Step 0 or Step 3; hidden requirements and task decomposition are
the top causes of projects that look done but are not.

## Scope and limits

### In scope

Native cross-platform desktop GUI applications. Windows uses `SendInput` +
`EnumWindows` + `signtool`; macOS uses `CGEventPost` +
`CGWindowListCopyWindowInfo` + codesign/notarytool; Linux uses
`XTestFakeInputEvent`/uinput + X11 EWMH. Build scripts accept `-Arch`;
NativeAOT is win-x64 only. Full matrix:
`references/distribution_playbook.md`.

### Out of scope

Mobile, web/SPA/extensions, CLI/library/server, headless services/drivers,
and browser/kiosk/locked-down endpoints. If a request falls here, stop and
tell the user.

## When NOT to use this skill

Skip when the deliverable is a CLI/library/server, web app, mobile app,
single-purpose script under ~200 lines, framework research only, or
console-mode service. For research-only requests, send
`references/framework_matrix.md` as a standalone doc.

## 代码开发硬性要求（minimal-change hard requirements）

MUST open `references/minimal_change_requirements.md` and apply
CODE-01..CODE-05 before code changes. Keep working logic, keep diffs
minimal, prefer incremental extensions, record intentional behavior
changes, and regression-verify original functionality. Each item is
recorded as a CODE-01..CODE-05 item or waiver in requirements.md.

## 界面硬性要求（UI hard requirements）

Every desktop GUI inherits mandatory UI-01..UI-19. Record each item in
requirements.md during Step 0. MUST open `references/ui_hard_requirements.md`
and apply its full rules, palette, semantic colors, theme URLs, startup
splash, loading states, dependency center, clickable homepage links, and
acceptance checklist before UI work.

## Step 0 -- Deep requirements analysis

Copy `templates/requirements_checklist.md` into requirements.md. Record
UI-01..UI-19 and CODE-01..CODE-05 item or waiver. Interrogate six buckets:
literal, implicit, non-functional, distribution, integration, failure
modes. Record showstopper, update method, and idle behavior. Deep dive:
`references/task_decomposition.md`.

## Step 1 -- Classify the app

- A: Game automation / hardware input -> SendInput, anti-cheat safe.
- B: Productivity / business -> forms, tables, reports, dashboards.
- C: System / DevOps -> registry, P/Invoke, COM, ETW, deep OS access.
- D: Multimedia / creative -> GPU, render, camera/audio, low latency.

Resolve mixed requests by the binding constraint. If no framework fits,
recommend splitting (for example Tauri UI + Rust sidecar).

## Step 2 -- Pick the language, then the UI framework

First use `python scripts/select_framework.py brief.json` (schema:
`templates/requirements_brief.md`) to lock the language. Then list UI
frameworks for that language and let the user choose:

```powershell
python scripts/select_framework.py --language python
python scripts/select_framework.py --language csharp
```

`--language` returns the recommended best overall first, then alternatives
with pros/cons/performance. Do not silently default to a language's native
UI toolkit. Use `templates/gui_framework_decision_tree.md` /
`references/framework_matrix.md` when a human decision is close. Always
document rejection reasons for the next two candidates.

The selector covers 24 canonical frameworks including C# / WinForms (.NET 8+)
and Python / GTK (PyGObject). Scoring:
`references/framework_selection_engine.md`.

### Step 2.5 -- Bootstrap the toolchain (optional)

```powershell
powershell -File scripts/bootstrap_environment.ps1 -Brief brief.json -DryRun
powershell -File scripts/bootstrap_environment.ps1 -Brief brief.json -Install
powershell -File scripts/bootstrap_environment.ps1 -Framework python -Install
```

Install actions use winget/pip and require network + user approval. Build
helpers never auto-install; safe installers run only with `-Install`.

## Step 3 -- Decompose into atomic tasks

One card per task via `templates/task_card.md`. Standard order: T1 scaffold,
T2 data/persistence, T3 core services, T4 UI shell, T5 features, T6 polish,
T7 integration, T8 packaging, T9 docs. Mark parallel tasks `[P]` and tag the
showstopper early. Deep dive: `references/task_decomposition.md`.

## Step 4 -- Apply core patterns

### 4.1 UI responsiveness (the universal rule)

Never block the UI thread and never mutate UI from a worker. Use
`scripts/threading_*` (30 templates) with cancel/progress/error and a
framework-native bridge. PySide6 apps (Python only) register runners in
`JobRegistry` and call `shutdown_all()` on close. Full contract:
`references/threading_playbook.md`.

### 4.2 Hardware-level input

Use `SendInput` (Win), `CGEventPost` (macOS), `XTestFakeInputEvent`/uinput
(Linux). Never use `PostMessage`, `SendMessage`, `keybd_event`, memory
writes, or AHK-style scripts. Windows order: find HWND -> restore +
`SetForegroundWindow` -> press -> wait 30-80 ms -> release. Templates:
`scripts/sendinput_*`.

### 4.3 Window enumeration

Try `FindWindowW` first, then `EnumWindows` with a 3-second timeout and
cache. Templates: `scripts/window_enum_*`.

### 4.4 Resource embedding

Per-framework asset embedding table: `references/framework_matrix.md`.

### 4.5 UI hard requirements

Open `references/ui_hard_requirements.md` before UI work. Required surface:
button loading states, list/table progress bars (0-100% when available),
startup animation + progress bar for packaged EXEs, dependency center with
manifest-driven homepage links, one table per page, and clean shutdown.
The lazy optional-module helper (`scripts/lazy_python_dependency.py`) and
the PySide6 `.ui` template are Python-only. For code changes, also apply
CODE-01..CODE-05 from `references/minimal_change_requirements.md`.

### 4.6 Media acquisition

Open `references/media_acquisition_playbook.md`. Use the media scripts and
sidecar listed there for crawl / HLS / download / transcode / publish,
with live bytes/speed/ETA progress and the built-in dependency center.

### 4.7 Web data pipeline

Open `references/web_data_pipeline_playbook.md`. Use `scripts/`:
`api_client.py`, `data_processor.py`, `web_data_pipeline.py`,
`proxy_pool.py`, `account_manager.py`, `task_scheduler.py`,
`notifier.py`, `security_detector.py`, `cloudflare_challenge.py`,
`deep_crawler.py`, and related helpers for API collection, CAPTCHA, and
rule-based processing.

### 4.8 Heavy desktop architecture

Open `references/heavy_desktop_playbook.md` and copy
`templates/heavy_desktop_acceptance.md` into requirements.md. Measure with
`scripts/heavy_desktop_verify.ps1 -AppPath <exe> -SampleSeconds 60`.

### 4.9 Desktop UI architecture

Open `references/desktop_ui_playbook.md`, copy
`templates/desktop_ui_tokens.json` as the token source, and close with
`templates/desktop_ui_checklist.md`.

## Step 5 -- Package

**Source preservation.** Build scripts never delete source; use
`scripts/backup_source.ps1` or `-BackupSource`.

**Single-file / zero-runtime default.** Portable EXE builds default to one
artifact, compression on, debug symbols off, and a size report. Build
helpers (14 `scripts/build_*.ps1`) cover Python, .NET, NativeAOT, Tauri,
Qt, Electron, Go, Kotlin, Swift, Neutralino, macOS, and Linux. Python /
PySide6 can pass `-FastStart` and `-InstallDeps`. Signing, AV, auto-update,
and exact recipes: `references/distribution_playbook.md`.

## Step 6 -- Verify

Required release gates:

- No clickable handler blocks the UI thread; workers use correct
  cancellation and clean shutdown.
- Input uses SendInput/CGEventPost/XTest, never PostMessage or memory
  writes.
- Window enumeration uses timeout + cache.
- UI-01..UI-19 pass, including startup splash, list progress bars, and
  dependency center.
- CODE-01..CODE-05 pass; behavior changes are recorded.
- Single-file EXE launches on a clean VM; source backup exists.
- Smoke tests and `tests/test_arch_awareness.ps1` pass.

Full checklist: `templates/release_checklist.md`.

## Step 7 -- Hand off

Produce a user-facing README with install/run commands, build-from-source
instructions, log/config locations, bug-report guidance, known
limitations, and the showstopper assumption from Step 0.

## Deep references (read on demand)

Read on demand: `references/task_decomposition.md`,
`references/ui_hard_requirements.md`, `references/minimal_change_requirements.md`,
`references/heavy_desktop_playbook.md`, `references/desktop_ui_playbook.md`,
`references/media_acquisition_playbook.md`,
`references/web_data_pipeline_playbook.md`,
`references/media_pipeline_clients.md`,
`references/accessibility_cross_platform.md`,
`references/framework_matrix.md`, `references/threading_playbook.md`,
`references/framework_selection_engine.md`,
`references/distribution_playbook.md`,
`references/nativeaot_optimization.md`, `references/win32_recipes.md`,
`references/restricted_network_playbook.md`, and `INDEX.md` (topic
navigation).

## Templates (copy-paste starting points)

`templates/requirements_checklist.md`, `templates/requirements_brief.md`,
`templates/task_card.md`, `templates/dpi_manifest.xml`,
`templates/gui_framework_decision_tree.md`, `templates/release_checklist.md`,
`templates/security_checklist.md`,
`templates/dependency_manifest.example.json`,
`templates/heavy_desktop_acceptance.md`,
`templates/desktop_ui_tokens.json`, `templates/desktop_ui_checklist.md`.

## Examples (minimal runnable projects)

`examples/wpf-threading/`, `examples/winui3-threading/`,
`examples/tkinter-threading/`, `examples/pyside6-threading/`,
`examples/pyside6-management/`, `examples/tauri-threading/`,
`examples/msix-packaging/`, `examples/nativeaot-winforms/`,
`examples/game-automation/`, `examples/media-toolkit/`.

## Framework selection engine

`scripts/select_framework.py` ranks a requirements brief across 24 canonical
frameworks and supports `--language` for per-language UI candidate lists.
Run `--self-test` after changes. See
`references/framework_selection_engine.md`.

## Tests (fixtures + smoke tests + CI)

Run `tests/smoke_windows.ps1` on Windows (138 / 138 currently pass),
`tests/smoke_macos.sh` / `tests/smoke_linux.sh` on macOS/Linux, and
`tests/test_arch_awareness.ps1` for build scripts. Python regressions:
`test_threading_templates.py`, `test_threading_concurrency.py`,
`test_dependency_center.py`, `test_pyside6_management.py`,
`test_media_pipeline.py`, `test_docs.py`, `test_no_bom.py`. See
`tests/README.md`; CI: `.github/workflows/ci.yml` on `ubuntu-22.04`.

## Changelog

`CHANGELOG.md` is a short index. Open `changelog/INDEX.md` for the full
index, and open `changelog/rounds/<round>.md` only when you need that
round's details.
