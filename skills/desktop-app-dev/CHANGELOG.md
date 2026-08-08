# Changelog

All notable improvements to this skill. Newest entries first.

## 2026-08-08 (round 41) -- Heavy desktop + desktop UI deep enhancement

### Added

- `references/heavy_desktop_playbook.md` -- layered architecture + DI,
  virtualization / paging matrix, long-running job persistence,
  startup/memory profiling, single-instance / crash readiness, plugin
  isolation, and 100k-row acceptance.
- `references/desktop_ui_playbook.md` -- design tokens, theme registry,
  control catalog, layout, data grids, keyboard interaction, state
  management, accessibility, and UI performance.
- `templates/heavy_desktop_acceptance.md` -- fill-in acceptance for data
  volume, architecture, long jobs, performance, stability, windows, and
  plugins.
- `templates/desktop_ui_tokens.json` -- one token source with light / dark /
  high-contrast colors, typography, spacing, radii, dimensions, and motion.
- `templates/desktop_ui_checklist.md` -- deep UI acceptance across theming,
  layout, controls, interaction, accessibility, performance, and
  screenshots.
- `scripts/heavy_desktop_verify.ps1` -- starts or attaches to a desktop
  app, measures cold start / working set / private memory / CPU, and writes
  an optional JSON report; includes `-SelfTest`.

### Docs

- `SKILL.md` adds Step 4.8 (heavy desktop) and Step 4.9 (desktop UI),
  new Step 6 release gates, and links to the new references / templates.
- `README.md`, `INDEX.md`, and `references/ui_hard_requirements.md` add
  entry points for heavy desktop and deep desktop UI work.

### Tests

- `tests/test_docs.py` verifies the two new playbooks, acceptance
  templates, token JSON, and `heavy_desktop_verify.ps1`.
- `tests/smoke_windows.ps1` adds the profiler self-test and heavy/UI
  wiring checks; 123/123 pass.

## 2026-08-08 (round 40) -- Build helper output/arch/Costura fixes

### Fixed

- `scripts/build_linux.ps1` now honors `-OutputDir` for both Go and
  PyInstaller branches; Go creates the output directory before building,
  and PyInstaller writes through `--distpath` / `--workpath` / `--specpath`
  instead of dumping into `./dist`.
- `scripts/build_electron.ps1` now passes
  `-c.directories.output=$OutputDir` to electron-builder and scans the
  configured directory instead of hardcoded `dist`.
- `scripts/build_dotnet.ps1` no longer treats `-Costura` as a silent
  no-op: it validates the project references `Costura.Fody` and has
  `FodyWeavers.xml`, and explains the requirement when missing.
- `scripts/build_kotlin_compose.ps1` warns when `-Arch` differs from the
  host because Compose Desktop packaging is host-bound.
- `scripts/build_macos.ps1` no longer uses PowerShell-7-only
  `Split-Path -LeafBase`; scheme names now resolve with
  `GetFileNameWithoutExtension()`.

### Docs

- `references/ui_hard_requirements.md` adds heavy desktop data /
  performance rules under UI-18: virtualization or paging for long
  lists/grids, data-layer filtering, layered architecture, and 100k-row
  verification before release.

### Tests

- `tests/smoke_windows.ps1` adds 5 static regression checks for the fixes
  above and `tests/test_docs.py` locks the new heavy-desktop terms;
  119/119 pass.

## 2026-08-08 (round 39) -- UI-19 built-in dependency center + app-local manager

### Added

- Global hard requirement `UI-19 内置依赖中心`: every desktop app that
  needs an external runtime (ffmpeg / tesseract / ImageMagick / Playwright
  Chromium / 7z, etc.) manages it inside the app; the user clicks
  `安装依赖`, and the app automatically downloads / installs / configures
  with live bytes, speed, ETA, and stage. No terminal commands, no manual
  PATH editing, no global install, no interactive prompts.
- `scripts/builtin_dependency_manager.py` -- generic app-local dependency
  manager: JSON manifest, check-only default, parallel chunked resumable
  downloads, SHA-256 verification, safe zip/tar extraction, portable /
  archive / pip / detect kinds, app-local bin paths, and environment
  configuration.
- `scripts/media_dependencies.py` -- ffmpeg zip now downloads through the
  chunked concurrent resumable downloader with a local cache and live
  bytes / speed / ETA progress instead of a single-stream fetch.

### Docs

- `SKILL.md`, `README.md`, `INDEX.md`,
  `references/ui_hard_requirements.md`,
  `templates/requirements_checklist.md`,
  `templates/release_checklist.md`,
  `references/media_acquisition_playbook.md`, and
  `references/media_pipeline_clients.md` updated with UI-01..UI-19 and
  the built-in dependency center contract.

### Tests

- `tests/test_media_pipeline.py` -- 3 new cases (archive install with
  checksum, portable install + checksum mismatch, check-only default);
  81/81 pass.

## 2026-08-08 (round 38) -- Unified all-format catalog + generic conversion + batch progress

### Added

- `scripts/media_formats.py` -- unified format registry covering video,
  audio, image, subtitle, document, data, and archive targets, with
  ffmpeg / stdlib / copy / optional engine hints, `lookup_format()`,
  `catalog_payload()`, and a `--list` / `--lookup` CLI.
- `scripts/file_converter.py` -- generic single-file and folder conversion:
  ffmpeg for media/images, stdlib for text / markdown / HTML / CSV / JSON /
  JSONL / XML / INI / SRT / VTT / ASS and ZIP/TAR/GZ/BZ2/XZ archives, plus
  safe `extract_archive()` and aggregate byte-based `convert_many()`
  progress.
- `scripts/ffmpeg_transcoder.py` -- expanded format presets and container
  mappings: m2ts/mts, mpeg, flv, wmv, m4v, 3gp, ogv, vob, asf, mka, oga,
  aiff, wma, amr, mp2, dts, eac3, m4b, alac, and jpg/png/bmp/tiff/webp/
  avif/heic/jxl/ico image targets, plus per-codec quality args and
  single-frame image extraction.
- `scripts/media_downloader.py` -- checkpoint validation against ETag /
  Last-Modified, optional `expected_sha256` verification, `content_type` /
  `filename` on `DownloadResult`, and `download_batch()` with aggregate
  bytes, speed, ETA, and per-file progress.
- `scripts/media_pipeline_service.py` -- `GET /formats` plus
  `kind: "convert"`, `kind: "batch-convert"`, and
  `kind: "batch-download"` tasks with the same live progress/event
  contract.
- `clients/*` -- `formats()` / `Formats()` / `FormatsAsync()` wrappers in
  TypeScript, C# / .NET, Go, Rust, Kotlin, Swift, Java, and C++.
- `examples/media-toolkit/` -- runnable tkinter demo with live download
  percent / total size / speed / ETA and an all-format conversion tab.

### Tests

- `tests/test_media_pipeline.py` -- 6 new cases (format catalog/profile
  integration, text/archive/subtitle/batch conversion, ffmpeg dispatch +
  optional-target error, ETag/hash download integrity, batch download
  progress, sidecar formats + convert tasks); 78/78 pass.

### Docs

- `README.md`, `SKILL.md`, `INDEX.md`,
  `references/media_acquisition_playbook.md`,
  `references/media_pipeline_clients.md`, `clients/README.md`,
  `examples/README.md`, and `tests/README.md` updated with the unified
  format catalog, conversion kinds, batch progress, and the new example.

## 2026-08-08 (round 37) -- Live long-poll events + download throttle + real ffmpeg progress

### Added

- `scripts/ffmpeg_transcoder.py` -- every generated ffmpeg command now
  includes `-progress pipe:1 -nostats`, so real encodes emit live
  `out_time_ms` / `total_size` / `fps` / `bitrate` / `frame` progress
  instead of only parsing fake output.
- `scripts/media_downloader.py` -- shared `SpeedLimiter` and
  `max_speed_bytes_per_sec` download option; total throughput is capped
  across all shards while keeping adaptive concurrency and resume.
- `scripts/media_pipeline_service.py` -- task events support long polling
  via `GET /tasks/<id>/events?after=N&timeout=0..30`; the request waits
  for the next event instead of returning immediately.
- `clients/*` -- `taskEvents(id, after, timeout)` wrappers now expose the
  long-poll timeout in TypeScript, C# / .NET, Go, Rust, Kotlin, Swift,
  Java, and C++.

### Tests

- `tests/test_media_pipeline.py` -- 3 new cases (speed limiter throttle,
  download speed-limit integration, sidecar long-poll events) plus
  assertions that generated ffmpeg args contain the real progress flags;
  72/72 pass.

### Docs

- `references/media_acquisition_playbook.md`,
  `references/media_pipeline_clients.md`, and `clients/README.md` updated
  with `max_speed_bytes_per_sec`, `-progress pipe:1 -nostats`, and the
  long-poll event API.

## 2026-08-08 (round 36) -- Real-time progress snapshots + total size + richer formats

### Added

- `scripts/media_downloader.py` -- automatic shard sizing for small files,
  `probe` / `merge` / `done` progress snapshots with total file size,
  downloaded bytes, percent, speed, window `speed_avg`, ETA, chunk counts,
  merge progress, and elapsed time; `DownloadResult` now returns elapsed
  time and average speed.
- `scripts/ffmpeg_transcoder.py` -- rich transcode snapshots
  (`input_size`, `output_size`, `duration_s`, `remaining_s`, `fps`,
  `bitrate`, `frame`, `state`), a `finalize` event with the real output file
  size, new format profiles (`avi`, `ts`, `ogg`, `opus`, `aac`, `ac3`,
  `gif`), and `start_time` / `duration` / `threads` options.
