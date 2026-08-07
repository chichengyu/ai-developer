# Restricted-network playbook

How to ship a Windows desktop GUI application when the build environment
has limited or no internet access. This is a common situation in
enterprise environments, on locked-down CI runners, in air-gapped
factories, and on developer machines behind corporate proxies that
randomly fail. The skill defaults assume you can `pip install`,
`dotnet add package`, etc.; this document gives the offline recipes.

---

## Python

### Pin everything in `requirements.txt`

Never let pip resolve at install time in CI. Pin exact versions and hashes:

```powershell
# Generate pinned, hashed requirements on a machine WITH internet:
python -m pip install pip-tools
pip-compile --generate-hashes --output-file=requirements.txt pyproject.toml

# Install offline:
python -m pip install --require-hashes --no-index --find-links=wheels/ -r requirements.txt
```

### Pre-download wheels

```powershell
mkdir wheels
# On a connected machine:
python -m pip download -r requirements.txt -d wheels/ --only-binary=:all:
# Copy the wheels/ folder to the offline machine and install from it.
```

### PyInstaller hidden imports

PyInstaller `static analysis` cannot see dynamic imports. List them
explicitly in the build command (`--hidden-import ...`); the skill's
`build_python.ps1` already exposes `-HiddenImports` for this.

### Vendoring a single dependency

If you cannot use pip at all, drop the package source into a `vendor/`
folder and add it to `sys.path`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))
import my_dependency
```

This is the cleanest fallback for one or two packages.

### Local PyPI mirror

Set up once on a machine with internet, then point pip at it everywhere:

```powershell
$env:PIP_INDEX_URL = "https://pypi.local/simple"
# Or in pip.conf:
#   [global]
#   index-url = https://pypi.local/simple
#   trusted-host = pypi.local
```

For a server, use `devpi`, `bandersnatch`, or `pypiserver`.

---

## .NET / NuGet

### Pre-restore NuGet packages

```powershell
nuget restore -PackagesDirectory .\packages
# Build offline:
dotnet publish --no-restore -c Release -r win-x64 ...
```

### Local NuGet feed

```xml
<!-- NuGet.config at repo root -->
<configuration>
  <packageSources>
    <clear />
    <add key="local" value="./nuget-packages" />
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
  </packageSources>
</configuration>
```

Copy `*.nupkg` files into `./nuget-packages/` and clear `nuget.org`
when offline.

### Self-contained publish skips NuGet

`dotnet publish -r win-x64 --self-contained true` bundles the runtime
so the resulting EXE runs without the matching .NET SDK installed --
this works even on machines with no NuGet access at runtime. Build the
EXE on a connected machine, copy it to the offline target.

---

## Node / npm

### Pre-build `node_modules`

```powershell
# On connected machine:
npm ci
# Copy the entire node_modules/ tree to the offline machine.
# Build offline:
npm run build --offline
```

### npm offline cache

npm uses `~/.npm` as a cache. With `--prefer-offline` and `--cache`
pointing at a copy of that folder, you can install from cache:

```powershell
npm install --prefer-offline --cache ./npm-cache --offline
```

### yarn / pnpm

`yarn install --offline` and `pnpm install --offline` both honor the
local store/cache.

### Electron-builder without internet

`electron-builder` downloads Electron binaries on first build. Pre-stage
them by setting `ELECTRON_MIRROR` to a local mirror or by caching the
downloads in `%LOCALAPPDATA%\electron\Cache`.

---

## Cargo (Rust / Tauri)

### Cargo vendoring (offline from a Cargo.lock)

```powershell
# On connected machine:
cargo vendor vendor/
# Commit vendor/ to your repo (or copy to offline machine).
# Build offline:
cargo build --offline
```

### Local registry / sparse registry

```toml
# .cargo/config.toml
[source.crates-io]
replace-with = "my-local-registry"

[source.my-local-registry]
registry = "https://cargo.local"
```

Tools: `cargo local-registry`, `tame-index`, or a private `gitea` repo.

---

## Qt

### aqtinstall for offline Qt

`aqt` (aqtinstall) downloads Qt installers; cache them locally:

```powershell
aqt install-qt windows desktop 6.7.0 win64_msvc -O C:\Qt -m qtbase
# Mirror via --archives-dir; offline install pulls from that mirror.
```

Or download the offline installer from
`https://www.qt.io/offline-installers` and run with `--offline`.

---

## MSIX / signing certificates

Code-signing certificates typically come from an internal CA in restricted
networks. Export the cert (with private key) once from a connected
machine, copy the `.pfx` to the offline build host:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.local /td SHA256 `
  /f cert.pfx /p "$env:CERT_PASSWORD" MyApp.exe
```

If your org runs its own timestamp server, replace `timestamp.digicert.com`
with it. Do **not** skip signing; unsigned binaries trip SmartScreen and
every modern EDR.

---

## When all else fails: build on a connected machine

The simplest pattern when the target has no internet and the tools
cannot be vendored:

1. Set up a clean Windows VM with internet access.
2. Build the EXE there.
3. Copy the single-file EXE + (optional) `assets/` folder to the target.
4. Done. The EXE is self-contained; the target machine needs no runtime.

This is exactly the "single-file portable EXE" pattern from
`distribution_playbook.md`, and it is the recommended default for any
non-developer recipient.

---

## Quick decision tree

```
Can you install Python / Node / Rust toolchain on the target?
├── Yes  -> Install the toolchain there, then build locally.
│         Use vendored deps or local mirror as needed.
├── No, but you have a clean machine with internet
│         -> Build there, copy the EXE.
└── No, no internet anywhere
          -> Build the EXE on a connected machine, copy to target.
             The recipient needs zero installs.
```

The last branch covers 90% of real-world recipient situations and is
why the skill's defaults assume PyInstaller / dotnet publish /
electron-builder single-file output.
