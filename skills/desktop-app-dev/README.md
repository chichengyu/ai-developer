# desktop-app-dev

Consultative Codex skill for shipping native cross-platform desktop GUI
applications.

## Entry point

`SKILL.md` -- read this first. It defines the 8-step workflow
(requirements -> classify -> pick framework -> decompose -> core patterns
-> package -> verify -> hand off) plus the "When NOT to use" anti-trigger.

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

The current 14 / 14 build scripts pass:

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
SKILL.md                          8-step workflow + When-NOT-to-use
README.md                         this file
CHANGELOG.md                      what changed and when
LICENSE                           MIT
pyproject.toml                    ruff + mypy config
.gitignore                        skill-internal ignores

references/
  task_decomposition.md           Step 0+3 deep dive, worked examples
  framework_matrix.md             detailed pros/cons per framework
  distribution_playbook.md        packaging, signing, auto-update
  win32_recipes.md                R1-R13 common Win32 patterns

scripts/
  sendinput_*       (11 scripts)  keyboard input; Python also has mouse
  window_enum_*     (11 scripts)  drop-in window enumeration
  threading_*       (7 templates) background-work templates
  build_*.ps1       (14 helpers)  packaging helpers
  auto_update_*                   Velopack / Squirrel / WinSparkle / Sparkle / AppImageUpdate
  vk_table.json                   canonical key table for keyboard templates
  check_vk_tables.py              verifies Python template matches vk_table.json
  sign_windows.ps1 / sign_macos.sh code signing helpers
  bootstrap_environment.ps1       detect/install toolchains (winget/pip)
  toolchain_map.json              framework -> toolchain mapping

templates/
  requirements_checklist.md       Step 0 fill-in
  requirements_brief.md           JSON/YAML brief for select_framework.py
  task_card.md                    one card per atomic task
  dpi_manifest.xml                Per-monitor V2 awareness
  gui_framework_decision_tree.md  second-level tool picker
  release_checklist.md            release gate checklist
  security_checklist.md           security review checklist

examples/                         minimal runnable projects
  wpf-threading/                  C# WPF + threading_wpf.cs
  winui3-threading/               C# WinUI 3 + threading_winui.cs
  tkinter-threading/              Python tkinter + threading_tkinter.py
  pyside6-threading/              Python PySide6 + threading_pyside6.py
  tauri-threading/                Rust + Web + threading_tauri.rs
  msix-packaging/                 WPF + Windows App SDK packaged as MSIX
  nativeaot-winforms/             WinForms NativeAOT single-file EXE
  game-automation/                TLBB-style bot (window + input + thread)

tests/                            smoke-test fixtures
  fixtures/sample.md, sample_config.json, AppxManifest.xml
```

## Quick recipe -- game automation bot

1. Fill `templates/requirements_checklist.md` (six-bucket interrogation).
2. Pick framework from `references/framework_matrix.md` (likely Python or C#).
3. Decompose tasks with `templates/task_card.md`.
4. Drop in `scripts/sendinput_<lang>` + `scripts/window_enum_<lang>`.
5. Use `scripts/threading_<lang>` for the UI bridge.
6. Package with `scripts/build_python.ps1` or `scripts/build_dotnet.ps1`.
7. Run `scripts/auto_update_*.ps1` for the channel.
8. Or just point at `examples/game-automation/` and start customizing.

## Quick recipe -- productivity / LOB app

Same as above, but the framework matrix row is usually C# WPF or PySide6.
Add `templates/dpi_manifest.xml` to the project for crisp text on
multi-monitor setups.

## CI / continuous testing

`.github/workflows/ci.yml` runs a lint job plus three smoke tests on every
push / PR:

| Job               | OS             | Script                       |
|-------------------|----------------|-------------------------------|
| `lint`            | ubuntu-22.04   | `ruff check` + `ruff format` |
| `test-windows`    | windows-latest | `tests/smoke_windows.ps1`   |
| `test-macos`      | macos-latest   | `tests/smoke_macos.sh`      |
| `test-linux`      | ubuntu-latest  | `tests/smoke_linux.sh`      |

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
- All SendInput implementations put foreground + timing in the helper, not
  in the caller.
- Examples consume canonical `scripts/` templates directly or document
  standalone packaging paths; templates stay canonical, never duplicated.

## Linting

```powershell
pip install ruff mypy
ruff check scripts/ tests/ examples/
ruff format --check scripts/
mypy scripts/   # CI surfaces warnings; it does not fail the build
```
