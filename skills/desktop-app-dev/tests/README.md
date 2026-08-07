# tests/

Three smoke tests + one structural test, all runnable locally and on
GitHub Actions across Windows / macOS / Ubuntu.

| Script                       | OS          | Purpose                                                  |
|------------------------------|-------------|----------------------------------------------------------|
| `smoke_windows.ps1`          | Windows     | PowerShell parse + Python imports + fixtures + arch check|
| `smoke_macos.sh`             | macOS       | bash syntax + PowerShell parse + Python + Swift -parse  |
| `smoke_linux.sh`             | Linux       | bash syntax + PowerShell parse + Python AST + const check|
| `test_arch_awareness.ps1`    | Windows*    | Verifies every `build_*.ps1` has `-Arch` / `-Rid`        |

`*` `test_arch_awareness.ps1` runs from PowerShell but uses the
`[System.Management.Automation.Language.Parser]` API to inspect the
script AST -- it works on any OS with PowerShell installed (Windows,
macOS via brew, Linux via apt).

## Running locally

### Windows

```powershell
cd tests
.\smoke_windows.ps1
```

Expected output: `Passed: 45   Failed: 0` (varies slightly as scripts
are added).

### macOS

```bash
cd tests
bash smoke_macos.sh
```

Requires `bash`, `python3`, and optionally `pwsh` + `swift` (both are
skipped if absent).

### Linux

```bash
cd tests
bash smoke_linux.sh
```

Requires `bash`, `python3`, and optionally `pwsh`.

### Arch awareness (any OS with PowerShell)

```powershell
pwsh ./tests/test_arch_awareness.ps1
```

Expected output: `Passed: 16   Failures: 0` (14 build scripts plus the
two `auto_update_*.ps1` parse checks).

## Running on CI

`.github/workflows/ci.yml` defines four jobs:

- `lint`: runs `ruff check scripts/ tests/ examples/` on `ubuntu-22.04`
- `test-windows`: runs `smoke_windows.ps1` on `windows-latest`
- `test-macos`: runs `smoke_macos.sh` on `macos-latest`
- `test-linux`: runs `smoke_linux.sh` on `ubuntu-latest`

Triggers on push to `main`, on PRs targeting `main`, and manual
dispatch. Upload-on-failure artifact retention: 7 days.

## Fixtures

```
tests/fixtures/
  sample.md              # Markdown input for T5.3-style converter tasks
  sample_config.json     # Default settings for a fresh app
  AppxManifest.xml       # Minimal packaged-app manifest for MSIX
```

These are static, OS-agnostic where possible, and small enough to be
read in a single screen.

## What is NOT covered

- Live SendInput / mouse click into a real game -- only do this on a
  dedicated test machine, never in shared CI.
- Real network roundtrips for Velopack / Squirrel upload.
- Code-signing end-to-end (uses your cert locally).
- macOS / Linux runtime behavior of `sendinput_macos.py`,
  `window_enum_macos.py`, `sendinput_linux.py`, `window_enum_linux.py`
  -- the scripts parse + const-table check on each platform, but
  runtime testing requires a GUI session on those hosts.
