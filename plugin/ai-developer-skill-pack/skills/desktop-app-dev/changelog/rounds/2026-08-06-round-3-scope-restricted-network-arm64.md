# 2026-08-06 (round 3) -- Scope, restricted network, ARM64

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
