---
name: desktop-app-dev
description: "Consultative Codex skill for shipping native cross-platform desktop GUI applications (Windows / macOS / Linux) via an 8-step workflow: deep requirements analysis, automated framework selection, task decomposition, UI responsiveness and hardware input, packaging, verification, and handoff. Ships with multi-language SendInput/window-enumeration templates, per-framework threading templates, build scripts, auto-update helpers, DPI manifest, requirements/task-card/release/security templates, and smoke-test fixtures across all three OSes."
---

# Desktop App Dev

A consultative Codex skill for shipping native cross-platform desktop GUI applications. It first digs past the literal request to surface hidden requirements, then selects a framework, decomposes the work, builds, verifies, and hands off.

## The 8-step workflow (apply in order)

| # | Step | Output | Key action |
|---|---|---|---|
| 0 | **Deep requirements analysis** | requirements.md | Six-bucket interview; record showstopper, update method, idle behavior; copy `templates/requirements_checklist.md` |
| 1 | **Classify the app** | category A/B/C/D | Bind to the hardest constraint |
| 2 | **Pick the framework** | framework decision + rationale | `python scripts/select_framework.py brief.json`; document rejection reasons for #2/#3 |
| 3 | **Decompose into atomic tasks** | tasks.md DAG | One card per task via `templates/task_card.md`; tag the showstopper |
| 4 | **Apply core patterns** | scaffold + core code | Threading, SendInput, window enum, resources, UI-01..UI-18, media pipeline |
| 5 | **Package** | installer / portable EXE | Source backup first, then build, sign, auto-update |
| 6 | **Verify** | verification report | Run the Step 6 checklist |
| 7 | **Hand off** | user-facing README + comments | Install/build/log/bug/limitations |

Do NOT skip Step 0 even if the user says "just build X fast". Hidden requirements are the #1 cause of projects that look done but aren't. Do NOT skip Step 3 even for small apps -- "build the GUI" is never one task.

## Scope and limits

### In scope

Native cross-platform desktop GUI applications. OS conventions:

| OS | Versions | Input API | Window enum API | Signing |
|---|---|---|---|---|
| Windows | 10 1809+, 11 | `SendInput` (user32) | `EnumWindows` (user32) | `signtool` + Authenticode |
| macOS | 11+ (Big Sur), Apple Silicon preferred | `CGEventPost` (Quartz) | `CGWindowListCopyWindowInfo` (Quartz) | `codesign` + `notarytool` |
| Linux | glibc 2.31+ (Ubuntu 20.04+, RHEL 9+, Debian 11+, Fedora 36+) | `XTestFakeInputEvent` (X11) or uinput (Wayland) | `XQueryTree` + `_NET_CLIENT_LIST` (X11) | per-distro |

Architecture coverage: win-x64 / win-arm64 / win-x86, macos-x64 / macos-arm64, linux-x64 / linux-arm64. All 14 `scripts/build_*.ps1` helpers accept `-Arch`; PyInstaller / dotnet publish / cargo default to host architecture; NativeAOT is win-x64 only. Full architecture matrix: `references/distribution_playbook.md`. Structural test: `powershell tests/test_arch_awareness.ps1`.

### Out of scope

- iOS / iPadOS / watchOS / visionOS and Android apps -> `mobile-app-dev`
- Web apps / SPAs, browser extensions
- CLI tools / libraries, server / headless
- Windows services / drivers
- Browser / kiosk / locked-down endpoints

If a request falls under any "Out of scope" row, **stop and tell the user** rather than silently producing a Windows desktop answer.

## When NOT to use this skill

- The deliverable is a CLI tool, library, or server.
- The deliverable is a web app, SPA, or browser extension.
- The deliverable is a mobile app.
- The user only wants a single-purpose script under ~200 lines.
- The user is researching or comparing frameworks but is not ready to commit: send `references/framework_matrix.md` as a standalone doc.
- The target is a console-mode subsystem, Windows service, or driver.
- The user is locked into one framework by team / company policy: skip Step 2 and apply Steps 0, 3, 4, 5, 6, 7 directly.

If the request is ambiguous, ask one clarifying question (the showstopper) before starting.

## 界面硬性要求（UI hard requirements）

Every desktop GUI built with this skill inherits the mandatory UI-01..UI-18 checklist below. Record each item in requirements.md during Step 0, implement it in the UI tasks, and verify it in Step 6. An item may be skipped only when the user explicitly waives it in requirements.md. Full rules, the Codex-like default palette, semantic colors, theme library URLs, and the acceptance checklist live in `references/ui_hard_requirements.md`.

