---
name: desktop-app-dev
description: "Consultative Codex skill for shipping native cross-platform desktop GUI applications (Windows / macOS / Linux) via an 8-step workflow: requirements analysis, framework selection, task decomposition, UI responsiveness, hardware input, packaging, verification, handoff. Ships SendInput/window-enum/threading templates, build scripts, auto-update helpers, DPI manifest, templates, and smoke tests."
---

# Desktop App Dev

A consultative Codex skill for shipping native cross-platform desktop GUI applications. It first digs past the literal request to surface hidden requirements, then selects a framework, decomposes the work, builds, verifies, and hands off.

## The 8-step workflow (apply in order)

0. `requirements.md` -- six-bucket interview; record showstopper, update method, idle behavior; copy `templates/requirements_checklist.md`.
1. category A/B/C/D -- bind to the hardest constraint.
2. framework decision + rationale -- `python scripts/select_framework.py brief.json`; document rejection reasons for #2/#3.
3. `tasks.md` DAG -- one card per task via `templates/task_card.md`; tag the showstopper.
4. scaffold + core code -- threading, SendInput, window enum, resources, UI-01..UI-18, media/web pipelines.
5. installer / portable EXE -- source backup first, then build, sign, auto-update.
6. verification report -- run the Step 6 checklist.
7. user-facing README + comments -- install/build/log/bug/limitations.

Do NOT skip Step 0 even if the user says "just build X fast". Hidden requirements are the #1 cause of projects that look done but aren't. Do NOT skip Step 3 even for small apps -- "build the GUI" is never one task.

## Scope and limits

### In scope

Native cross-platform desktop GUI applications. OS conventions: Windows 10 1809+/11 uses `SendInput` + `EnumWindows` + `signtool`; macOS 11+ uses `CGEventPost` + `CGWindowListCopyWindowInfo` + `codesign`/`notarytool`; Linux glibc 2.31+ (Ubuntu 20.04+, RHEL 9+, Debian 11+, Fedora 36+) uses `XTestFakeInputEvent`/uinput + `XQueryTree`/`_NET_CLIENT_LIST`.

Architecture: win/mac/linux x64/arm64 plus win-x86; all 14 `scripts/build_*.ps1` accept `-Arch`; NativeAOT is win-x64 only. Full matrix: `references/distribution_playbook.md`; structural test: `tests/test_arch_awareness.ps1`.

### Out of scope

Mobile -> `mobile-app-dev`; web/SPA/extensions; CLI/library/server; headless Windows services/drivers; browser/kiosk/locked-down endpoints. If a request falls here, **stop and tell the user** rather than producing a Windows desktop answer.

## When NOT to use this skill

Skip when the deliverable is a CLI/library/server, web app/SPA, mobile app, single-purpose script under ~200 lines, framework research only, console-mode subsystem/service/driver, or the user is locked into one framework (skip Step 2 and apply the rest). For research-only requests, send `references/framework_matrix.md` as a standalone doc.

If the request is ambiguous, ask one clarifying question (the showstopper) before starting.

## 代码开发硬性要求（minimal-change hard requirements）

原逻辑可用则不改写；改动最小；豁免须记录。MUST open `references/minimal_change_requirements.md` and apply CODE-01..CODE-05 before code changes.

## 界面硬性要求（UI hard requirements）

Every desktop GUI built with this skill inherits mandatory UI-01..UI-18. Record each item in requirements.md during Step 0, implement it in UI tasks, and verify it in Step 6. An item may be skipped only when explicitly waived in requirements.md. MUST open `references/ui_hard_requirements.md` and apply its full rules, Codex-like palette, semantic colors, theme URLs, and acceptance checklist before UI work.

| ID | 硬性要求 |
|---|---|
| UI-01 | 全局配色统一；未指定主题时模仿 Codex 界面 |
| UI-02 | 全局控件样式统一 |
| UI-03 | 文字与背景对比鲜明 |
| UI-04 | 布局对齐一致，溢出滚动/换行 |
| UI-05 | 右侧单表格，多表格另开页 |
| UI-06 | 不重复页面标题 |
| UI-07 | 管理列表底部分页 |
| UI-08 | 截断文本悬停显示完整内容 |
| UI-09 | 行操作栏与右键菜单支持自动刷新间隔 |
| UI-10 | 主题中心 + 下载地址 + 刷新 + 应用 |
| UI-11 | 所有选项去重 |
| UI-12 | 用户配置持久化 |
| UI-13 | 左侧日志中心，失败含原因与解决 |
| UI-14 | 语义色全局统一 |
| UI-15 | 表单编辑提供示例 |
| UI-16 | 滚动条明显且菜单图标不丢失 |
| UI-17 | 表格提示与搜索栏分行 |
| UI-18 | 重型桌面端界面，禁止 Web 化 |