- `scripts/hls_downloader.py` -- HLS progress now reports downloaded bytes
  and the final merged output size.
- `scripts/task_queue.py` / `scripts/media_pipeline_service.py` -- SQLite
  `progress_meta` column with migration, persisted progress snapshots,
  richer task events, `GET /tasks/<id>/progress`, and payload forwarding
  for `auto_chunk_sizing`, `start_time`, `duration`, and `threads`.
- `clients/*` -- `taskProgress` / `taskEvents` in TypeScript, C# / .NET,
  Go, Rust, Kotlin, Swift, Java, and C++; TypeScript and Go also ship a
  `watchProgress` helper that polls until the task finishes.

### Tests

- `tests/test_media_pipeline.py` -- 5 new cases (progress metadata
  persistence, download total-size snapshots, auto chunk sizing, rich
  transcode progress, sidecar progress endpoint); 69/69 pass.

### Docs

- `references/media_acquisition_playbook.md`,
  `references/media_pipeline_clients.md`, `clients/README.md`, `SKILL.md`,
  `README.md`, and `INDEX.md` updated with the live progress snapshot
  contract, richer format presets, and client polling helpers.

## 2026-08-08 (round 35) -- Extreme download + format transcode deep enhancement

### Added

- `scripts/media_downloader.py` -- adaptive AIMD concurrency with a
  sliding-window speed tracker (live speed / ETA in progress), slow-shard
  restart with per-chunk cancellation and restart limit, and a 1-byte
  Range GET fallback when HEAD hides the file size.
- `scripts/media_session.py` -- `Content-Range` parsing so chunked resume
  works even when servers omit `Accept-Ranges`.
- `scripts/hls_downloader.py` -- segment retries with backoff,
  `#EXT-X-BYTERANGE` byte-range segments, `#EXT-X-MAP` init segment
  download, suffix-aware segment naming, and direct concatenation
  fallback when ffmpeg is absent.
- `scripts/media_parser.py` -- `#EXT-X-MAP`, `#EXT-X-BYTERANGE`, and
  `#EXT-X-ENDLIST` parsing with sequential byte-range offsets.
- `scripts/ffmpeg_transcoder.py` -- named format presets
  (mp4/mp4-hq/hevc/hevc-hq/webm/mp3/m4a/wav/flac/mkv/mov), GPU encoder
  auto-detection (NVENC/AMF/QSV/VideoToolbox), smart copy/remux when
  source codecs already match the target, resolution/bitrate/fps/audio
  options, `build_ffmpeg_args()` for testable command construction, and a
  `--list-profiles` CLI.
- `scripts/media_pipeline_service.py` -- download / HLS / transcode
  payload options forwarded to the engine plus `POST /media/probe` for
  local media inspection.

### Tests

- `tests/test_media_pipeline.py` -- 8 new cases (speed tracker/tuning,
  adaptive download, Content-Range fallback, HLS BYTERANGE / init /
  fallback merge, transcode presets / hardware / copy, fake-ffmpeg
  progress, sidecar probe, sidecar transcode options); 64/64 pass.

### Docs

- `references/media_acquisition_playbook.md` and
  `references/media_pipeline_clients.md` updated with the new download,
  HLS, transcode, and probe APIs.

## 2026-08-08 (round 34) -- Slim SKILL.md with mandatory hooks

### Changed

- `SKILL.md` -- compressed from 25,529 to 16,264 bytes. UI-01..18 keep a
  compact ID/requirement table; full acceptance criteria stay in
  `references/ui_hard_requirements.md`. Media/web script lists became
  compact scenario indexes with all script paths retained.
- Mandatory application hooks kept: MUST open
  `references/ui_hard_requirements.md` before UI work, MUST open
  `references/minimal_change_requirements.md` before code changes, Step 0
  records UI-01..18 + CODE-01..05, Step 4.5 applies both, Step 6 verifies
  both.

### Tests

- `tests/test_docs.py` now guards the mandatory-open hooks and the
  Step 0 UI+CODE recording rule.

### Verified

- test_docs.py -- 789 checks
- test_no_bom.py -- 215 files, 0 BOM / U+FEFF
- smoke_windows.ps1 -- 110 / 110
- ruff check / ruff format --check -- green
- SKILL.md -- 16,264 bytes

## 2026-08-08 (round 33) -- Minimal-change hard requirements

### Added

- `SKILL.md` -- `代码开发硬性要求（minimal-change hard requirements）`
  compact rule set: keep working original logic, minimal diff, explicit
  waiver; full CODE-01..CODE-05 checklist moved to
  `references/minimal_change_requirements.md`.
- `references/minimal_change_requirements.md` -- canonical CODE-01..CODE-05
  rules with acceptance criteria and decision rules.
- `templates/requirements_checklist.md` and `templates/release_checklist.md`
  now carry CODE-01..CODE-05 record/waiver and release gates.
- `tests/test_docs.py` -- structural checks for the CODE-01..CODE-05
  heading, reference file, template wiring, and README/INDEX coverage.

### Docs

- `SKILL.md` Step 4.5 and Step 6 now apply CODE-01..CODE-05 to all code
  changes; `README.md` and `INDEX.md` document the minimal-change rules.

### Verified

- test_docs.py -- 786 checks
- test_no_bom.py -- 215 files, 0 BOM / U+FEFF
- SKILL.md size -- 25,529 bytes (<= 25 KiB)

## 2026-08-08 (round 32) -- Bounded pool concurrency deep enhancement

### Added

- `scripts/threading_pool.py` -- runtime-safe Python worker pool with
  bounded concurrency, aggregate `BatchProgress`, per-item progress,
  `RetryPolicy`, fail-fast, and cooperative cancellation.
- 7 more pool templates: `threading_pool_tkinter.py`,
  `threading_pool_pyside6.py`, `threading_pool_csharp.cs`,
  `threading_pool_tauri.rs`, `threading_pool_kotlin_compose.kt`,
  `threading_pool_electron.ts`, and
  `threading_pool_electron_worker.ts`. The `scripts/threading_*` set is
  now 30 files (22 single-worker + 8 pool).
- `tests/test_threading_concurrency.py` -- runtime checks for bounds,
  retry, cancel, progress aggregation, per-item errors, and fail-fast;
  wired into the Windows / macOS / Linux smoke suites.
- `references/threading_playbook.md` and `framework_matrix.md` now carry
  pool-template tables, aggregate-progress rules, retry/backoff,
  backpressure, and cancellation fan-out guidance.

### Docs

- `SKILL.md`, `README.md`, `INDEX.md`, and `tests/README.md` updated with
  the 30-template map and pool-first guidance for batch work.

### Verified

- smoke_windows.ps1 -- 110 / 110
- test_docs.py -- 766 checks
- threading templates -- 22 / 22 single + 8 / 8 pool
- threading concurrency -- 5 / 5
- media pipeline -- 56 / 56
- test_no_bom.py -- 214 files, 0 BOM / U+FEFF
- arch awareness -- 16 / 16
- ruff check / ruff format --check / mypy scripts/ -- all green

## 2026-08-08 (round 31) -- Deep threading enhancement

### Added

- 15 new threading templates: WinForms, Avalonia, .NET MAUI, Electron
  (main + worker), Qt 6, Wails, Fyne, walk, egui, Slint, JavaFX, Compose,
  Flutter, and Win32 C. The `scripts/threading_*` set is now 22 files.
- `references/threading_playbook.md` -- worker contract, 22-template map,
  patterns (worker pools, sequential queues, fan-out, progress throttling,
  state handoff, COM apartments, dispatcher lifetime), anti-patterns, and a
  Step 6 checklist.
- `tests/test_threading_templates.py` -- source-level contract check for
  every threading template (cancel, progress, error, UI bridge); wired
  into the Windows / macOS / Linux smoke suites.
- `tests/test_docs.py` now enforces the playbook registration and the
  22-template count.

### Fixed

- `scripts/threading_dispatch.swift` -- rewritten to a clean
  `Task.detached` + `@MainActor` contract; the previous Task signature was
  not usable as a job bridge.
- WPF / WinUI templates now support `onCancel`, dispose the
  `CancellationTokenSource`, and reject starting without a UI dispatcher.
- PySide6 template now honors the `auto_delete` option.

### Docs

- `SKILL.md`, `README.md`, `INDEX.md`, `framework_matrix.md`, and
  `CONTRIBUTING.md` updated with the 22-template map and playbook pointer.

### Verified

- smoke_windows.ps1 -- 105 / 105
- test_docs.py -- 754 checks
- threading templates -- 22 / 22
- media pipeline -- 56 / 56
- test_no_bom.py -- 205 files, 0 BOM / U+FEFF
- arch awareness -- 16 / 16
- select_framework.py -- self-test pass
- ruff check / ruff format --check / mypy scripts/ -- all green

## 2026-08-08 (round 30) -- Library entry points and doc drift fixes

### Added

- Every Python script under `scripts/` now ships a `__main__` block; 16
  library modules gained a no-I/O import/usage entry point so the README
  convention is fully met.
- `tests/test_docs.py` now enforces the `__main__` convention for every
  Python script under `scripts/`.

### Fixed

- `SKILL.md` Step 2.5 no longer claims every build helper supports
  `-Install`; only helpers with a safe installer (PyInstaller / tauri-cli /
  electron-builder / fyne / wails) install on `-Install`, and the rest fail
  with the exact install command.