| ID | 硬性要求 | 验收标准 |
|---|---|---|
| UI-01 | 全局配色统一；未指定主题时模仿 Codex 界面 | 左右导航、表格、控件共用同一套颜色令牌；按钮/图标与背景对比可见 |
| UI-02 | 全局控件样式统一 | 右键菜单、下拉框、输入框占位、滚动条、按钮、弹窗、分页共用同一套样式 |
| UI-03 | 文字与背景形成鲜明对比 | 普通文字 >= 4.5:1，大字号/图标 >= 3:1；禁用同色不可见按钮 |
| UI-04 | 布局上下左右对齐一致 | 行高、间距、基线一致；宽度/长度不足时使用滚动条或换行 |
| UI-05 | 右侧页面只显示一个表格 | 需要多个表格时另开页面/视图 |
| UI-06 | 不重复页面标题 | 左侧导航已显示菜单名时，右侧表格不再重复显示该名称 |
| UI-07 | 管理列表底部显示分页 | 总数、每页条数、页码、上/下一页，样式与全局一致 |
| UI-08 | 截断文本显示完整提示 | 省略号文本悬停时弹出完整内容框 |
| UI-09 | 每行支持设置自动刷新间隔 | 行操作栏与右键菜单都有“设置自动刷新时间间隔” |
| UI-10 | 主题中心与主题下载地址 | 内置主题 >= 3；显示主题库地址；“刷新”拉取在线主题；下载完成后按钮变为“应用” |
| UI-11 | 所有选项去重 | 菜单、下拉、主题列表等不出现重复选项 |
| UI-12 | 用户配置持久化 | 保存后的主题、布局、分页、刷新间隔等下次启动保持一致 |
| UI-13 | 左侧导航提供日志中心 | 成功/失败日志可列表查看；失败日志含原因与解决方法 |
| UI-14 | 语义色全局统一 | 危险红、警告橙、成功绿、信息蓝 |
| UI-15 | 表单编辑提供示例 | 搜索、分页、编辑表单等控件有默认值和示例文本 |
| UI-16 | 滚动条明显且图标显示 | 左侧菜单与右侧内容溢出时滚动条颜色明显；菜单图标不丢失 |
| UI-17 | 表格提示与搜索栏分行 | 提示信息不挤在搜索栏同一行；过长换行，上下溢出加滚动条 |
| UI-18 | 重型桌面端界面，禁止 Web 化 | 原生窗口/菜单/工具栏/状态栏/数据表格/右键菜单/键盘操作；不使用网页式大卡片、英雄区、浮动圆角卡片、无尽滚动等布局 |

## Step 0 -- Deep requirements analysis

Copy `templates/requirements_checklist.md` and fill it in. Do not paraphrase the user back to themselves; dig deeper. Record each UI-01..UI-18 item or an explicit waiver in requirements.md.

**Six buckets to interrogate:**

1. Functional (literal) -- what they explicitly asked for.
2. Functional (implicit) -- settings persistence, error handling, logging, crash reporting, localization, accessibility, undo/redo, auto-save.
3. Non-functional -- cold start budget, memory ceiling, CPU at idle vs peak, network assumptions, reliability, security classification.
4. Distribution -- portable EXE vs MSI vs MSIX vs Store, code-signing cert, auto-update channel, per-user vs per-machine, elevation.
5. Integration -- local files/registry/services/COM/hardware; remote HTTP/gRPC/sockets/queues; databases/auth/IPC.
6. Failure modes -- missing process, network down, disk full, permission denied, concurrent modification, corrupt config, wrong runtime.

**Three questions to always ask** (record even "don't care"):

- What is the smallest thing this app must NOT do wrong? (showstopper)
- How will recipients get updates? (forces a distribution answer)
- What does this app look like when nothing is happening? (idle behavior)

**Common omissions to flag:** logging destination, settings migration, AV false-positive handling, Windows version skew, mixed-DPI scaling, user-data backup, opt-in telemetry.

If any of these cannot be resolved before coding starts, they become explicit assumptions recorded in requirements.md.

Deep dive: `references/task_decomposition.md`.

## Step 1 -- Classify the app

Pick the one category whose hardest constraint would force a different framework. Mixed requests are normal; resolve by the binding constraint.

