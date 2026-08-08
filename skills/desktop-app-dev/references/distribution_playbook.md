# Distribution playbook (deep dive)

Per-framework packaging with exact commands, signing steps, and auto-update
recipes. The build scripts in `scripts/build_*.ps1` are the starting point;
this document is what to do after.

---

## Single-file, zero-runtime, small footprint

When the recipient must get one file, install nothing, and keep RAM low,
rank the framework before you build:

| Framework / artifact           | Single artifact   | Runtime on target                          | Typical size        | Idle memory   |
|--------------------------------|-------------------|--------------------------------------------|---------------------|---------------|
| NativeAOT (WinForms)           | EXE               | none                                       | ~5-15 MB            | ~20-60 MB     |
| Go Fyne / Gio / walk           | EXE               | none                                       | ~8-30 MB            | ~15-60 MB     |
| PyInstaller + tkinter          | EXE               | none                                       | ~10-40 MB           | ~25-80 MB     |
| C++/Qt static                  | EXE               | none                                       | ~10-40 MB           | ~30-80 MB     |
| Tauri NSIS                     | one setup EXE     | WebView2 (Win 10/11 usually preinstalled)  | ~3-10 MB installer  | ~60-120 MB    |
| .NET self-contained            | EXE               | none                                       | ~30-80 MB           | ~50-150 MB    |
| Electron portable              | EXE               | none                                       | ~80-150 MB          | ~150-400 MB   |
| Compose Multiplatform          | MSI/EXE + JBR     | none                                       | ~50-150 MB          | ~150-300 MB   |

The `scripts/build_*.ps1` helpers now default to the size-lean path:
single-file or single-installer output, no runtime install, compression on,
debug symbols off, and a printed size report. Record idle RAM on a clean VM
in Step 6; size without memory is only half the acceptance.

Default size / memory guidance:

| Goal                          | Use                                                   |
|-------------------------------|-------------------------------------------------------|
| Smallest EXE, no runtime      | NativeAOT, raw Win32/MFC, Go Fyne/Gio/walk            |
| Small EXE + fast iteration    | PyInstaller (tkinter), .NET self-contained            |
| One installer, small size     | Tauri NSIS (WebView2 present), Qt NSIS, Go Wails NSIS |
| Avoid for small RAM           | Electron, Compose Multiplatform with default JBR      |

### Runtime memory reduction

- Python: import heavy libraries lazily inside functions, keep
  `pandas` / `numpy` / GUI backends out of module scope when possible, and
  use the size-lean PyInstaller excludes.
- .NET: prefer NativeAOT when the UI stack allows it; otherwise keep
  compression on and avoid `ReadyToRun` unless cold start demands it.
- Go: `-s -w -H windowsgui -trimpath -buildvcs=false` (already the script
  default); do not ship a console subsystem with a GUI app.
- Web-based UIs: Tauri shares the OS WebView2 instead of embedding
  Chromium; Electron should only be chosen when its ecosystem wins matter
  more than RAM.
- Measure on a clean VM: idle RAM, peak RAM during a typical workflow, and
  RAM after the window is minimized. Record all three in the Step 6 report.

---

## Distribution-first override

If the user specifies a hard distribution constraint, narrow the framework
matrix first:

| Distribution | Viable frameworks |
|---|---|
| **Single-file portable EXE** (< 50 MB, no install) | Tauri, Rust+Slint, .NET 8 self-contained + R2R, NativeAOT, C++/Qt static, PyInstaller, Fyne, Gio, walk, Neutralino.js (TS+WebView2), Kotlin/Native (limited desktop UI) |
| **MSI installer** | C#/.NET (WiX), C++/Qt (windeployqt + WiX), Tauri, Electron (electron-builder MSI) |
| **MSIX** | C#/WinUI 3, C#/WPF (WAP), Tauri (MSIX target) |
| **Microsoft Store** | C#/WinUI 3, C#/WPF (packaged), Electron, Tauri |
| **Auto-update channel** | Velopack (any), Squirrel (Electron, C#), WinSparkle (C++/Qt) |
| **Cross-platform + single codebase** | Tauri, .NET MAUI, Avalonia, Electron, Flutter Desktop, Qt, Wails, Fyne, Gio, Compose Multiplatform, Neutralino.js |

## Architecture support matrix

| Framework / script            | Win x64 | Win arm64 | Win x86 | macOS x64 | macOS arm64 | Linux x64 | Linux arm64 | Notes |
|-------------------------------|:-------:|:---------:|:-------:|:---------:|:-----------:|:---------:|:-----------:|-------|
| `build_dotnet.ps1`            |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | per-OS RID; default win-x64 |
| `build_dotnet_nativeaot.ps1`  |   Y     |    -      |    -    |     -     |     -       |     -     |     -       | NativeAOT is win-x64 only |
| `build_electron.ps1`          |   Y     |    Y      |    Y*   |     Y     |     Y       |     Y     |     Y       | `ia32` instead of `x86`     |
| `build_qt.ps1`                |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | needs matching Qt toolchain |
| `build_python.ps1`            |   Y     |    Y*     |    Y*   |     Y     |     Y*      |     Y     |     Y*      | PyInstaller is host-bound   |
| `build_tauri.ps1`             |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | uses Rust target triples    |
| `build_go_wails.ps1`          |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | `windows/{amd64,arm64,386}` |
| `build_go_fyne.ps1`           |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | sets `GOOS`+`GOARCH`       |
| `build_go_gio.ps1`            |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | sets `GOOS=...` + `GOARCH`  |
| `build_kotlin_compose.ps1`    |   Y     |    Y*     |    Y*   |     Y     |     Y*      |     Y     |     Y*      | Compose Desktop arch        |
| `build_swift.ps1`             |   Y     |    Y      |    -    |     Y     |     Y       |     Y*    |     Y*      | `--triple` per triple       |
| `build_neutralino.ps1`        |   Y     |    Y      |    Y    |     Y     |     Y       |     Y     |     Y       | arch follows WebView runtime|
| `build_macos.ps1`             |   -     |    -      |    -    |     Y     |     Y       |     -     |     -       | macOS-only build helper     |
| `build_linux.ps1`             |   -     |    -      |    -    |     -     |     -       |     Y     |     Y       | Linux-only build helper     |
| `build_dmg.sh`                |   -     |    -      |    -    |     Y     |     Y       |     -     |     -       | DMG packaging               |
| `build_appimage.sh`           |   -     |    -      |    -    |     -     |     -       |     Y     |     Y       | AppImage packaging          |
| `build_deb.sh`                |   -     |    -      |    -    |     -     |     -       |     Y     |     Y       | .deb packaging              |

`*` = supported by the toolchain but not yet verified at run time in this skill.

### Source backup

Every `scripts/build_*.ps1` helper accepts `-BackupSource` and creates a
timestamped source zip via `scripts/backup_source.ps1` before packaging.
Use it even when the project is already under version control.

## Python: PyInstaller

### Single-file EXE
```powershell
pyinstaller --onefile --windowed --name MyApp --icon assets/icon.ico ^
  --noupx ^
  --exclude-module unittest --exclude-module pydoc ^
  --exclude-module pydoc_data --exclude-module tkinter.test ^
  --add-data "assets;assets" ^
  --hidden-import custom_module ^
  app.py
```

`scripts/build_python.ps1` already passes `--onefile --windowed --noupx` and
a safe `-ExcludeModules` list (`unittest`, `pydoc`, `pydoc_data`,
`tkinter.test`, `setuptools`, `distutils`). Pass `-ExcludeModules @()` when
the app really imports one of them. UPX is opt-in (`-Upx`) because packed
binaries can trigger AV false positives.

### Common pitfalls
- **Missing module**: PyInstaller static analysis misses dynamic imports
  (`importlib.import_module`, `__import__("mod_" + name)`, plugin systems).
  List each in `--hidden-import`.
- **Missing data**: assets disappear at runtime. Add `--add-data "src;dest"`.
  Access via `sys._MEIPASS`:
  ```python
  import sys, os
  base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
  icon = os.path.join(base, "assets", "icon.ico")
  ```
- **Antivirus flags unsigned EXE**: see Signing below.
- **Slow cold start**: PyInstaller extracts to a temp dir at launch. Switch to
  `--onedir` if cold start matters more than install footprint.

### Source preservation (your stated requirement)
- Bundle source with `--add-data "src;src"` and self-extract on first run:
  ```python
  import zipfile, sys, os
  if not os.path.exists("first_run_done.flag"):
      with zipfile.ZipFile(sys._MEIPASS) as z:
          z.extractall("src")
      open("first_run_done.flag", "w").close()
  ```

---

## .NET: dotnet publish

### Single-file self-contained
```powershell
dotnet publish -c Release -r win-x64 --self-contained true ^
  -p:PublishSingleFile=true ^
  -p:IncludeNativeLibrariesForSelfExtract=true ^
  -p:EnableCompressionInSingleFile=true ^
  -p:DebugType=None ^
  -p:DebugSymbols=false
```

### NativeAOT (smallest)
```powershell
dotnet publish -c Release -r win-x64 --self-contained true ^
  -p:PublishAot=true ^
  -p:PublishSingleFile=true ^
  -p:OptimizationPreference=Size ^
  -p:IlcOptimizationPreference=Size ^
  -p:InvariantGlobalization=true ^
  -p:DebugType=None
```
Requirements: .NET 8+, no dynamic code-gen in dependencies.

`scripts/build_dotnet.ps1` makes ReadyToRun opt-in (`-ReadyToRun`) because
R2R trades several MB for a faster cold start. `-Trim` enables
`PublishTrimmed` for reflection-safe projects; use NativeAOT when the UI
stack allows it for the smallest result.

### Bundle third-party DLLs
Use **Costura.Fody** to embed native DLLs into the managed EXE:
```xml
<PackageReference Include="Costura.Fody" Version="5.7.0" PrivateAssets="all" />
```
Build with `PublishSingleFile=true` for a single-file output that contains
both managed and unmanaged code.

---

## Tauri

```powershell
cargo tauri build
```
Produces:
- `src-tauri/target/release/bundle/nsis/MyApp_0.1.0_x64-setup.exe` (default)
- `src-tauri/target/release/bundle/msi/MyApp_0.1.0_x64_en-US.msi` (with `-Targets msi`)

`scripts/build_tauri.ps1` defaults to the NSIS target (one setup EXE) and
sets the size-lean Rust release profile through Cargo env vars:

```powershell
$env:CARGO_PROFILE_RELEASE_OPT_LEVEL = "z"
$env:CARGO_PROFILE_RELEASE_LTO = "true"
$env:CARGO_PROFILE_RELEASE_CODEGEN_UNITS = "1"
$env:CARGO_PROFILE_RELEASE_PANIC = "abort"
$env:CARGO_PROFILE_RELEASE_STRIP = "true"
```

The equivalent `[profile.release]` block can also go in `src-tauri/Cargo.toml`:

```toml
[profile.release]
opt-level = "z"
lto = true
codegen-units = 1
panic = "abort"
strip = true
```

For auto-update, configure `tauri.conf.json`:
```json
{
  "plugins": {
    "updater": {
      "endpoints": ["https://releases.example.com/{{target}}/{{arch}}/{{current_version}}"],
      "pubkey": "..."
    }
  }
}
```
On app start: `tauri::updater::check_update()` returns an `Update` you can
prompt the user to install.

---

## Electron

```powershell
npm run build
electron-builder --win portable --x64 -c.compression=maximum -c.asar=true
```
Output: `dist/MyApp 0.1.0.exe` (portable, single file). NSIS produces
`dist/MyApp Setup 0.1.0.exe`.

Electron bundles Chromium: expect 80-150 MB and 150-400 MB RAM. If EXE size
or idle memory is a hard budget, use Tauri or NativeAOT instead.

For auto-update, install `electron-updater` and configure
`build.publish.provider = "generic"` in `electron-builder.yml` with your
release server URL.

---

## Qt 6

```powershell
# Build with CMake
cmake -B build -DCMAKE_BUILD_TYPE=Release -G "Ninja"
cmake --build build --config Release

# Collect Qt DLLs
windeployqt --release --no-translations --no-system-d3d-compiler ^
  --no-opengl-sw --no-compiler-runtime --qmldir qml build/MyApp.exe

# Build installer
cpack -G NSIS            # or -G WIX for MSI
```

For a single-file portable EXE, build with static Qt (`-static` configure flag
when building Qt itself). Easiest path: use `aqtinstall` to grab a static Qt
build, or use the KDE Craft installer.

Without static Qt, the NSIS installer produced by `scripts/build_qt.ps1` is
the single-file deliverable; it carries the Qt DLLs and needs no runtime
installed on the recipient machine.

---

## C++ (raw / MFC)

Pure Win32 / MFC apps have no runtime to bundle. Distribute the EXE plus any
DLLs you link against. For auto-update: WinSparkle (https://winsparkle.com)
is a drop-in DLL that handles the entire update flow over HTTPS.

---

## MSI in general

Use **WiX Toolset v3 or v4**:
- v3: XML-based, mature, lots of docs.
- v4: same XML, better MSBuild integration, faster.

Minimum WiX fragment:
```xml
<?xml version="1.0"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="MyApp" Version="0.1.0" Manufacturer="Me" Language="1033">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perMachine" />
    <MediaTemplate EmbedCab="yes" />
    <Directory Id="INSTALLFOLDER" Name="MyApp">
      <Component><File Source="MyApp.exe" /><RegistryValue Root="HKCU" Key="Software\Me\MyApp" Name="installed" Type="integer" Value="1" KeyPath="yes" /></Component>
    </Directory>
    <Feature Id="Main" Title="MyApp" Level="1"><ComponentRef Id="MyApp" /></Feature>
  </Product>
</Wix>
```

---

## MSIX

Two paths:
1. **With Windows Application Packaging Project** (WPF, WinForms): add a
   `Windows Application Packaging Project` to your solution; Visual Studio
   generates the MSIX for you.
2. **Manual with MakeAppx.exe**:
   ```powershell
   MakeAppx.exe pack /d Publish\ /p MyApp.msix
   signtool sign /fd SHA256 /a MyApp.msix
   ```

For Store submission, your MSIX must declare identity, capabilities, and
visual elements in `AppxManifest.xml`.

---

## Auto-update channels compared

| Channel | Framework | Delta updates | HTTPS | Code signing required |
|---|---|---|---|---|
| Velopack | .NET, Rust, anything | yes | yes | yes |
| Squirrel.Windows | .NET, Electron | yes | yes | yes |
| WinSparkle | C++ (any) | no | yes | yes |
| electron-updater | Electron | yes | yes | yes |
| Tauri updater | Tauri | yes | yes | yes |
| Auto-update from custom server | any | roll your own | yes | yes |

Velopack is the most flexible: it works for .NET, Rust, Python (via
`velopack install`), and Electron, with delta updates and Windows installer
or portable bundles.

---

## Signing

Always sign before distribution. SmartScreen and most EDR products flag
unsigned binaries.

```powershell
# Get a code-signing cert from Sectigo, DigiCert, etc.
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Select-Object -First 1
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /sha1 $cert.Thumbprint MyApp.exe
```

For MSI:
```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a MyApp.msi
```

For MSIX, signing is part of `MakeAppx.exe` or Visual Studio's MSIX project.

---

## Verification on a clean Windows VM

Before declaring done:
1. Spin up a clean Windows 11 VM (no Python, no .NET, no Node, no Qt).
2. Copy the EXE / installer.
3. Launch and click through every button.
4. Verify auto-update if applicable: install v1, publish v2 to your update
   channel, restart app, confirm it updates.
5. Verify signed binary passes SmartScreen on first run.
