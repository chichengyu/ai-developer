# desktop-app-dev

Consultative Codex skill for shipping native cross-platform desktop GUI
applications.

## Entry point

`SKILL.md` -- read this first. It is a compact workflow index
(requirements -> classify -> pick framework -> decompose -> core patterns
-> package -> verify -> hand off) plus the "When NOT to use" anti-trigger.
Deep details live in `references/` and are read on demand.

## When to use

Reach for this skill whenever the user asks for:
- A new desktop GUI application.
- A rewrite / port of an existing desktop tool.
- Choosing between WPF, WinUI 3, Tauri, Electron, Qt, Python, etc.
- Adding SendInput-style hardware input (game automation, accessibility).
- Shipping a single-file EXE or an installer with auto-update.
- Migrating from one desktop framework to another.

## When NOT to use

CLI tools, libraries, web apps, mobile apps (iOS / Android),
single-purpose scripts under ~200 lines, framework-comparison-only
conversations, console-mode subsystems, Windows services, drivers.
See SKILL.md for the full list.

## Supported platforms and architectures

Cross-platform desktop GUI: **Windows 10 1809+ / 11**, **macOS 11+**, and
**Linux** (glibc 2.31+: Ubuntu 20.04+, RHEL 9+, Debian 11+, Fedora 36+).

Windows build scripts accept platform-appropriate `-Arch` values: most use
`x64|arm64|x86`, Electron uses `ia32` instead of `x86`, and NativeAOT is
`win-x64` only. `build_macos.ps1` adds `-Arch x64|arm64` (default arm64 --
Apple Silicon). `build_linux.ps1` adds `-Arch x64|arm64` (default x64).

Verify with:

```powershell
powershell -ExecutionPolicy Bypass -File tests/test_arch_awareness.ps1
```

The current 14 build scripts pass; `test_arch_awareness.ps1` reports 16 / 16 checks (14 build scripts + 2 auto-update parse checks):

```
[OK] build_dotnet.ps1 -- $Rid accepts win-x64, win-arm64, win-x86
[OK] build_dotnet_nativeaot.ps1 -- $Rid accepts win-x64
[OK] build_tauri.ps1  -- $Arch accepts x64, arm64, x86
[OK] build_electron.ps1 -- $Arch accepts x64, arm64, ia32
[OK] build_qt.ps1, build_python.ps1, ...
[OK] build_macos.ps1 -- $Arch accepts x64, arm64
[OK] build_linux.ps1 -- $Arch accepts x64, arm64
```

## Cross-platform input / windowing templates

| OS      | SendInput analogue              | Window enumeration                  |
|---------|----------------------------------|--------------------------------------|
| Windows | `scripts/sendinput_*.{py,cs,c,...}` | `scripts/window_enum_*.{py,cs,...}`   |
| macOS   | `scripts/sendinput_macos.py`     | `scripts/window_enum_macos.py`        |
| Linux   | `scripts/sendinput_linux.py`     | `scripts/window_enum_linux.py`        |

All three use the same send_key / press_combo / WindowFinder.find() API
so a single Python script can target any of them by importing the right
module at runtime.

The Windows Python template also includes mouse helpers (`move_mouse`,
`click`, `scroll`); the other language templates are keyboard-only.

## Layout