| Category | Typical signals | Hardest constraint |
|---|---|---|
| **A. Game automation / hardware input** | "send keys", "anti-cheat", "SendInput", game name | Hardware-level input even when not focused; anti-cheat safe |
| **B. Productivity / business** | "form", "table", "report", "dashboard", "SQL", "Excel" | Fast UI development, data-grid performance, native Windows 11 look |
| **C. System / DevOps** | "registry", "service", "driver", "P/Invoke", "COM", "ETW" | Deep OS access; Windows-only usually acceptable |
| **D. Multimedia / creative** | "GPU", "render", "OpenGL", "DirectX", "camera", "audio" | GPU access, frame budget, low-latency I/O |

If no popular framework satisfies all constraints, recommend splitting the project (e.g. a Tauri UI talking to a Rust sidecar).

## Step 2 -- Pick the framework

Use `python scripts/select_framework.py brief.json` (schema: `templates/requirements_brief.md`) for an evidence-backed ranking, or use `templates/gui_framework_decision_tree.md` / `references/framework_matrix.md` when a human decision is already close. **Always document rejection reasons for the next two candidates.**

The selector covers all 24 canonical frameworks, including C# / WPF, C# / WinForms (.NET 8+), C# / WinUI 3, .NET MAUI, Avalonia, C++ / Qt 6, Tauri, Electron, Rust + Slint, Rust + egui, Python / tkinter, Python / PySide6, Python / GTK (PyGObject), Flutter Desktop, JavaFX, Wails, Fyne, Gio, walk, Compose Multiplatform, TornadoFX, SwiftUI, and Neutralino.js. Deep pros/cons: `references/framework_matrix.md`; scoring algorithm: `references/framework_selection_engine.md`; distribution-first override and architecture matrix: `references/distribution_playbook.md`.

### Step 2.5 -- Bootstrap the toolchain (optional)

```powershell
powershell -File scripts/bootstrap_environment.ps1 -Brief brief.json -DryRun
powershell -File scripts/bootstrap_environment.ps1 -Brief brief.json -Install
powershell -File scripts/bootstrap_environment.ps1 -Framework python -Install
```

`-Brief` auto-selects the framework with `scripts/select_framework.py`; `-Framework` accepts a framework or language key directly. The mapping lives in `scripts/toolchain_map.json`. Install actions use winget and pip, so they require network access and user approval. Build helpers follow the same rule: missing CLIs are only installed when you pass `-Install`; otherwise the script fails with the exact install command.

## Step 3 -- Decompose into atomic tasks

"Build me X" is never one task. Decompose until each task is:
- Completable in one focused work session (<= a few hours).
- Independently verifiable against an acceptance criterion.
- Zero or few dependencies on other tasks.

Use `templates/task_card.md` -- one card per task.

Standard order: T1 scaffold, T2 data model/persistence, T3 core services, T4 UI shell (UI-01..UI-18 + DPI), T5 feature tasks, T6 polish, T7 integration (auto-update/telemetry/crash), T8 packaging (build/sign/hash), T9 documentation.

Variations: game automation inserts a T3.5 anti-cheat research spike; system tools start with a Win32 capability survey; multimedia adds GPU device enumeration and shader/asset pipeline.

Each card: title, description, category, concrete acceptance criteria, dependencies, S/M/L effort, risk + mitigation, verification method. Mark parallel tasks `[P]`; tag the single failure that kills the project `[showstopper]` and verify it early.

Deep dive + worked examples: `references/task_decomposition.md`.

## Step 4 -- Apply core patterns

### 4.1 UI responsiveness (the universal rule)

Every desktop framework runs UI callbacks on a single UI thread. Any blocking call (sleep, sync socket, subprocess wait, large file read, COM, DB query) freezes the window. Wrap blocking work in a background worker and post results back through the framework's safe bridge. NEVER mutate UI from the worker.

Templates: `scripts/threading_wpf.cs`, `scripts/threading_winui.cs`, `scripts/threading_tkinter.py`, `scripts/threading_pyside6.py`, `scripts/threading_tauri.rs`, `scripts/threading_glib.py`, `scripts/threading_dispatch.swift`. Full background/UI-bridge table: `references/framework_matrix.md`.

### 4.2 Hardware-level input (SendInput, anti-cheat safe)

For input that must reach a specific window even when unfocused -- including games with anti-cheat -- use `user32.SendInput` (Win), `CGEventPost` (mac), `XTestFakeInputEvent` (X11), or `uinput` (Linux Wayland). Do NOT use `PostMessage`, `SendMessage`, `keybd_event`, memory write, or AHK-style scripts.