- `README.md` and `INDEX.md` arch wording now says the structural test
  reports 16 / 16 checks (14 build scripts + 2 auto-update parse checks).
- `tests/test_media_pipeline.py` suppresses the expected stderr message
  from the deliberate 404 fetch in `test_web_data_pipeline_deep_crawl`, so
  the final verification summary is clean.

### Verified

- smoke_windows.ps1 -- 103 / 103
- test_docs.py -- 720 checks
- media pipeline -- 56 / 56
- test_no_bom.py -- 188 files, 0 BOM / U+FEFF
- arch awareness -- 16 / 16
- select_framework.py -- self-test pass
- ruff check / ruff format --check / mypy scripts/ -- all green

## 2026-08-08 (round 29) -- Single-file zero-runtime packaging optimization

### Added

- `scripts/build_python.ps1` -- `--noupx` and safe `-ExcludeModules`
  defaults, plus a printed EXE size report.
- `scripts/build_dotnet.ps1` -- compression on / symbols off by default,
  ReadyToRun and trimming are now opt-in, invariant globalization default.
- `scripts/build_dotnet_nativeaot.ps1` -- invariant globalization and no
  debug symbols, keeping NativeAOT as the smallest .NET path.
- `scripts/build_qt.ps1` -- minimal `windeployqt` flags
  (`--no-translations --no-system-d3d-compiler --no-opengl-sw
  --no-compiler-runtime`) and portable-folder size report.
- `scripts/build_tauri.ps1` -- NSIS single-installer default and automatic
  size-lean Rust release profile via Cargo env vars, with artifact size
  reporting.
- `scripts/build_electron.ps1` -- `compression=maximum`, `asar`, and a
  clear warning that Electron is the wrong default for small size / RAM.
- Go helpers (`build_go_wails.ps1`, `build_go_fyne.ps1`,
  `build_go_gio.ps1`) -- stripped binaries, hidden console, and
  `-trimpath -buildvcs=false` by default.
- `scripts/build_swift.ps1` -- `-Osize` default and EXE size report.
- `scripts/build_macos.ps1` / `build_linux.ps1` -- same compression /
  symbol / Rust-profile defaults for dotnet, cargo, go, and python paths.
- Docs: `references/distribution_playbook.md` size / memory table and
  per-framework flags; SKILL.md Step 5/6 single-file and idle-memory gates;
  README / INDEX quick recipes; `templates/release_checklist.md` gates.
- Tests: 10 new packaging-optimization regression checks in
  `tests/smoke_windows.ps1` plus matching doc-audit terms.

### Verified

- smoke_windows.ps1 -- 103 / 103
- test_docs.py -- 683 checks
- media pipeline -- 56 / 56
- test_no_bom.py -- 188 files, 0 BOM / U+FEFF
- select_framework.py -- self-test pass
- ruff check / ruff format --check / mypy scripts/ -- all green

## 2026-08-08 (round 28) -- Cloudflare high-intensity challenge handling

### Added

- `scripts/cloudflare_challenge.py` -- dedicated high-intensity Cloudflare
  handler: stage classification (`js_challenge`,
  `managed_non_interactive`, `turnstile_captcha`, `blocked`), `cf_clearance`
  cookie waiting, Turnstile checkbox interaction, third-party token
  injection, reload retries, and `needs_new_session` proxy-rotation signal.
- `web_data_pipeline.py` -- new `cloudflare` config section. After the
  challenge passes, the pipeline reuses the browser user agent,
  `cf_clearance` cookie, and pinned proxy for subsequent API fetches so the
  clearance is not invalidated by an IP / UA mismatch.
- `security_detector.py` -- Cloudflare challenge findings now include stage,
  sitekey, frame URL, ray ID, and clearance-cookie presence details.

### Docs

- `references/web_data_pipeline_playbook.md`, `SKILL.md`, `README.md`, and
  `INDEX.md` -- Cloudflare high-intensity workflow and `cloudflare` config.
- `tests/test_media_pipeline.py` -- Cloudflare state extraction and fake
  browser challenge-handler tests.

### Verified

- media pipeline -- 56 / 56
- test_docs.py -- 671 checks
- test_no_bom.py -- 188 files, 0 BOM / U+FEFF
- smoke_windows.ps1 -- 93 / 93
- arch awareness -- 16 / 16
- ruff check, ruff format --check, mypy scripts/ -- all green

## 2026-08-08 (round 27) -- Automatic security identification + deep crawling

### Added

- `scripts/security_detector.py` -- classifies Cloudflare challenge / block,
  WAF, rate limit, CAPTCHA, login wall, cookie consent, JS required, geo
  block, empty page, and SPA shell responses into an actionable
  `SecurityReport`. `WebDataPipeline` uses the report to retry, rotate
  proxy, escalate to the fingerprint browser, or skip without user input.
- `scripts/deep_crawler.py` -- BFS deep crawler over links and sitemaps with
  robots.txt, same-host / include / exclude filters, depth and page limits,
  URL deduplication, and blocked-page skipping. Includes a standalone CLI.
- `MediaSession.get_bytes_with_meta()` and non-raising
  `request_json_with_meta()` now return body, status, and headers for
  4xx / 5xx responses. `ApiFetchResult` keeps `status`, `headers`, and a
  `security` report instead of only a generic exception.
- `PageDataAnalysis.links` and `BrowserSession.wait_for_challenge()`.
  `web_data_pipeline.py` accepts `security` and `crawl` config sections.
- `RobotsPolicy.sitemap_urls()` plus raw robots text access.

### Docs

- `references/web_data_pipeline_playbook.md` -- new automatic security
  identification and deep crawling sections, plus API failure metadata
  notes.
- `SKILL.md`, `README.md`, and `INDEX.md` -- pointers to the new scripts and
  config sections.
- `tests/test_media_pipeline.py` -- security classifier, deep crawler,
  HTTP error metadata, and pipeline crawl integration tests.

### Verified

- media pipeline -- 54 / 54
- test_docs.py -- 663 checks
- test_no_bom.py -- 187 files, 0 BOM / U+FEFF
- smoke_windows.ps1 -- 92 / 92
- arch awareness -- 16 / 16
- ruff check, ruff format --check, mypy scripts/ -- all green

## 2026-08-08 (round 26) -- Proxy pools, multi-account, schedules, notifications

### Added

- `scripts/proxy_pool.py` -- round-robin / random proxy pool with failure
  cooldown plus a named `ProxyPoolStore` for sidecar-managed pools.
  `MediaSession`, `ApiClient`, and `WebDataPipeline` now rotate proxies on
  retry without changing their existing APIs.
- `scripts/account_manager.py` -- persistent multi-account profiles with
  storage state, cookie files, browser profile dirs, proxies, headers, and
  login config. Tasks lease one account at a time; failed accounts cool
  down before reuse.
- `scripts/task_scheduler.py` -- interval / daily / cron / once schedules
  persisted in the same SQLite database as the task queue, with a sidecar
  loop that enqueues due tasks.
- `scripts/notifier.py` -- best-effort completion notifications through
  desktop toast, SMTP email, and webhook.
- Sidecar endpoints: `/proxy-pools`, `/accounts`, `/schedules`, and
  `/notifications/status` / `/notifications/test`. `POST /tasks` also
  accepts `run_after_seconds` for one-shot delayed tasks.
- Per-task controls: `"account": "<name>"`, `"proxy_pool": ...`,
  `"auto_retry": false`, `"retry_delay_seconds": N`, and
  `"notify": false`.

### Docs

- `references/web_data_pipeline_playbook.md` -- new sections for proxy
  pools, multi-account sessions, scheduled tasks / retry, and notifications.
- `SKILL.md`, `README.md`, `INDEX.md`, and
  `references/media_acquisition_playbook.md` -- advanced automation
  pointers and sidecar endpoint references.

### Verified

- `smoke_windows.ps1` -- 90 / 90
- `test_docs.py` -- 647 checks
- `test_no_bom.py` -- 185 files, 0 BOM / U+FEFF
- media pipeline -- 48 / 48
- arch awareness -- 16 / 16
- ruff check, ruff format --check, mypy scripts/ -- all green

## 2026-08-08 (round 25) -- x64 selector weights, safe staging, universal source backup

### Fixed

- `scripts/select_framework.py` -- architecture weighting now distinguishes
  `macos-x64` / `linux-x64` from arm64. `macos x64` no longer weights
  `macos_arm64_arch`, Linux x64 now scores per-arch instead of being
  ignored, and all seven architecture dimensions have human-readable labels.
- `scripts/build_qt.ps1` -- refuses to remove a staging directory that
  overlaps the project source, and supports `-BackupSource`.
- `scripts/build_appimage.sh` / `scripts/build_deb.sh` -- stage in a private
  `mktemp` directory instead of deleting user-visible `AppDir` / `stage_*`
  folders; the AppImage header no longer claims linuxdeploy is downloaded
  by default.
- `scripts/bootstrap_environment.ps1` -- dry-run only prints the pip command
  when Python is actually available, otherwise reports that Python must be
  installed first.

### Added

- `-BackupSource` is now supported by all 14 `scripts/build_*.ps1` helpers,
  not just `build_python.ps1` / `build_dotnet.ps1`.
- `tests/test_docs.py` -- duplicate `##` heading audit, selector x64
  dimension checks, all-build-script `-BackupSource` wiring checks,
  `build_qt.ps1` staging guard, and bootstrap dry-run consistency
  (623 checks).
- `tests/smoke_windows.ps1` -- checks every build helper exposes
  `-BackupSource` and that `build_qt.ps1` protects source staging (86 / 86).