## Step 0 -- Deep requirements analysis

Copy `templates/requirements_checklist.md` into requirements.md and fill it in; do not just paraphrase the user. Record each UI-01..UI-18 and CODE-01..CODE-05 item or waiver. Interrogate six buckets: literal, implicit, non-functional, distribution, integration, failure modes. Always ask and record the showstopper, update method, and idle behavior (even "don't care"). Flag common omissions: logging, settings migration, AV false positives, Windows version skew, mixed-DPI, user-data backup, telemetry. Unresolved items become assumptions in requirements.md. Deep dive: `references/task_decomposition.md`.

## Step 1 -- Classify the app

Pick the one category whose hardest constraint would force a different framework; resolve mixed requests by the binding constraint.

- **A. Game automation / hardware input** -- "send keys", "anti-cheat", `SendInput`; hardware-level input even when unfocused, anti-cheat safe.
- **B. Productivity / business** -- forms, tables, reports, dashboards; fast UI + data-grid performance + native Windows 11 look.
- **C. System / DevOps** -- registry, P/Invoke, COM, ETW, service/driver GUI; deep OS access, Windows-only usually acceptable.
- **D. Multimedia / creative** -- GPU, render, OpenGL/DirectX, camera/audio; GPU access, frame budget, low-latency I/O.

If no framework satisfies all constraints, recommend splitting (e.g. Tauri UI + Rust sidecar).

## Step 2 -- Pick the framework

Use `python scripts/select_framework.py brief.json` (schema: `templates/requirements_brief.md`), or `templates/gui_framework_decision_tree.md` / `references/framework_matrix.md` when a human decision is close. **Always document rejection reasons for the next two candidates.**

The selector covers 24 canonical frameworks including C# / WinForms (.NET 8+) and Python / GTK (PyGObject); full list + pros/cons: `references/framework_matrix.md`; scoring: `references/framework_selection_engine.md`; distribution/arch: `references/distribution_playbook.md`.

### Step 2.5 -- Bootstrap the toolchain (optional)

```powershell
powershell -File scripts/bootstrap_environment.ps1 -Brief brief.json -DryRun
powershell -File scripts/bootstrap_environment.ps1 -Brief brief.json -Install
powershell -File scripts/bootstrap_environment.ps1 -Framework python -Install
```

`-Brief` auto-selects via `scripts/select_framework.py`; `-Framework` accepts a direct key (`scripts/toolchain_map.json`). Install actions use winget/pip and require network + user approval. Build helpers never auto-install missing CLIs; safe installers run only with `-Install`, others print the exact command.

## Step 3 -- Decompose into atomic tasks

"Build me X" is never one task. Decompose until each task is completable in one focused session, independently verifiable, and has few dependencies. Use `templates/task_card.md` -- one card per task.

Standard order: T1 scaffold, T2 data/persistence, T3 core services, T4 UI shell (UI-01..UI-18 + DPI), T5 features, T6 polish, T7 integration, T8 packaging, T9 docs. Mark parallel tasks `[P]`; tag the single project-killing failure `[showstopper]` and verify it early.

Each card: title, description, category, acceptance criteria, dependencies, effort, risk + mitigation, verification method. Deep dive + worked examples: `references/task_decomposition.md`.

## Step 4 -- Apply core patterns

### 4.1 UI responsiveness (the universal rule)

Every framework runs UI callbacks on one UI thread; blocking calls (sleep, sync sockets, subprocess wait, file/DB/COM) freeze the window. Wrap blocking work in a background worker and post results through the framework's safe bridge. NEVER mutate UI from the worker.

Templates: `scripts/threading_*` (30 files: 22 single-worker + 8 bounded-pool). Batch jobs use `threading_pool_*` with aggregate progress, retry, and one `cancel()`. Full contract: `references/threading_playbook.md`; quick table: `references/framework_matrix.md`.