```
SKILL.md                          slim 8-step entry point + When-NOT-to-use
README.md                         this file
CHANGELOG.md                      short changelog index
changelog/                        full index + per-round detail files
LICENSE                           MIT
pyproject.toml                    ruff + mypy config
requirements-dev.txt              pinned ruff / mypy / types-requests
.gitignore                        skill-internal ignores

references/
  task_decomposition.md           Step 0+3 deep dive, worked examples
  ui_hard_requirements.md         UI-01..UI-19 mandatory UI rules + theme URLs
  minimal_change_requirements.md  CODE-01..CODE-05 minimal-change rules
  framework_selection_engine.md   scoring methodology for select_framework.py
  framework_matrix.md             detailed pros/cons + quick decision/threading/resource tables
  threading_playbook.md           worker contract, pool templates, patterns, anti-patterns, 30-template map
  distribution_playbook.md        packaging/signing/auto-update + distribution-first/arch matrix
  nativeaot_optimization.md       .NET NativeAOT deep dive
  win32_recipes.md                R1-R13 common Win32 patterns
  accessibility_cross_platform.md UIA / MSAA / AppleScript / AT-SPI deep dive
  restricted_network_playbook.md  offline builds, vendoring, local mirrors
  heavy_desktop_playbook.md       layered architecture, virtualization, long jobs, startup/memory, stability
  desktop_ui_playbook.md          tokens, theming, control catalog, keyboard, state, accessibility, UI performance
  media_acquisition_playbook.md   crawl / HLS / download / transcode / publish + queue
  web_data_pipeline_playbook.md   fingerprint browser / CAPTCHA / API collection / data processing
  media_pipeline_clients.md       sidecar clients for every desktop language

scripts/
  sendinput_* + SendInput.java (12 files: 10 Windows languages + macOS/Linux analogues)  keyboard input; Python also has mouse
  window_enum_* + WindowEnum.java (12 files: 9 Windows languages + Node C++ shim + macOS/Linux analogues)  drop-in window enumeration
  threading_*       (30 files: 22 single-worker + 8 pool templates) cancel/progress/UI bridge + bounded concurrency
  select_framework.py             auto-select language, then list UI candidates per language
  build_*.ps1       (14 helpers)  packaging helpers
  build_dmg.sh / build_appimage.sh / build_deb.sh  macOS / Linux packaging helpers
  auto_update_*                   Velopack / Squirrel / WinSparkle / Sparkle / AppImageUpdate
  bootstrap_environment.ps1       detect/install toolchains (winget/pip)
  find_python.ps1                 shared Python interpreter discovery
  toolchain_map.json              framework -> toolchain mapping
  backup_source.ps1               timestamped source zip before packaging
  vk_table.json                   canonical key table for keyboard templates
  check_vk_tables.py              verifies all Windows templates match vk_table.json
  media_*.py + hls_downloader.py  crawl, parse, chunk download, HLS
  media_formats.py                unified audio/video/image/subtitle/document/data/archive catalog
  file_converter.py               all-format convert engine (ffmpeg + stdlib + batch)
  page_data_parser.py             deep page parse + CLI: metadata, embedded JSON, API endpoints
  api_client.py                   API specs from captures + rate-limited API fetching
  smart_fetch.py                  auto multi-backend anti-bot HTTP fetch (curl_cffi/cloudscraper/httpx/urllib)
  ensure_all_dependencies.py      one-pass check/install for web-fetch + media + manifest deps
  ensure_web_fetch_dependencies.py auto-check/install optional web-fetch packages
  flaresolverr.py                 standard-library client for local FlareSolverr
  stealth_browser.py              Patchright / nodriver / DrissionPage deep solvers
  api_analyzer.py                 API manifest: auth headers, scores, data paths, pagination
  data_processor.py               declarative filter/sort/dedupe/aggregate + JSON/JSONL/CSV I/O
  web_data_pipeline.py            one-config end-to-end web data pipeline
  scrape_guard.py                 rate limit / retry / robots / adaptive throttle
  task_queue.py                   SQLite persistent task queue
  captcha_solver.py etc.          CAPTCHA auto-detect/solve, browser session + network capture, ffmpeg, publisher
  builtin_dependency_manager.py   app-local one-click runtime installer (UI-19)
  dependency_center.py            manifest-driven dependency menu + chunked install
  lazy_python_dependency.py       check/install optional Python deps on first use
  media_dependencies.py           check / install manager (default check-only)
  media_pipeline_service.py       local HTTP sidecar for any desktop UI language
  proxy_pool.py                   rotating proxy pool + named pool store
  account_manager.py              multi-account leases and session profiles
  task_scheduler.py               interval / daily / cron recurring schedules
  notifier.py                     desktop / email / webhook notifications
  setup_media_dependencies.ps1    check / install runtime dependencies
  heavy_desktop_verify.ps1        sample cold start / memory / CPU for a desktop app
  sign_windows.ps1 / sign_macos.sh code signing helpers

clients/
  media_client.*                  ready-made wrappers: TS / C# / Go / Rust /
                                  Kotlin / Swift / Java / C++

templates/
  requirements_checklist.md       Step 0 fill-in
  requirements_brief.md           JSON/YAML brief for select_framework.py
  task_card.md                    one card per atomic task
  dpi_manifest.xml                Per-monitor V2 awareness
  gui_framework_decision_tree.md  second-level tool picker
  release_checklist.md            release gate checklist
  security_checklist.md           security review checklist
  dependency_manifest.example.json fill-in dependency manifest (homepage/url per project)
  heavy_desktop_acceptance.md     heavy desktop data/performance/stability acceptance fill-in
  desktop_ui_tokens.json          one token source for color/type/spacing/dimensions
  desktop_ui_checklist.md         deep desktop UI acceptance checklist

examples/                         minimal runnable projects
  wpf-threading/                  C# WPF + threading_wpf.cs
  winui3-threading/               C# WinUI 3 + threading_winui.cs
  tkinter-threading/              Python tkinter + threading_tkinter.py
  pyside6-threading/              Python PySide6 + threading_pyside6.py
  pyside6-management/             PySide6 .ui shell: nav, loading, lazy deps, clean exit
  tauri-threading/                Rust + Web + threading_tauri.rs
  msix-packaging/                 WPF + Windows App SDK packaged as MSIX
  nativeaot-winforms/             WinForms NativeAOT single-file EXE
  game-automation/                TLBB-style bot (window + input + thread)
  media-toolkit/                  live-progress downloader + all-format converter

tests/                            smoke tests + BOM regression + fixtures
  test_no_bom.py, fixtures/sample.md, sample_config.json, AppxManifest.xml
```