Mandatory Windows order:
1. Find the target HWND (4.3).
2. Restore + foreground: `ShowWindow(hwnd, SW_RESTORE)` then `SetForegroundWindow(hwnd)`.
3. Build an `INPUT` struct; press with `dwFlags = 0`, release with `KEYEVENTF_KEYUP`.
4. Call `SendInput` for press, wait 30-80 ms, then send release as a separate call.
5. Add 50-150 ms jitter between key events when targeting a game.

Templates: `scripts/sendinput_*` (10 Windows languages + Java) plus `scripts/sendinput_macos.py` and `scripts/sendinput_linux.py`. The Python Windows template also ships `move_mouse`, `click`, and `scroll`. Canonical key table: `scripts/vk_table.json`; verify with `scripts/check_vk_tables.py`.

### 4.3 Window enumeration (timeout + cache, always)

Default flow on Windows:
1. Try `user32.FindWindowW(class_name, window_title)` -- O(1).
2. If title is partial or class is unknown, fall back to `EnumWindows`.
3. Always run `EnumWindows` inside a thread guarded by a 3-second timeout.
4. Cache results by `(class_name or None, title_substring)`; invalidate on refresh.

Templates: `scripts/window_enum_*` (9 Windows languages + Java, plus the Node C++ shim) and `scripts/window_enum_macos.py` / `scripts/window_enum_linux.py`.

### 4.4 Resource embedding

Per-framework asset embedding table: `references/framework_matrix.md`.

### 4.5 UI hard requirements

Apply the `界面硬性要求` section above to every view. Theme tokens, layout rules, control styles, pagination, tooltips, auto-refresh, theme center URLs, settings persistence, and log center details: `references/ui_hard_requirements.md`.

### 4.6 Media acquisition and task persistence pipeline

For media-downloader / republisher desktop apps, use the templates in `references/media_acquisition_playbook.md`:

- `scripts/media_session.py` -- cookies, proxy, retry HTTP session
- `scripts/media_parser.py` -- page parsing + HLS/m3u8 parsing
- `scripts/media_downloader.py` -- Range chunk download + resume
- `scripts/hls_downloader.py` -- m3u8 segments + AES-128 + ffmpeg merge
- `scripts/captcha_solver.py` -- third-party solver + manual fallback
- `scripts/browser_session.py` -- Playwright login / cookies / fingerprint
- `scripts/task_queue.py` -- SQLite persistent queue with crash recovery
- `scripts/ffmpeg_transcoder.py` -- transcode with live progress
- `scripts/platform_publisher.py` -- publish adapter interface
- `scripts/media_dependencies.py` -- check-only dependency manager; pass `--install` to download
- `scripts/media_pipeline_service.py` -- local HTTP sidecar with optional Bearer token
- `scripts/setup_media_dependencies.ps1` -- check / install wrapper

Client snippets: `references/media_pipeline_clients.md`; ready-made wrappers: `clients/README.md`.

## Step 5 -- Package

**Source preservation.** Build and packaging scripts never delete project source. Before packaging, create a timestamped source zip with `scripts/backup_source.ps1`, or pass `-BackupSource` to `scripts/build_python.ps1` / `scripts/build_dotnet.ps1` so the backup runs automatically before the build starts.

### 5.1 Pick the right packaging tool

Build helpers (14 `build_*.ps1`): Python, .NET, NativeAOT, Tauri, Qt, Electron, Go Wails/Fyne/Gio, Kotlin Compose, Swift, Neutralino, macOS, Linux. Shell helpers: `scripts/build_dmg.sh`, `scripts/build_appimage.sh`, `scripts/build_deb.sh`. Auto-update helpers: `scripts/auto_update_velopack.ps1`, `scripts/auto_update_squirrel.ps1`, `scripts/auto_update_winsparkle.cpp`, `scripts/auto_update_sparkle.swift`, `scripts/auto_update_appimage.md`. Exact per-framework recipes: `references/distribution_playbook.md`.

### 5.2 Signing and antivirus

- Windows: `signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a MyApp.exe`, or `powershell -File scripts/sign_windows.ps1 -File MyApp.exe`.
- macOS: `scripts/sign_macos.sh` (codesign + notarytool + stapler).
- Submit false-positive reports to Microsoft / CrowdStrike / SentinelOne if AV still flags a signed binary. Never instruct the recipient to disable AV.

### 5.3 Auto-update