### 4.2 Hardware-level input (SendInput, anti-cheat safe)

For unfocused-window input (including games with anti-cheat), use `user32.SendInput` (Win), `CGEventPost` (mac), `XTestFakeInputEvent` (X11), or `uinput` (Wayland). Do NOT use `PostMessage`, `SendMessage`, `keybd_event`, memory write, or AHK-style scripts.

Mandatory Windows order: find HWND (4.3) -> restore + `SetForegroundWindow` -> press via a separate `SendInput` call, wait 30-80 ms -> release with `KEYEVENTF_KEYUP`; add 50-150 ms jitter for games.

Templates: `scripts/sendinput_*` (10 Windows languages + macOS/Linux analogues); Python also ships `move_mouse`, `click`, `scroll`. Canonical keys: `scripts/vk_table.json`; verify: `scripts/check_vk_tables.py`.

### 4.3 Window enumeration (timeout + cache, always)

Default Windows flow: try `FindWindowW(class_name, title)` first; on partial/unknown titles fall back to `EnumWindows`; always run `EnumWindows` in a thread with a 3-second timeout; cache by `(class_name or None, title_substring)` and invalidate on refresh.

Templates: `scripts/window_enum_*` (9 Windows languages + Node C++ shim) and `scripts/window_enum_macos.py` / `scripts/window_enum_linux.py`.

### 4.4 Resource embedding

Per-framework asset embedding table: `references/framework_matrix.md`.

### 4.5 UI hard requirements

Apply the `界面硬性要求` section above to every view. Theme tokens, layout rules, control styles, pagination, tooltips, auto-refresh, theme center URLs, settings persistence, and log center details: `references/ui_hard_requirements.md`. For all code changes, also apply `代码开发硬性要求` CODE-01..CODE-05 from `references/minimal_change_requirements.md`.

### 4.6 Media acquisition and task persistence pipeline

For media-downloader / republisher apps, open `references/media_acquisition_playbook.md` and use `scripts/`: `media_session.py`, `media_parser.py`, `page_data_parser.py`, `media_downloader.py`, `hls_downloader.py`, `captcha_solver.py`, `scrape_guard.py`, `browser_session.py`, `task_queue.py`, `ffmpeg_transcoder.py`, `platform_publisher.py`, `media_dependencies.py` (`--install` opt-in), `media_pipeline_service.py`, `setup_media_dependencies.ps1`. Client wrappers: `references/media_pipeline_clients.md` / `clients/README.md`.

### 4.7 Web data pipeline (API collection + data processing)

For page/API collection and rule-based processing, open `references/web_data_pipeline_playbook.md` and use `scripts/`: `api_client.py`, `api_analyzer.py`, `data_processor.py`, `web_data_pipeline.py`, `security_detector.py`, `cloudflare_challenge.py`, `deep_crawler.py`, `browser_session.py`, `captcha_solver.py`, `proxy_pool.py`, `account_manager.py`, `task_scheduler.py`, `notifier.py`. The sidecar accepts `kind: "webdata"` for any desktop UI language.

## Step 5 -- Package

**Source preservation.** Build/package scripts never delete source. Before packaging, create a timestamped zip via `scripts/backup_source.ps1`, or pass `-BackupSource` to any `scripts/build_*.ps1`.

**Single-file / zero-runtime default.** Portable EXE builds default to one artifact, no target runtime, compression on, debug symbols off, and a size report. Prefer NativeAOT / Go / PyInstaller / static Qt for size; avoid Electron when size/idle RAM is budgeted; record size + idle memory in Step 6.

### 5.1 Pick the right packaging tool

Build helpers (14 `scripts/build_*.ps1`): Python, .NET, NativeAOT, Tauri, Qt, Electron, Go (Wails/Fyne/Gio), Kotlin Compose, Swift, Neutralino, macOS, Linux. Shell helpers: `build_dmg.sh`, `build_appimage.sh`, `build_deb.sh`. Auto-update: `auto_update_velopack.ps1`, `auto_update_squirrel.ps1`, `auto_update_winsparkle.cpp`, `auto_update_sparkle.swift`, `auto_update_appimage.md`. Exact recipes: `references/distribution_playbook.md`.