## Quick recipe -- game automation bot

1. Fill `templates/requirements_checklist.md` (six-bucket interrogation).
2. Pick the language from `references/framework_matrix.md`, then run
   `python scripts/select_framework.py --language python` (or the chosen
   language) to review that language's best UI frameworks with pros/cons
   and performance before committing.
3. Decompose tasks with `templates/task_card.md`.
4. Drop in `scripts/sendinput_<lang>` + `scripts/window_enum_<lang>`.
5. Use `scripts/threading_<lang>` for the UI bridge.
6. Package with `scripts/build_python.ps1` or `scripts/build_dotnet.ps1`;
   pass `-BackupSource` (supported by every `scripts/build_*.ps1` helper)
   to keep a timestamped source zip before the build.
7. Run `scripts/auto_update_*.ps1` for the channel.
8. Or just point at `examples/game-automation/` and start customizing.

## Quick recipe -- productivity / LOB app

Same as above, but the framework matrix row is usually C# WPF or PySide6.
Add `templates/dpi_manifest.xml` to the project for crisp text on
multi-monitor setups, and apply `references/ui_hard_requirements.md`
(UI-01..UI-19) before declaring the UI done. For data-heavy / multi-window
apps, open `references/heavy_desktop_playbook.md`, copy
`templates/heavy_desktop_acceptance.md`, and measure with
`scripts/heavy_desktop_verify.ps1 -AppPath <exe> -SampleSeconds 60`.

For a ready-to-copy PySide6 starting point, use
`examples/pyside6-management/`: it loads `app.ui` with `QUiLoader`, keeps
one table per navigation page, gives every button/table a loading state,
lazy-loads optional dependencies on first use, and cancels all
`JobRunner`s/pools/child processes on close. See its `README.md` for the
`-FastStart -InstallDeps` build command. PySide6 is only for Python
projects; C#/Tauri/Electron and other languages do not need it and should
use their own UI files and dependency managers.
For deep desktop UI work, use `references/desktop_ui_playbook.md` with
`templates/desktop_ui_tokens.json` and `templates/desktop_ui_checklist.md`.

