# Distribution playbook (deep dive)

Per-framework packaging with exact commands, signing steps, and auto-update
recipes. The build scripts in `scripts/build_*.ps1` are the starting point;
this document is what to do after.

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

## Python: PyInstaller
## Python: PyInstaller

### Single-file EXE
```powershell
pyinstaller --onefile --windowed --name MyApp --icon assets/icon.ico ^
  --add-data "assets;assets" ^
  --hidden-import custom_module ^
  app.py
```

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
  -p:PublishReadyToRun=true ^
  -p:IncludeNativeLibrariesForSelfExtract=true
```

### NativeAOT (smallest)
```powershell
dotnet publish -c Release -r win-x64 --self-contained true ^
  -p:PublishAot=true
```
Requirements: .NET 8+, no dynamic code-gen in dependencies.

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
- `src-tauri/target/release/bundle/nsis/MyApp_0.1.0_x64-setup.exe`
- `src-tauri/target/release/bundle/msi/MyApp_0.1.0_x64_en-US.msi`

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
electron-builder --win nsis --x64
```
Output: `dist/MyApp Setup 0.1.0.exe`.

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
windeployqt --release --qmldir qml build/MyApp.exe

# Build installer
cpack -G NSIS            # or -G WIX for MSI
```

For a single-file portable EXE, build with static Qt (`-static` configure flag
when building Qt itself). Easiest path: use `aqtinstall` to grab a static Qt
build, or use the KDE Craft installer.

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