### Verified

- `smoke_windows.ps1` -- 86 / 86
- `test_docs.py` -- 623 checks
- `test_no_bom.py` -- 181 files, 0 BOM / U+FEFF
- media pipeline -- 42 / 42; arch awareness -- 16 / 16
- selector self-test -- 8 / 8 canonical cases + arch-weight assertions
  (24 x 29)
- ruff check, ruff format --check, mypy scripts/ -- all green

## 2026-08-08 (round 24) -- Lint version pinning, CI cache, cleanup

### Changed

- `tests/run_lint.ps1` -- `Ensure-Tool` now reads the exact version from
  `requirements-dev.txt` and compares it with `pip show` output instead
  of only checking that the module imports. Check-only mode reports a
  version mismatch; `-InstallDeps` installs the pinned version.
- `.github/workflows/ci.yml` -- the lint job now enables the
  `setup-python` pip cache, matching the Windows smoke job.
- `tests/test_docs.py` -- verifies the pre-commit ruff/mypy revisions
  stay in sync with `requirements-dev.txt` (571 checks).

### Housekeeping

- Removed the empty stray `app/` directory from the skill root.

### Verified

- `smoke_windows.ps1` -- 84 / 84
- `test_docs.py` -- 571 checks
- `test_no_bom.py` -- 181 files, 0 BOM / U+FEFF
- media pipeline -- 42 / 42; arch awareness -- 16 / 16
- selector self-test -- 8 / 8; VK table -- 119 keys / 10 templates
- ruff check, ruff format --check, mypy scripts/ -- all green

## 2026-08-08 (round 23) -- Toolchain dry-run safety, dev deps, doc sync

### Fixed

- `scripts/bootstrap_environment.ps1` -- `-DryRun` now always wins over
  `-Install`. Previously `-DryRun -Install` executed winget/pip installs
  and then printed "no changes were made"; dry-run now skips every
  install action and prints the pip command it would run.
- `SKILL.md` -- SendInput / window-enum template counts no longer double
  count Java; Step 1 Category C no longer lists service/driver delivery
  as in scope while "Out of scope" forbids it.
- `scripts/select_framework.py` -- self-test case lines use `[OK]`
  consistently instead of `[OK  ]`.

### Added

- `requirements-dev.txt` -- shared pin file for `ruff==0.6.9`,
  `mypy==1.13.0`, and `types-requests`. CI and `tests/run_lint.ps1` now
  consume the same file, and `run_lint.ps1` checks `types-requests`
  alongside ruff/mypy.
- `tests/smoke_windows.ps1` -- regression test proving
  `bootstrap_environment.ps1 -DryRun -Install` never runs an install,
  plus a doc-count sync check that fails when README/SKILL smoke counts
  drift from the real total.
- `tests/test_docs.py` -- Windows smoke count checks now compare
  README/SKILL dynamically instead of hard-coding `83`, and verify
  `requirements-dev.txt` is referenced by CI, run_lint, and README.

### Verified

- `smoke_windows.ps1` -- 84 / 84
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 570 checks
- `test_no_bom.py` -- 181 files, 0 BOM / U+FEFF
- media pipeline -- 42 / 42
- selector self-test -- 8 / 8; VK table -- 119 keys / 10 templates
- ruff check, ruff format --check, mypy scripts/ -- all green

## 2026-08-08 (round 22) -- API manifest, fetch metadata, live task events

### Added

- `scripts/api_analyzer.py` -- deep API manifest: endpoint scoring, auth
  header names (redacted by default), candidate pagination config, list data
  paths inside JSON responses, and summary counts.
- `api_client.ApiFetchResult` now carries HTTP status, response headers, and
  request duration; `MediaSession.request_json_with_meta()` returns
  `(data, status, headers)`.
- `media_pipeline_service.py` records per-task progress events and exposes
  `GET /tasks/<id>/progress` and `GET /tasks/<id>/events?after=N` for
  real-time desktop UI polling.
- `data_processor.py` adds a `join` step for left/inner joins against
  another JSON / JSONL / CSV file.
- `web_data_pipeline.py` can write an API manifest (`api.manifest_output`)
  and auto-applies inferred pagination (`api.auto_pagination`, default true).

### Verified

- `smoke_windows.ps1` -- 83 / 83
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 565 checks
- `test_no_bom.py` -- 180 files, 0 BOM / U+FEFF
- media pipeline -- 42 / 42

## 2026-08-08 (round 21) -- Pagination, cookies, richer data rules, live progress

### Added

- `api_client.py` now supports automatic pagination (`page` / `offset` /
  `cursor`) driven by `items_path`, `total_path`, `has_more_path`, and
  `next_path`; fetch results report the actual page count.
- `ApiClient` accepts Playwright-style cookies so browser-login sessions are
  carried into API fetching; `web_data_pipeline` copies browser cookies
  automatically.
- `data_processor.py` adds `drop`, `default`, `convert`, `map`, and
  `replace` operations for common field cleanup and derivation.
- `web_data_pipeline.py` accepts an optional progress callback and reports
  collect / discover / fetch / process / save / done stages.
- `media_pipeline_service.py` forwards webdata task progress into the SQLite
  queue progress field for live desktop UI updates.
- `OcrCaptchaSolver` preprocesses image CAPTCHAs (grayscale, threshold,
  resize) before OCR when Pillow is available.

### Verified

- `smoke_windows.ps1` -- 82 / 82
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 560 checks
- `test_no_bom.py` -- 179 files, 0 BOM / U+FEFF
- media pipeline -- 39 / 39

## 2026-08-08 (round 20) -- Web data pipeline

### Added

- `scripts/api_client.py` -- converts page/network captures into replayable
  API specs and fetches JSON through `MediaSession` with rate limits and
  retries; includes `build_api_specs`, `ApiClient`, and a local self-test.
- `scripts/data_processor.py` -- declarative processing engine with
  select / rename / filter / sort / dedupe / flatten / limit / aggregate
  steps and JSON / JSONL / CSV I/O.
- `scripts/web_data_pipeline.py` -- one-config end-to-end pipeline for
  fingerprint browser + auto CAPTCHA + page/API analysis + API fetching +
  data processing.
- `references/web_data_pipeline_playbook.md` -- full workflow, config
  schema, CAPTCHA modes, API replay, processing operations, UI sidecar
  integration, and compliance checklist.
- `scripts/media_pipeline_service.py` now accepts `kind: "webdata"` tasks
  so desktop UIs can run the whole pipeline through the sidecar.

### Enhanced

- `scripts/captcha_solver.py` -- local OCR adapter (`OcrCaptchaSolver`) and
  OCR-first automatic solving with third-party / manual fallback; CLI
  self-test.
- `scripts/browser_session.py` -- network entries now keep request POST
  bodies and content types; Playwright storage state can be saved/restored;
  `BrowserSession` accepts a `storage_state` profile path.
- `scripts/media_session.py` -- `request_json()` for arbitrary methods with
  JSON or raw bodies.
- `scripts/media_dependencies.py` -- checks/installs Pillow and pytesseract
  and reports system `tesseract` availability as the `ocr` status key.

### Verified

- `smoke_windows.ps1` -- 82 / 82
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 560 checks
- `test_no_bom.py` -- 179 files, 0 BOM / U+FEFF
- media pipeline -- 36 / 36; selector self-test -- 8 / 8; VK table --
  119 keys / 10 templates

## 2026-08-08 (round 19) -- Slim SKILL.md entry point

### Changed

- `SKILL.md` reduced from 40 KB / 723 lines to 21 KB / 301 lines. The
  workflow, scope gates, UI-01..UI-18, step rules, references, templates,
  examples, and tests remain in the entry point.
- Quick decision tree, threading bridge table, and resource embedding
  table moved to `references/framework_matrix.md`.
- Distribution-first override and the full architecture support matrix
  moved to `references/distribution_playbook.md`.
- `tests/test_docs.py` now excludes utility sections from the
  framework-matrix heading count so the 24 framework sections stay
  structurally verified.
- README / CONTRIBUTING document the "SKILL.md stays slim; details live
  in references" convention.
- `tests/test_docs.py` now fails if `SKILL.md` grows above 25 KB, keeping
  the entry point context-light.
- Fixed stale "matrix in SKILL.md" wording in
  `references/framework_matrix.md`, `references/framework_selection_engine.md`,
  `INDEX.md`, and `CONTRIBUTING.md`.

### Verified

- `smoke_windows.ps1` -- 77 / 77
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 530 checks
- `test_no_bom.py` -- 173 files, 0 BOM / U+FEFF
- media pipeline -- 15 / 15; selector self-test -- 8 / 8; VK table --
  119 keys / 10 templates

## 2026-08-08 (round 18) -- Media path hardening and CI doc drift

### Added

- `media_downloader.safe_output_name` -- shared sanitizer for URL-derived
  filenames; `media_pipeline_service._filename_from_url` and
  `hls_downloader.download_hls` now reject `..`, path separators, control
  characters, Windows-reserved names, and trailing dots/spaces.
- `media_dependencies._zip_member_is_safe` -- refuses absolute, drive,
  and `..` zip entries before extracting the portable ffmpeg archive.
- Media sidecar returns 400 for non-object JSON, invalid priority /
  max_attempts / resume_token / payload, and malformed Content-Length;
  request bodies over 16 MiB return 413.
- Bearer token checks now use constant-time `hmac.compare_digest`.
- Regression tests for filename sanitization, zip safety, and bad API
  payloads; doc checks guard INDEX/README CI wording.

### Fixed

