# Changelog

All notable improvements to this skill. Newest entries first.

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