Velopack (C# / Rust / Python / Electron), Squirrel.Windows (C# / Electron), WinSparkle (C++ / Qt), Sparkle (macOS), AppImageUpdate (Linux). Scripts listed in 5.1.

## Step 6 -- Verify

Run before handing back:

- [ ] No clickable handler blocks the UI thread; workers use correct cancellation.
- [ ] Input uses `SendInput` / `CGEventPost` / `XTestFakeInputEvent`; never `PostMessage`, memory write, or AHK.
- [ ] Window enumeration runs with a 3 s timeout and session cache.
- [ ] Every needed keyboard key maps to a real VK / keycode constant.
- [ ] Single-file EXE launches on a clean Windows VM without the framework runtime installed.
- [ ] Source backup zip exists when `-BackupSource` was used (or `scripts/backup_source.ps1` was run).
- [ ] EXE is code-signed; AV false-positive notes prepared if needed.
- [ ] Recipients need zero installs and no admin.
- [ ] Auto-update channel verified end-to-end (install v1 -> publish v2 -> update).
- [ ] All Step 0 requirements met; deferred items recorded with reasons.
- [ ] UI-01..UI-18 all pass; any waiver is recorded in requirements.md.

## Step 7 -- Hand off

Produce a user-facing README with: what the app does, install/run commands, build-from-source instructions, log/config locations, bug-report guidance, known limitations, and the showstopper assumption from Step 0.

## Deep references (read on demand)

- `references/task_decomposition.md` -- Step 0 + Step 3 deep dive
- `references/ui_hard_requirements.md` -- UI-01..UI-18 + theme library URLs
- `references/media_acquisition_playbook.md` -- crawl / HLS / download / transcode / publish
- `references/media_pipeline_clients.md` -- sidecar clients per desktop language
- `references/accessibility_cross_platform.md` -- UIA / MSAA / AppleScript / AT-SPI
- `references/framework_matrix.md` -- detailed pros/cons + threading/resource tables
- `references/framework_selection_engine.md` -- selector scoring algorithm
- `references/distribution_playbook.md` -- packaging/signing/auto-update + architecture matrix
- `references/nativeaot_optimization.md` -- NativeAOT trade-offs and migration
- `references/win32_recipes.md` -- 13 common Win32 patterns
- `references/restricted_network_playbook.md` -- offline builds and mirrors
- `INDEX.md` -- topic-based navigation

## Templates (copy-paste starting points)

- `templates/requirements_checklist.md`
- `templates/requirements_brief.md`
- `templates/task_card.md`
- `templates/dpi_manifest.xml`
- `templates/gui_framework_decision_tree.md`
- `templates/release_checklist.md`
- `templates/security_checklist.md`

## Examples (minimal runnable projects)

- `examples/wpf-threading/` -- C# WPF
- `examples/winui3-threading/` -- C# WinUI 3
- `examples/tkinter-threading/` -- Python tkinter
- `examples/pyside6-threading/` -- Python PySide6
- `examples/tauri-threading/` -- Rust + Web
- `examples/msix-packaging/` -- WPF + Windows App SDK MSIX
- `examples/nativeaot-winforms/` -- WinForms NativeAOT
- `examples/game-automation/` -- window + SendInput + threading

## Framework selection engine

`scripts/select_framework.py` scores a JSON/YAML requirements brief (`templates/requirements_brief.md`) across all 24 canonical frameworks and returns the top 3 with rationale. Run `--self-test` after every change to confirm the canonical cases still produce the expected winner. See `references/framework_selection_engine.md`.

## Tests (fixtures + smoke tests + CI)

- `tests/smoke_windows.ps1` -- PowerShell parse, Python imports, fixtures, source backup, arch check, examples AST, BOM regression (77 / 77 currently pass on Windows).
- `tests/test_no_bom.py` -- rejects UTF-8 BOM / U+FEFF bytes.
- `tests/smoke_macos.sh` -- bash syntax, PowerShell parse, Python AST, Swift parse (skipped if absent).
- `tests/smoke_linux.sh` -- bash syntax, PowerShell parse, Python AST for Linux scripts.
- `tests/test_arch_awareness.ps1` -- verifies every `build_*.ps1` declares `-Arch` / `-Rid`.
- `tests/README.md` -- how to run locally + what CI runs.
- `.github/workflows/ci.yml` -- lint job plus a three-job smoke matrix on `windows-latest` / `macos-latest` / `ubuntu-22.04`.