- INDEX.md and smoke_linux.sh still referenced `ubuntu-latest` while CI
  is pinned to `ubuntu-22.04`.
- README CI table omitted `--check` from the `ruff format` job.
- CI header comment said `ubuntu-latest` for the Linux job.

### Verified

- `smoke_windows.ps1` -- 77 / 77
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 529 checks
- `test_no_bom.py` -- 173 files, 0 BOM / U+FEFF
- media pipeline -- 15 / 15; selector self-test -- 8 / 8; VK table --
  119 keys / 10 templates

## 2026-08-08 (round 17) -- Shared Python resolver, Linux PyInstaller gate, docs drift

### Added

- `scripts/find_python.ps1` -- single shared Python discovery used by
  `build_python.ps1`, `bootstrap_environment.ps1`,
  `setup_media_dependencies.ps1`, `tests/run_lint.ps1`, and
  `tests/smoke_windows.ps1`. Order: `-PythonExe` / `CODEX_PYTHON` /
  `PYTHON` / Codex runtime under `$HOME\.cache` / PATH.
- `smoke_windows.ps1` -- regression tests for the shared resolver,
  including `PYTHON` env-var preference.

### Fixed

- `bootstrap_environment.ps1`, `setup_media_dependencies.ps1`,
  `tests/run_lint.ps1`, and `tests/smoke_windows.ps1` now honor the
  `PYTHON` environment variable and no longer embed a hardcoded
  `C:\Users\xc` path (Codex runtime lookup uses `$HOME\.cache`).
- `build_linux.ps1` -- `-Tool python` now invokes PyInstaller through
  the resolved `python3` module and only installs missing PyInstaller
  when `-Install` is passed.
- `build_electron.ps1` -- `-Target` is now `[ValidateSet(...)]` so a
  typo fails fast instead of reaching electron-builder.

### Changed

- README / INDEX / SKILL clarified template file counts (12 files each
  for the SendInput and window-enum sets incl. Java) and made
  `media_dependencies.py` default-check-only explicit.
- Smoke count updated to 77 / 77.

### Verified

- `smoke_windows.ps1` -- 77 / 77
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 527 checks
- `test_no_bom.py` -- 173 files, 0 BOM / U+FEFF
- media pipeline -- 11 / 11; selector self-test -- 8 / 8; VK table --
  119 keys / 10 templates

## 2026-08-08 (round 16) -- BOM regression, examples coverage, check-only lint

### Added

- `tests/test_no_bom.py` -- scans every text file for UTF-8 BOM / U+FEFF
  and is wired into all three smoke suites.
- Smoke tests now AST-parse every `.py` under `examples/` on Windows,
  macOS, and Linux.
- `smoke_windows.ps1` -- backup test now proves `mybuild` survives while
  `build` is excluded (exact-segment semantics).

### Fixed

- `run_lint.ps1` -- default is check-only: missing ruff / mypy now prints
  the install command and exits non-zero unless `-InstallDeps` is passed;
  PowerShell detection falls back from `pwsh` to `powershell`.
- `bootstrap_environment.ps1` -- successfully installed toolchains are
  removed from the missing list, and a failed pip install now exits
  non-zero instead of reporting success.
- `backup_source.ps1` -- exclude matching is exact path-segment based
  (`mybuild` no longer matches `build`), and a custom output directory
  under the source root is skipped automatically.
- `test_arch_awareness.ps1` -- host architecture detection falls back to
  `PROCESSOR_ARCHITECTURE` when `RuntimeInformation` is unavailable.

### Changed

- CI docs now consistently say `ubuntu-22.04` (README, tests README,
  SKILL, CONTRIBUTING).
- CONTRIBUTING fixed the stale 13 / 14 build count, `veloappck` typo,
  pre-commit hook description, and CI job count.
- Smoke count updated to 74 / 74.

### Verified

- `smoke_windows.ps1` -- 74 / 74
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 513 checks
- `test_no_bom.py` -- 172 files, 0 BOM / U+FEFF
- media pipeline -- 11 / 11; selector self-test -- 8 / 8; VK table --
  119 keys / 10 templates

## 2026-08-08 (round 15) -- Opt-in toolchain installs and packaging fixes

### Changed

- `build_python.ps1`, `build_tauri.ps1`, `build_electron.ps1`,
  `build_linux.ps1`, `build_macos.ps1`, `build_go_fyne.ps1`, and
  `build_go_wails.ps1` no longer auto-install missing CLIs. Each now
  takes `-Install`; without it, the script prints the exact install
  command and exits non-zero.
- `build_appimage.sh` now supports `aarch64` output and only downloads
  linuxdeploy with `--download`; the fallback rename no longer risks
  moving the linuxdeploy helper into the release artifact.
- `build_deb.sh` accepts an optional `amd64|arm64` package architecture.

### Fixed

- `auto_update_squirrel.ps1` now copies the main EXE into the release
  stage instead of moving (and losing) the original build artifact.
- `auto_update_winsparkle.cpp` converts the app name / version to narrow
  UTF-8 before passing them to WinSparkle, fixing a wide-string compile
  error.
- `build_go_wails.ps1` discovers the built EXE / NSIS installer instead
  of reporting a hardcoded `myapp` path, and `-Clean` also clears
  `build/darwin` as documented.
- `build_dotnet.ps1` reads the project's TFM for the publish-path
  fallback instead of hardcoding `net8.0`.

### Added

- `select_framework.py --self-test` validates the 24 x 27 scoring table,
  display/rationale/language maps, and `toolchain_map.json` coverage.
- `tests/test_docs.py` guards the new invariants: `-Install` gating,
  AppImage/deb architecture support, Squirrel copy semantics, and
  WinSparkle narrow-string API usage.
- `tests/test_media_pipeline.py` now verifies unauthenticated POSTs are
  rejected by the token-protected sidecar.

## 2026-08-08 (round 14) -- Framework selector/matrix alignment

### Fixed

- `scripts/select_framework.py` -- added the missing `walk` framework so
  the selector now scores all 24 canonical frameworks advertised by the
  matrix instead of 23.
- `scripts/toolchain_map.json` -- added `walk` to the Go toolchain mapping.
- `SKILL.md` -- framework matrix now includes `C# / WinForms` and
  `Python / GTK`, matching the selector and deep-dive matrix.
- `references/framework_matrix.md` -- added the `C# / WinForms` deep-dive
  section and corrected the 24-framework count.
- `references/framework_matrix.md` -- removed duplicated quick-verdict
  bullets for Rust/Go teams.
- `templates/gui_framework_decision_tree.md` -- fixed the stale
  `CommunityToolkit.Wpfdataload` typo and clarified the Avalonia
  anti-pattern for Windows-only apps.
- `scripts/build_dotnet.ps1` -- accepts `-OutputDir` and no longer assumes
  the project targets `net8.0` when reporting the publish output.

### Added

- `tests/test_docs.py` -- structural checks that the selector, SKILL
  matrix, and framework matrix all agree on the 24-framework set, plus
  duplicate-bullet and toolkit-typo guards.

## 2026-08-08 (round 13) -- Client endpoint parity and full PowerShell parse

### Added

- `clients/` -- every wrapper now exposes dependency status, dependency
  progress, and dependency install in addition to enqueue / task lookup:
  C#, Go, Rust, Kotlin, Swift, Java, C++ (TypeScript already had them).
- `tests/smoke_windows.ps1` -- parses every `.ps1` in the skill, including
  `examples/msix-packaging/build_msix.ps1`,
  `examples/winui3-threading/build_winui3.ps1`, and the test scripts.
- `tests/smoke_macos.sh` / `tests/smoke_linux.sh` -- parse every `.ps1`
  when PowerShell is installed instead of a small hand-picked subset.
- `tests/run_lint.ps1` -- only installs ruff / mypy when they are missing,
  and `ruff format --check` now covers scripts, tests, and examples.
- README layout and SKILL deep references now list all 11 reference docs;
  INDEX now covers the full canonical framework list and points macOS /
  Linux accessibility to `references/accessibility_cross_platform.md`.
- `tests/test_docs.py` -- checks reference completeness, INDEX framework
  rows, client endpoint parity, expanded CI format scope, and all-.ps1
  parse coverage.

### Fixed

- `.github/workflows/ci.yml` -- stale "Three jobs" comment now says four
  jobs, and the lint job checks formatting on tests / examples too.
- `clients/README.md` -- capability claim now matches the wrappers.
- `tests/test_docs.py` -- skips generated cache directories (`.mypy_cache`,
  `.ruff_cache`, `__pycache__`, build output) during the line-ending audit.
- `scripts/select_framework.py` -- strips a UTF-8 BOM before parsing the
  brief, so Windows editors that write BOM JSON no longer silently fall
  back to an empty requirements object.

## 2026-08-08 (round 12) -- Sidecar auth and API hardening

### Added

- `scripts/media_pipeline_service.py` -- optional `--token` Bearer auth
  for every endpoint except `/health`.
- `clients/` -- all 8 wrappers accept an optional token and send
  `Authorization: Bearer <token>`.
- `templates/security_checklist.md` -- local sidecar binding and token
  requirement.
- `templates/release_checklist.md` -- clean-machine one-click media
  runtime install verification.

## 2026-08-08 (round 11) -- Second audit pass

### Fixed

- `scripts/select_framework.py` -- the flat YAML loader now parses nested
  inline arrays correctly (`target_os: [["windows", "x64"]]`), and
  `--self-test` covers the YAML path.
- `references/win32_recipes.md` -- removed the duplicated R13 section and
  fixed an apostrophe typo.