## Quick recipe -- media downloader / republisher

1. Start from `references/media_acquisition_playbook.md`.
2. Use `scripts/task_queue.py` for the persistent crawl / download /
   transcode / publish queue.
3. Drop in `scripts/media_session.py`, `media_parser.py`,
   `media_downloader.py`, and `hls_downloader.py` for acquisition.
4. Add `scripts/captcha_solver.py` and `scripts/browser_session.py` for
   login / challenge handling.
5. Transcode or convert any file with `scripts/ffmpeg_transcoder.py` /
   `scripts/file_converter.py`; query the full catalog from
   `GET /formats` or `python scripts/media_formats.py --list`; publish
   through a `scripts/platform_publisher.py` adapter.
6. Ship a built-in dependency center (UI-19): the app shows one-click
   `安装依赖`, calls `POST /deps/install` on the local sidecar, and
   automatically downloads / installs / configures Playwright / ffmpeg /
   pycryptodome into the app-local runtime with live bytes / speed / ETA.
   The same flow works outside the sidecar with
   `scripts/dependency_center.py` (manifest + menu) /
   `scripts/builtin_dependency_manager.py` or
   `scripts/setup_media_dependencies.ps1 -Install`; or install every
   optional group at once with `scripts/ensure_all_dependencies.py --install`.
7. Show live progress in the UI by polling `/tasks/<id>/progress` or using
   the `taskProgress` / `taskEvents` client wrappers with long-poll
   `timeout`; snapshots include total file size, downloaded/output bytes,
   speed, ETA, and stage. Enqueue `kind: "batch-download"` for folder
   downloads with aggregate progress, or `kind: "convert"` /
   `kind: "batch-convert"` for single-file or folder conversion with the
   same live progress contract.

## Quick recipe -- API data collection and processing

1. Start from `references/web_data_pipeline_playbook.md`.
2. Use `scripts/browser_session.py` (fingerprint, cookies, network capture)
   and `scripts/captcha_solver.py` (auto CAPTCHA) for logged-in flows.
3. Analyze pages with `scripts/page_data_parser.py`.
4. Turn captures into API specs and fetch them with `scripts/api_client.py`.
   For Cloudflare / WAF-heavy targets, add `"fetch": {"backend": "auto"}`
   so `scripts/smart_fetch.py` switches between `curl_cffi`, `cloudscraper`,
   `httpx`, and the standard-library fallback automatically. Auto mode
   defaults to `"auto_install": true`, so missing web-fetch packages are
   downloaded on first use; set it to `false` to disable. You can also run
   `scripts/ensure_web_fetch_dependencies.py` directly.
   For Managed Challenge / Turnstile, add `"browser": {"engine":
   "patchright", "browser_path": "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
   "auto_install": true}` or `"stealth_engine": "nodriver"` and use
   `scripts/flaresolverr.py` / `scripts/stealth_browser.py` for deeper
   browser-level solving.
5. Classify Cloudflare / WAF / rate-limit / CAPTCHA / login / geo blocks
   automatically with `scripts/security_detector.py`, and run
   `scripts/deep_crawler.py` when the job needs recursive link / sitemap
   discovery. For high-intensity Cloudflare challenges,
   `scripts/cloudflare_challenge.py` waits for `cf_clearance`, clicks /
   injects Turnstile, and reuses the cleared session for API calls.
6. Shape the records with `scripts/data_processor.py` and save JSON / JSONL /
   CSV.
7. Or run everything from one JSON config (`security` + `crawl` sections)
   with `scripts/web_data_pipeline.py`; desktop UIs can enqueue
   `kind: "webdata"` tasks through `scripts/media_pipeline_service.py`.

## Quick recipe -- tiny single-file portable EXE

When the deliverable must be one file that runs on a clean Windows machine
with no environment installs, use the size-lean helper for the chosen stack:

```powershell
# WinForms / tool-style apps: NativeAOT, smallest .NET option
powershell -ExecutionPolicy Bypass -File scripts/build_dotnet_nativeaot.ps1 `
  -Project examples/nativeaot-winforms/NativeAotWinFormsDemo.csproj -BackupSource

# Python tkinter / PySide6: PyInstaller onefile
powershell -ExecutionPolicy Bypass -File scripts/build_python.ps1 `
  -Entry app.py -Name MyApp -BackupSource

# Python / PySide6: fast-start OneDir build + auto install project deps
powershell -ExecutionPolicy Bypass -File scripts/build_python.ps1 `
  -Entry app.py -Name MyApp -Install -InstallDeps -FastStart

# Go Fyne / Gio: static single EXE
powershell -ExecutionPolicy Bypass -File scripts/build_go_gio.ps1 -Output MyApp.exe

# Tauri: one NSIS setup EXE (size-lean Rust release profile is automatic)
powershell -ExecutionPolicy Bypass -File scripts/build_tauri.ps1 -BackupSource
```

Every helper prints the artifact size. Record idle RAM on a clean VM as part
of Step 6; see `references/distribution_playbook.md` for the framework
size / memory table and per-framework flags.

## CI / continuous testing

`.github/workflows/ci.yml` runs a lint job plus three smoke tests on every
push / PR:

| Job               | OS             | Script                       |
|-------------------|----------------|-------------------------------|
| `lint`            | ubuntu-22.04   | `ruff check` + `ruff format --check` |
| `test-windows`    | windows-latest | `tests/smoke_windows.ps1`   |
| `test-macos`      | macos-latest   | `tests/smoke_macos.sh`      |
| `test-linux`      | ubuntu-22.04   | `tests/smoke_linux.sh`      |

Each job installs PowerShell (via brew / apt) + Python 3.12, then runs
the matching smoke test. On failure, logs are uploaded as artifacts
for 7 days. See `tests/README.md` for the full breakdown.

Run the same suite locally before pushing.

## Index

See `INDEX.md` for topic-based navigation (by use case / OS / framework
/ task). `SKILL.md` is path-based.

## Conventions in this skill

- Step numbering is 0-7; do not skip Step 0 or Step 3.
- Every task card has explicit acceptance criteria and a verification method.
- Every script has a `__main__` block that does no real hardware I/O.
- Every shipped framework has a build path and threading guidance.
- Every threading template follows the same worker contract: start, cancel,
  progress, done, error, and a framework-native UI bridge. See
  `references/threading_playbook.md`.
- Independent batch jobs use the bounded pool templates
  (`threading_pool_*`) with aggregate progress, retry, and one `cancel()`.
- Build scripts never delete project source; `-BackupSource` creates a
  timestamped zip before packaging.
- Build helpers never auto-install missing CLIs; pass `-Install` to
  install PyInstaller / tauri-cli / electron-builder / fyne / wails.
- All SendInput implementations put foreground + timing in the helper, not
  in the caller.
- Every GUI app passes `界面硬性要求` UI-01..UI-19 unless explicitly
  waived in requirements.md.
- When touching existing code, apply the `代码开发硬性要求`
  CODE-01..CODE-05 minimal-change rules unless explicitly waived in
  requirements.md.
- Examples consume canonical `scripts/` templates directly or document
  standalone packaging paths; templates stay canonical, never duplicated.
- SKILL.md stays a slim context-light entry point; deep details live in
  `references/` and are read on demand.

## Linting

```powershell
powershell -File tests/run_lint.ps1              # check-only; fails if ruff/mypy missing
powershell -File tests/run_lint.ps1 -InstallDeps # install from requirements-dev.txt, then run
pip install -r requirements-dev.txt
ruff check scripts/ tests/ examples/
ruff format --check scripts/ tests/ examples/
mypy scripts/   # CI enforces mypy; it fails the build on type errors
```