### 5.2 Signing and antivirus

Windows: `scripts/sign_windows.ps1` (signtool SHA256 + timestamp). macOS: `scripts/sign_macos.sh` (codesign + notarytool + stapler). Submit false-positive reports to Microsoft / CrowdStrike / SentinelOne if AV flags the signed binary; never tell recipients to disable AV.

### 5.3 Auto-update

Velopack / Squirrel / WinSparkle / Sparkle / AppImageUpdate; scripts listed in 5.1.

## Step 6 -- Verify

Run before handing back:

- [ ] No clickable handler blocks the UI thread; workers use correct cancellation.
- [ ] Input uses `SendInput` / `CGEventPost` / `XTestFakeInputEvent`; never `PostMessage`, memory write, or AHK.
- [ ] Window enumeration runs with a 3 s timeout and session cache.
- [ ] Every needed keyboard key maps to a real VK / keycode constant.
- [ ] Single-file EXE launches on a clean Windows VM without the framework runtime installed.
- [ ] Exactly one distributable artifact is produced (EXE or documented installer), and its size is recorded against the Step 0 budget.
- [ ] Idle memory is measured on a clean VM (Task Manager / Activity Monitor) and recorded against the Step 0 budget.
- [ ] Source backup zip exists when `-BackupSource` was used (or `scripts/backup_source.ps1` was run).
- [ ] EXE is code-signed; AV false-positive notes prepared if needed.
- [ ] Recipients need zero installs and no admin.
- [ ] Auto-update channel verified end-to-end (install v1 -> publish v2 -> update).
- [ ] All Step 0 requirements met; deferred items recorded with reasons.
- [ ] UI-01..UI-18 all pass; any waiver is recorded in requirements.md.
- [ ] CODE-01..CODE-05 all pass; any intentional behavior change is recorded in requirements.md.

## Step 7 -- Hand off

Produce a user-facing README with: what the app does, install/run commands, build-from-source instructions, log/config locations, bug-report guidance, known limitations, and the showstopper assumption from Step 0.

## Deep references (read on demand)

Read on demand: `references/task_decomposition.md` (Step 0+3), `references/ui_hard_requirements.md` (UI-01..18), `references/minimal_change_requirements.md` (CODE-01..05), `references/media_acquisition_playbook.md`, `references/web_data_pipeline_playbook.md`, `references/media_pipeline_clients.md`, `references/accessibility_cross_platform.md`, `references/framework_matrix.md`, `references/threading_playbook.md`, `references/framework_selection_engine.md`, `references/distribution_playbook.md`, `references/nativeaot_optimization.md`, `references/win32_recipes.md`, `references/restricted_network_playbook.md`, and `INDEX.md` (topic navigation).

## Templates (copy-paste starting points)

`templates/requirements_checklist.md`, `templates/requirements_brief.md`, `templates/task_card.md`, `templates/dpi_manifest.xml`, `templates/gui_framework_decision_tree.md`, `templates/release_checklist.md`, `templates/security_checklist.md`.

## Examples (minimal runnable projects)

`examples/wpf-threading/` (WPF), `examples/winui3-threading/` (WinUI 3), `examples/tkinter-threading/` (tkinter), `examples/pyside6-threading/` (PySide6), `examples/tauri-threading/` (Tauri), `examples/msix-packaging/` (MSIX), `examples/nativeaot-winforms/` (NativeAOT WinForms), `examples/game-automation/` (SendInput).

## Framework selection engine

`scripts/select_framework.py` ranks a JSON/YAML brief across 24 canonical frameworks and returns top 3 with rationale. Run `--self-test` after changes. See `references/framework_selection_engine.md`.

## Tests (fixtures + smoke tests + CI)

Run `tests/smoke_windows.ps1` on Windows (110 / 110 currently pass), `tests/smoke_macos.sh` / `tests/smoke_linux.sh` on macOS/Linux, and `tests/test_arch_awareness.ps1` for build scripts. Python regressions: `test_threading_templates.py`, `test_threading_concurrency.py`, `test_media_pipeline.py`, `test_docs.py`, `test_no_bom.py`. See `tests/README.md`; CI: `.github/workflows/ci.yml` on `ubuntu-22.04`.