- `references/framework_matrix.md` -- added the missing Python GTK section,
  matching the 23-framework count advertised by the selector.
- Repo line endings now match `.editorconfig`: `.ps1` / `.bat` / `.cmd` use
  CRLF; all other text files use LF.

### Added

- `tests/test_docs.py` -- line-ending audit for every text file, plus
  duplicate-heading checks for `win32_recipes.md` and a Python GTK
  presence check in the framework matrix.
- `templates/requirements_brief.md` / `references/framework_selection_engine.md`
  -- documented the supported flat YAML shape and the inline-list
  requirement.

## 2026-08-08 (round 10) -- Audit fixes, source backup restore, stricter types

### Fixed

- `scripts/build_linux.ps1` -- Go builds no longer pass the Windows-only
  `-H windowsgui` linker flag.
- `scripts/build_go_fyne.ps1` -- fixed broken EXE-name derivation when
  `-Strip` / `-NoConsole` rebuild the binary.
- `scripts/build_go_wails.ps1` -- corrected the `-Nsis` comment to match
  the actual switch default.
- `scripts/build_qt.ps1` -- only passes `--qmldir` to windeployqt when the
  project actually contains a `qml` directory.
- `scripts/media_downloader.py` -- servers without `Content-Length` now
  fall back to a single-stream download instead of passing `None` into
  the chunk map builder.
- `scripts/media_dependencies.py` -- dependency status now returns real
  booleans for `ffmpeg` / `ffprobe`.
- `scripts/hls_downloader.py` -- AES IV parsing also accepts an uppercase
  `0X` prefix.
- `scripts/media_parser.py`, `scripts/task_queue.py`,
  `scripts/hls_downloader.py`, `scripts/media_pipeline_service.py` --
  fixed all remaining mypy errors (13 findings) and made mypy clean.
- `SKILL.md` -- Step 4.2 now documents press and release as two separate
  `SendInput` calls, matching the smoke-test regression guard.
- `SKILL.md` -- corrected the mobile skill name in the out-of-scope table.

### Added

- Restored source preservation integration: `-BackupSource` on
  `scripts/build_python.ps1` and `scripts/build_dotnet.ps1` creates a
  timestamped source zip before the build starts.
- `scripts/backup_source.ps1` now excludes the `source_backup` folder so
  repeated backups never archive previous backups.
- `tests/smoke_windows.ps1` -- backup-source smoke test and platform-flag
  regression checks for `build_linux.ps1` / `build_go_fyne.ps1`.
- `tests/smoke_linux.sh` / `tests/smoke_macos.sh` -- run `test_docs.py`,
  `test_media_pipeline.py`, and `test_arch_awareness.ps1` when Python /
  PowerShell are available.
- `tests/test_docs.py` -- structural checks for source-preservation docs,
  `-BackupSource` wiring, README layout, and the SendInput batching rule.

## 2026-08-08 (round 9) -- All-language sidecar + runtime installer

### Added

- `scripts/media_dependencies.py` -- check / install Playwright,
  pycryptodome, Chromium, and portable ffmpeg; `--install` is explicit.
- `scripts/setup_media_dependencies.ps1` -- PowerShell wrapper with
  check-only default and `-Install`.
- `scripts/media_pipeline_service.py` -- local HTTP sidecar with task
  queue, workers, crawl / download / HLS / transcode handlers,
  dependency install endpoint, and JSON API.
- `references/media_pipeline_clients.md` -- C# / JS / TS / Go / Rust /
  Kotlin / Swift / Java / C++ client snippets for the sidecar.
- `clients/` -- ready-made wrapper templates in the same 8 languages.
- `scripts/media_pipeline_service.py` -- `/deps/progress` endpoint,
  task enqueue now accepts `max_attempts` / `resume_token`, and
  download / HLS tasks accept proxy, headers, concurrency, chunk size,
  and resume settings via payload.
- `scripts/task_queue.py` -- `count()` now supports the same search
  filter as `list_tasks()`, so list totals are correct when searching.
- `scripts/media_dependencies.py` / `setup_media_dependencies.ps1` --
  ffmpeg download URL can be overridden with `--ffmpeg-url` / `-FfmpegUrl`.
- `scripts/media_downloader.py` -- per-chunk retry with exponential
  backoff via `chunk_retries`.
- `scripts/hls_downloader.py` -- `quality` selects a zero-based master
  variant instead of always taking the highest bandwidth.
- `scripts/media_pipeline_service.py` -- service startup closes the SQLite
  queue if the HTTP server cannot bind.
- `tests/test_media_pipeline.py` -- dependency status, HTTP sidecar, and
  crawl handler tests; media pipeline suite is now 11/11.

### Fixed

- `scripts/task_queue.py` -- retry tasks support `run_after` delayed
  scheduling and existing databases migrate the new column.
- `scripts/media_dependencies.py` -- Chromium detection now covers
  Windows, macOS, and Linux Playwright cache paths.
- `scripts/captcha_solver.py` -- solver HTTP errors now surface as
  `CaptchaError` with the server response instead of a raw urllib error.

## 2026-08-08 (round 8) -- Media acquisition pipeline

### Added

- `references/media_acquisition_playbook.md` -- architecture, SQLite task
  queue design, crawl / HLS / download / transcode / publish pipeline,
  CAPTCHA and anti-bot handling, crash recovery, and compliance notes.
- `scripts/media_session.py` -- cookies, proxy, retry HTTP session.
- `scripts/media_parser.py` -- HTML media extraction + m3u8 parsing.
- `scripts/media_downloader.py` -- Range chunked download, resume,
  concurrency, checkpoint files, and progress callbacks.
- `scripts/hls_downloader.py` -- HLS segments, AES-128 keys, ffmpeg merge.
- `scripts/captcha_solver.py` -- third-party solver + manual fallback.
- `scripts/browser_session.py` -- Playwright login / cookies / fingerprint.
- `scripts/task_queue.py` -- SQLite persistent queue with atomic claims,
  dedupe, retry, progress, and stale-running recovery.
- `scripts/ffmpeg_transcoder.py` -- ffmpeg / ffprobe progress wrapper.
- `scripts/platform_publisher.py` -- publish adapter interface + retry.
- `tests/test_media_pipeline.py` -- 5 local tests for queue persistence,
  parser, manual CAPTCHA, chunked download, and HLS download.
- `tests/smoke_windows.ps1` -- runs the media pipeline test suite.

## 2026-08-08 (round 7) -- Heavy desktop UI requirement

### Added

- UI-18 -- heavy desktop UI style: native window / menu / toolbar /
  status bar / data grid / right-click menu / keyboard operations;
  web-styled layouts, hero pages, floating rounded cards, and infinite
  scroll are prohibited.
- `references/ui_hard_requirements.md` -- UI-18 rules and acceptance
  checklist item; all current docs now use UI-01..UI-18.

## 2026-08-08 (round 6) -- UI hard requirements

### Added

- `SKILL.md` -- `界面硬性要求（UI hard requirements）` section with the
  mandatory UI-01..UI-17 checklist.
- `references/ui_hard_requirements.md` -- canonical UI rules, Codex-like
  default palette, semantic colors, theme library URLs, refresh
  contract, settings persistence, log center, auto-refresh, and
  acceptance checklist.
- `templates/requirements_checklist.md` -- section 1.3 for recording
  UI-01..UI-17 waivers / acceptance evidence, plus sign-off checkbox.
- README, INDEX, task decomposition T4, Step 6, and release checklist
  updates.
- `tests/test_docs.py` -- structural checks for UI-01..UI-17 consistency
  across SKILL.md, reference, templates, README, and INDEX.

## 2026-08-07 (round 5) -- Environment bootstrap

### Added

- `scripts/bootstrap_environment.ps1` -- auto-selects the framework via
  `select_framework.py --json`, or accepts `-Framework`, then detects and
  installs the matching SDK / toolchain with winget / pip.
- `scripts/toolchain_map.json` -- framework-to-toolchain mapping for all
  canonical frameworks.
- `tests/fixtures/sample_brief.json` plus smoke coverage for the bootstrap
  dry run and JSON validity.
- SKILL.md Step 2.5, README layout, and INDEX environment setup section.

## 2026-08-07 (round 4) -- Full optimization pass

### Added

- Randomized 50-150 ms jitter by default in every `sendinput_*` language
  template; pass an explicit positive `jitterMs` to force a fixed delay.
- Canonical `scripts/vk_table.json` reference comments in all language
  templates.
- `check_vk_tables.py` now validates all 10 Windows language templates
  against the canonical JSON, not just Python.
- `tests/fixtures/csharp-smoke/` and an optional `dotnet build` check in
  `smoke_windows.ps1`.

### Fixed

- `scripts/sendinput_macos.py` -- missing `c_uint16` import.
- `scripts/window_enum_macos.py` -- moved missing `c_uint32` / `c_void_p`
  imports to the top.
- Added missing special VK keys (`select`, `print`, `execute`,
  `snapshot`, `help`, numpad extras) to C, C#, Java, Rust, Go, Dart,
  Node, Kotlin, and Swift templates.
- Full `ruff check` cleanup (128 findings) and `mypy scripts/` cleanup
  (10 findings); both now pass locally.

## 2026-08-07 (round 3) -- Optimization pass

### Added

- `scripts/select_framework.py --self-test` now runs inside
  `tests/smoke_windows.ps1`.
- `tests/test_docs.py` -- structural doc audit for frontmatter, duplicate
  sections, relative references, and advertised file counts.
- `scripts/vk_table.json` + `scripts/check_vk_tables.py` -- canonical key
  table with an automated Python reference check.
- Mouse helpers (`move_mouse`, `click`, `scroll`) in
  `scripts/sendinput_python.py`.
- Flutter, Slint, egui, and TornadoFX entries in `select_framework.py`,
  bringing the selector to 23 canonical frameworks.
- `scripts/sign_windows.ps1` and `scripts/sign_macos.sh` code-signing
  helpers.

### Changed

- `tests/smoke_windows.ps1` and `tests/run_lint.ps1` now honor
  `CODEX_PYTHON` before falling back to the bundled Codex runtime.
- Docs now distinguish randomized Python jitter from fixed jitter in the
  other language templates.
- Removed generated Python `__pycache__` cache files from `scripts/`.

### Fixed

- `examples/game-automation/app/app.py` -- corrected `SKILL_ROOT` parents
  depth so the example can actually import `scripts/`.

## 2026-08-07 (round 2) -- Full audit fixes

### Fixed

- Unified key-hold, foreground-check, and single-side modifier semantics
  across all 10 Windows `sendinput_*` language templates.
- `scripts/sendinput_win32.c` -- removed undefined `holdMs` reference in
  `pressCombo()`.
- `scripts/SendInput.java` -- removed undefined `pair` reference in
  `pressCombo()`.
- `scripts/sendinput_go.go` -- `pressOne()` now passes `nInputs=1` instead
  of `2`.
- Replaced remaining UTF-8 em dashes in PowerShell build scripts.
- Added a source-level regression check to `smoke_windows.ps1` that rejects
  down/up events batched into a single `SendInput` call.
- Aligned CI job counts and lint commands in `tests/README.md` and
  `README.md`.

## 2026-08-07 -- Review fixes

### Fixed

- `SKILL.md` frontmatter and tail corruption; restored the framework
  selection engine section and removed duplicated test lists.
- `scripts/sendinput_python.py` -- real key hold semantics, foreground
  failure raises instead of sending to the wrong window, randomized
  jitter range, and single-side modifier aliases.
- `scripts/sendinput_macos.py` / `sendinput_linux.py` -- randomized jitter
  range and keyboard-only docs (mouse is not implemented).
- `scripts/window_enum_python.py` -- `HWND` / `LPARAM` callback types and
  explicit argtypes for 64-bit correctness.
- `examples/game-automation/` -- enumeration and key sends now run on
  `TkBackgroundTask`; unused imports removed.
- `tests/test_arch_awareness.ps1` -- now covers `build_dotnet_nativeaot.ps1`
  and Electron's `ia32` architecture value.
- Aligned framework/language/example counts across `SKILL.md`, `README.md`,
  `INDEX.md`, `examples/`, and `tests/`.
- Removed UTF-8 BOM from 58 files.

## 2026-08-06 (round 2) -- Bug fixes + structural completeness

### Fixed -- Round 1 (4 real bugs that earlier "perfect" claim missed)

- `scripts/auto_update_winsparkle.cpp` -- WinSparkle takes **narrow** URL
  strings. Replaced `feedUrl.c_str()` (wide) with `to_narrow(feedUrl)`
  using `WideCharToMultiByte(CP_UTF8, ...)`.
- `scripts/window_enum_node.ts` -- Worker branch referenced `shimFuncs!`
  without ever loading the shim in the worker context. Added the same
  shim-load logic inside the worker before calling `enum`.
- `scripts/sendinput_kotlin.kt` -- `cbSize` was computed by
  `Input::class.java.superclass.let { 40 }` (coincidentally right on x64
  but semantically wrong). Replaced with `Native.getNativeSize(Input::class.java)`.
- `scripts/window_enum_swift.swift` -- Cancellation flag was non-atomic
  `NSMutableData.isEmpty`, callback ran on a worker thread. Replaced with
  a `Holder` class exposing `var snapshot: Bool` protected by `NSLock`,
  and added `resultsLock` for the `results` array.

### Added -- Round 2 (structural completeness)

- SKILL.md -- new "When NOT to use this skill" section with 7 explicit
  anti-triggers (CLI / web / mobile / single-purpose script / framework
  comparison / console subsystem / framework locked-in).
- `examples/` -- 5 minimal runnable projects:
  - `wpf-threading/`  (C# WPF, links `scripts/threading_wpf.cs`)
  - `tkinter-threading/`  (Python, imports `scripts/threading_tkinter.py`)
  - `pyside6-threading/`  (Python, imports `scripts/threading_pyside6.py`)
  - `tauri-threading/`  (Rust + Web, real `src-tauri/` + `src/`)
  - `game-automation/`  (TLBB-style: window + SendInput + threading)
- `.gitignore` -- PyInstaller / Cargo / .NET / Node / IDE artefacts.
- `LICENSE` -- MIT.
- `pyproject.toml` -- ruff + mypy config; selectable rules
  E/W/F/I/B/UP/SIM; per-file ignores for the dynamic-import parts.

## 2026-08-06 (round 1) -- Coverage completeness pass

Filled every gap called out in the skill self-audit.

### Added -- build scripts
- `scripts/build_qt.ps1` -- C++/Qt 6 + windeployqt + cpack NSIS/WIX.
- `scripts/build_electron.ps1` -- electron-builder NSIS / MSI / portable.
- `scripts/build_python.ps1` -- auto-resolves Python from `-PythonExe`,
  `CODEX_PYTHON` / `PYTHON` env vars, Codex primary runtime, or PATH.

### Added -- threading templates
- `scripts/threading_tkinter.py`, `threading_pyside6.py`,
  `threading_tauri.rs`.

### Added -- SendInput / window enumeration
- `scripts/sendinput_swift.swift`, `scripts/sendinput_kotlin.kt`,
  matching `window_enum_*` pair, plus `window_enum_node_shim.cc` and a
  rewritten `window_enum_node.ts`.

### Added -- auto-update implementations
- `scripts/auto_update_velopack.ps1`,
  `scripts/auto_update_squirrel.ps1`,
  `scripts/auto_update_winsparkle.cpp`.

### Added -- templates + tests
- `templates/dpi_manifest.xml`,
  `templates/gui_framework_decision_tree.md`,
  `tests/README.md`,
  `tests/fixtures/{sample.md, sample_config.json, AppxManifest.xml}`.

### Changed
- `SKILL.md` -- description, build-script list, threading line, auto-update
  cross-references, "Templates" + "Deep references" + new "Tests" sections.
- `references/framework_matrix.md` -- removed duplicate
  "Quick verdict by user persona" block at the tail.


## 2026-08-06 (round 3) -- Scope, restricted network, ARM64

### Added
- `SKILL.md` -- explicit **Scope and limits** section with IN-scope (Win 10
  1809+ / Win 11 on `win-x64` / `win-arm64` / `win-x86`) and an Out-of-scope
  table covering iOS / iPadOS, macOS, Linux desktop, Android, web apps,
  browser extensions, CLI / libraries, server / headless, Windows services
  and drivers.
- `SKILL.md` -- architecture support matrix table covering all 11
  build_*.ps1 scripts and which of x64 / arm64 / x86 they support.
- `references/restricted_network_playbook.md` -- vendoring / pinning /
  local mirrors / offline caches for Python, NuGet, npm / yarn / pnpm,
  Cargo, and Qt. Plus the "build on a connected machine, ship the EXE"
  fallback that covers 90% of real recipient situations.
- `tests/test_arch_awareness.ps1` -- structural test that uses the
  PowerShell AST to confirm every `build_*.ps1` declares `-Arch` or `-Rid`
  with a `ValidateSet` that includes `x64` / `arm64` / `x86` (or framework
  equivalents).

### Changed -- all 11 build_*.ps1 scripts
- `build_dotnet.ps1`      -- added `[Alias("Arch")]` to `$Rid`,
                              ValidateSet on `win-x64|win-arm64|win-x86`,
                              NativeAOT x64-only guard.
- `build_tauri.ps1`       -- new `-Arch` mapped to Rust target triple.
- `build_electron.ps1`    -- ValidateSet on `x64|arm64|ia32`.
- `build_qt.ps1`          -- new `-Arch` + `qtArchDir` toolchain prefix.
- `build_python.ps1`      -- new `-Arch`; warns when host arch mismatch.
- `build_go_wails.ps1`    -- new `-Arch` mapped to Wails platform string.
- `build_go_fyne.ps1`     -- new `-Arch` sets `GOARCH` env.
- `build_go_gio.ps1`      -- new `-Arch` sets `GOOS=windows` + `GOARCH`.
- `build_kotlin_compose.ps1` -- new `-Arch` (nativeArch hint).
- `build_swift.ps1`       -- new `-Arch` mapped to Swift `--triple`.
- `build_neutralino.ps1`  -- new `-Arch` (Neutralino is arch-agnostic;
                              runs on whatever WebView2 is installed).

### Index
- `SKILL.md` deep references now include `restricted_network_playbook.md`.
- `README.md` When-NOT section expanded to call out iOS / macOS / Linux
  explicitly; new "Supported architectures" section.
- `SKILL.md` Tests section now references `test_arch_awareness.ps1`.

### Verified
- `tests/test_arch_awareness.ps1` -- 11/11 build scripts pass.
- All 11 `build_*.ps1` parse cleanly with `[System.Management.Automation.Language.Parser]`.
- `SKILL.md` "When NOT to use" + "Out of scope" tables cross-reference
  separate skills (planned, not built) for iOS / macOS / Linux / Android.


## 2026-08-06 (round 4) -- Cross-platform Win + macOS + Linux

Scope change: the skill is now **cross-platform desktop** (Windows + macOS +
Linux). iOS / iPadOS / Android remain out of scope (use the
`mobile-app-dev-ios` skill).

### Added -- macOS primitives
- `scripts/sendinput_macos.py` -- Quartz `CGEventPost` via ctypes; no
  PyObjC dependency; USB HID keysym table.
- `scripts/window_enum_macos.py` -- `CGWindowListCopyWindowInfo` via ctypes;
  3 s EnumWindows-style timeout; EWMH-like session cache.
- `scripts/threading_dispatch.swift` -- `Task.detached` + `@MainActor` callback
  pattern with cooperative cancel.
- `scripts/auto_update_sparkle.swift` -- Sparkle 2.x integration.

### Added -- Linux primitives
- `scripts/sendinput_linux.py` -- X11 `XTestFakeKeyEvent` via ctypes; XK_
  keysym table; covers foreground-only X11 sessions.
- `scripts/window_enum_linux.py` -- X11 `XQueryTree` + EWMH `_NET_CLIENT_LIST`
  via ctypes; no python-xlib dependency.
- `scripts/threading_glib.py` -- GTK / GLib `idle_add` bridge pattern with
  lazy gi import.

### Added -- cross-platform packaging
- `scripts/build_macos.ps1` -- dotnet / cargo (Tauri) / xcodebuild wrapper
  with `-Arch x64|arm64` mapping to Apple target triples and RID.
- `scripts/build_linux.ps1` -- dotnet / cargo / go / python wrapper with
  `-Arch x64|arm64`.
- `scripts/build_dmg.sh` -- macOS DMG packaging with codesign + notarytool
  + stapler + hdiutil.
- `scripts/build_appimage.sh` -- Linux AppImage via linuxdeploy.
- `scripts/build_deb.sh` -- Debian .deb via dpkg-deb + fakeroot.
- `scripts/auto_update_appimage.md` -- AppImageUpdate / zsync flow for Linux
  portable distribution.

### Added -- Tier 1 #4 MSIX example (Windows packaging)
- `examples/msix-packaging/` -- complete WPF + WAP project with
  `Package.appxmanifest`, `build_msix.ps1` (dotnet publish + MakeAppx +
  signtool), and sideload instructions.

### Added -- Tier 1 #5 accessibility (R13 closure)
- `scripts/accessibility_uia.py` -- comtypes-based UI Automation client
  with tree walker + predicate filtering.
- `scripts/accessibility_msaa.py` -- no-deps ctypes MSAA reader.
- `references/win32_recipes.md` R13 -- rewritten with priority order
  (UIA > MSAA > SendInput > memory write) and a "when to pick what" table.

### Changed -- SKILL.md
- Scope section rewritten as 3-OS table (Windows / macOS / Linux) with
  versions, default UI stack, input / window-enum API, code-sign tool.
- Out-of-scope table trimmed to iOS / Android / Web / CLI / Server / drivers.
- Architecture support matrix expanded from 11 to 17 build scripts,
  now a 7-column matrix (Win x64/arm64/x86 + macOS x64/arm64 + Linux x64/arm64).
- Deep references unchanged.

### Changed -- tests
- `tests/test_arch_awareness.ps1` extended from 11 to 13 build scripts;
  covers `build_macos.ps1` and `build_linux.ps1`. All 13 pass.

### Verified
- 13 / 13 `build_*.ps1` parse cleanly + have ValidateSet covering x64 +
  arm64 (and x86 where applicable).
- All Python scripts are syntactically valid (no live Linux/macOS host
  available for runtime testing; the macOS/Linux SendInput and window
  enumeration code follows the same ctypes patterns as the Windows
  version which is runtime-tested).
- `tests/test_arch_awareness.ps1` exits 0 on success.


## 2026-08-07 (round 5) -- CI, INDEX, real smoke tests

### Added
- `INDEX.md` -- topic-based navigation (by use case / OS / framework /
  task) complementing the path-based `SKILL.md`.
- `tests/smoke_windows.ps1` -- 32-check smoke test for Windows. Runs
  PowerShell parse on every `build_*.ps1` + `auto_update_*.ps1`, Python
  imports, fixture validity, arch awareness, and Python AST parse for
  all scripts/*.py. Pass: 32 / 32.
- `tests/smoke_macos.sh` -- macOS smoke: bash syntax for `build_dmg.sh`
  (and others), PowerShell parse via brew pwsh, Python AST + const-table
  for `sendinput_macos.py` (validates `lcmd`, `f5`, etc.) and
  `window_enum_macos.py`, Swift `-parse` if toolchain present.
- `tests/smoke_linux.sh` -- Linux smoke: bash syntax for AppImage + deb
  scripts, PowerShell parse via apt pwsh, Python AST + const-table for
  `sendinput_linux.py` (validates `control_l`, `super_l`, etc.),
  `window_enum_linux.py`, `threading_glib.py`.
- `.github/workflows/ci.yml` -- three-job matrix on
  `windows-latest` / `macos-latest` / `ubuntu-latest`. Each job
  installs Python 3.12 + PowerShell, runs the matching smoke test,
  uploads logs on failure (7-day retention).

### Changed
- `tests/README.md` rewritten to document the new smoke tests, the
  arch-awareness test, and the CI matrix.
- `tests/test_arch_awareness.ps1` already covered `build_macos.ps1`
  and `build_linux.ps1`; no change.
- `SKILL.md` "Deep references" now lists `INDEX.md`.
- `SKILL.md` "Tests" section expanded to list all smoke scripts and
  the CI workflow.
- `README.md` adds "CI / continuous testing" + "Index" sections.

### Verified locally
- `pwsh tests/smoke_windows.ps1` -- 32 / 32 pass on Windows.
- `tests/test_arch_awareness.ps1` -- 13 / 13 pass.
- YAML parse -- `.github/workflows/ci.yml` has all required keys.

### Out of scope
- Live runtime testing of `sendinput_macos.py` /
  `window_enum_macos.py` / `sendinput_linux.py` / `window_enum_linux.py`
  still requires a GUI session on those hosts. Smoke tests verify AST
  + const-table + script import sanity, not actual Quartz / X11 calls.


## 2026-08-07 (round 6) -- Bug fixes, lint, contributor docs

### Fixed -- 5 real bugs

- `scripts/build_dmg.sh` -- DMG output path was `$(dirname "$WORKDIR")`
  (parent of the .app's directory) instead of `$WORKDIR` (same directory
  as the .app). DMGs now land next to the .app bundle, not two levels up.
- `scripts/window_enum_macos.py` and `window_enum_linux.py` -- docstring
  now explicitly states that `thread.join(timeout=3)` is a **soft**
  timeout: Quartz / Xlib are synchronous C, the Python interpreter
  cannot preempt mid-walk. The 3 s value detaches and returns whatever
  was accumulated. Hard timeout requires multiprocessing.
- `scripts/sendinput_macos.py` -- `c_bool` was forward-referenced and
  re-bound at the bottom of the file. Moved to the top `from ctypes
  import c_bool, ...` line; removed the redundant re-binding. Also
  stripped UTF-8 BOM that had been re-added by Set-Content.
- `.github/workflows/ci.yml` -- `test-linux` ran on `ubuntu-latest`
  (24.04 as of 2026) but the apt URL was hardcoded to
  `ubuntu/22.04/`. Pinned to `runs-on: ubuntu-22.04` with a comment
  explaining the rationale.
- `scripts/build_python.ps1` -- host-arch detection used
  `[System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture`
  which is .NET 6+ only. Windows PowerShell 5.1 lacks the type and
  would throw. Wrapped in try/catch with a fallback to
  `$env:PROCESSOR_ARCHITECTURE`.

### Added

- `CONTRIBUTING.md` -- how-to guide for adding a new SendInput language,
  a new window-enumeration language, a new framework wrapper, a new
  packaging format, a new auto-update channel, or a new example.
  Documents pre-commit hooks, CI, and coding style.
- `tests/run_lint.ps1` -- local one-shot: ruff check + ruff format
  --check + mypy + smoke_windows.ps1 + test_arch_awareness.ps1.
  Equivalent on macOS / Linux is documented inline.
- `.pre-commit-config.yaml` -- ruff + ruff-format + mypy + PowerShell
  parse hook via local system pwsh + standard pre-commit-hooks.
- `.editorconfig` -- LF line endings globally except `.ps1`/`.bat`/`.cmd`
  (CRLF for Windows-native tooling), 4-space indent except YAML/JSON/TOML
  (2 spaces) and Go (tabs).

### Changed

- `.github/workflows/ci.yml` -- new `lint` job on `ubuntu-22.04` runs
  `ruff check` + `ruff format --check` + `mypy scripts/` before the
  three OS jobs. mypy is non-blocking (matches local `run_lint.ps1`).
- `tests/test_arch_awareness.ps1` -- added `auto_update_*.ps1 parse`
  section (2 scripts: `auto_update_squirrel.ps1`,
  `auto_update_velopack.ps1`). Count went from 13 / 13 to 15 / 15.

### Verified

- `pwsh tests/smoke_windows.ps1` -- 32 / 32 pass.
- `pwsh tests/test_arch_awareness.ps1` -- 15 / 15 pass.
- `pwsh tests/run_lint.ps1 -SkipSmoke` -- would install ruff + mypy
  (skipped here to avoid network); smoke tests pass independently.
- All five bug fixes pass their respective verification checks.

## Earlier history

Initial 8-step workflow + `references/` + `scripts/` (SendInput / window
enumeration / threading / build) + `templates/` (requirements + task card).
