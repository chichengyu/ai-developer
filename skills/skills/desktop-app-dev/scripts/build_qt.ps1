# build_qt.ps1 -- C++/Qt 6 packaging with windeployqt + cpack.
#
# Two outputs are produced:
#   1. A portable folder (build/release/<AppName>/<AppName>.exe + Qt DLLs + plugins)
#   2. An NSIS installer via cpack -G NSIS (override with -Generator)
#
# Usage: powershell -ExecutionPolicy Bypass -File build_qt.ps1 -AppName MyApp -SourceDir .
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $AppName,
    [string] $SourceDir = ".",
    [string] $BuildDir = "build",
    [string] $Generator = "Ninja",          # Ninja, "Visual Studio 17 2022", NMake Makefiles...
    [string] $QtDir = "",                   # e.g. C:\Qt\6.7.0\msvc2019_64. Auto-detected if empty.
    [ValidateSet("x64", "arm64", "x86")]
    [string] $Arch = "x64",
    [string] $Config = "Release",
    [string] $PackageType = "NSIS",         # NSIS | WIX (MSI) | IFW_ServerInstaller | THIRDPARTY
    [bool] $MinimalDeploy = $true,          # skip translations/compiler-runtime/software GL to shrink the bundle
    [string] $OutputDir = "dist",
    [switch] $BackupSource                  # timestamped source zip before packaging
)

# Map Arch to the Qt toolchain prefix we expect to find.
$qtArchDir = @{
    "x64"   = "msvc2019_64"
    "arm64" = "msvc2022_arm64"     # Qt 6.5+ ships MSVC arm64
    "x86"   = "msvc2019"
}[$Arch]

$ErrorActionPreference = "Stop"

if ($BackupSource) {
    Write-Host "==> Backing up source before packaging" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "backup_source.ps1") `
        -SourcePath (Get-Location).Path `
        -OutputDir (Join-Path $OutputDir "source_backup") `
        -Name $AppName
    if ($LASTEXITCODE -ne 0) { throw "Source backup failed" }
}

function Resolve-QtBin {
    param([string]$Dir)
    if ($Dir -and (Test-Path (Join-Path $Dir "bin\windeployqt.exe"))) { return $Dir }
    if ($env:QTDIR -and (Test-Path (Join-Path $env:QTDIR "bin\windeployqt.exe"))) { return $env:QTDIR }
    # Try the aqtinstall convention, prefer the architecture-specific subdir.
    $candidates = Get-ChildItem "C:\Qt\6.*" -Directory -ErrorAction SilentlyContinue |
                  Where-Object { $_.Name -like "*$qtArchDir*" -and (Test-Path (Join-Path $_.FullName "bin\windeployqt.exe")) } |
                  Sort-Object Name -Descending
    if ($candidates) { return $candidates[0].FullName }
    throw "Qt $qtArchDir not found. Set -QtDir or QTDIR env var. Install Qt 6 via aqtinstall or Qt online installer."
}

if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    throw "cmake not on PATH. Install from https://cmake.org/download/ or via Visual Studio Installer."
}

$qtDir = Resolve-QtBin -Dir $QtDir
$qtBin = Join-Path $qtDir "bin"
Write-Host "==> Using Qt: $qtDir" -ForegroundColor Cyan

# 1. Configure
$configureArgs = @("-S", $SourceDir, "-B", $BuildDir, "-G", $Generator, "-DCMAKE_BUILD_TYPE=$Config",
                   "-DCMAKE_PREFIX_PATH=$qtDir")
Write-Host "==> cmake configure" -ForegroundColor Cyan
& cmake @configureArgs
if ($LASTEXITCODE -ne 0) { throw "cmake configure failed" }

# 2. Build
Write-Host "==> cmake build" -ForegroundColor Cyan
& cmake --build $BuildDir --config $Config
if ($LASTEXITCODE -ne 0) { throw "cmake build failed" }

# 3. Locate exe (caller is expected to set MYAPP_EXE target via CMakeLists)
$exePath = Get-ChildItem -Path $BuildDir -Recurse -Filter "$AppName.exe" -ErrorAction SilentlyContinue |
           Select-Object -First 1 -ExpandProperty FullName
if (-not $exePath) { throw "Could not find $AppName.exe under $BuildDir" }

# 4. windeployqt
Write-Host "==> windeployqt" -ForegroundColor Cyan
$windeployArgs = @("--release")
if ($MinimalDeploy) {
    $windeployArgs += "--no-translations"
    $windeployArgs += "--no-system-d3d-compiler"
    $windeployArgs += "--no-opengl-sw"
    $windeployArgs += "--no-compiler-runtime"
}
if (Test-Path (Join-Path $SourceDir "qml")) {
    $windeployArgs += "--qmldir"
    $windeployArgs += (Join-Path $SourceDir "qml")
}
$windeployArgs += $exePath
& (Join-Path $qtBin "windeployqt.exe") @windeployArgs
if ($LASTEXITCODE -ne 0) { throw "windeployqt failed" }

# 5. Optional installer via cpack
if ($PackageType -in @("NSIS","WIX")) {
    if (-not (Get-Command cpack -ErrorAction SilentlyContinue)) {
        Write-Host "cpack not on PATH; skipping installer." -ForegroundColor Yellow
    } else {
        Write-Host "==> cpack -G $PackageType" -ForegroundColor Cyan
        & cpack -G $PackageType -C $Config --config (Join-Path $BuildDir "CPackConfig.cmake")
        if ($LASTEXITCODE -ne 0) { throw "cpack failed" }
    }
}

# 6. Collect into dist
if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir | Out-Null }
$staging = Join-Path $OutputDir $AppName
if (Test-Path $staging) {
    $sourceRoot = (Resolve-Path -LiteralPath $SourceDir).Path
    $stagingPath = (Resolve-Path -LiteralPath $staging).Path
    if ($stagingPath -eq $sourceRoot -or
        $sourceRoot.StartsWith($stagingPath + [System.IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove ${staging}: it overlaps the project source at ${sourceRoot}. Set -OutputDir to a generated-output directory."
    }
    Remove-Item -LiteralPath $staging -Recurse -Force
}
Copy-Item (Split-Path $exePath -Parent) $staging -Recurse -Force

Write-Host "==> Staged: $staging" -ForegroundColor Green
$stagedSize = (Get-ChildItem $staging -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("==> Portable folder size: {0:N1} MB ({1:N0} KB). Use the NSIS installer as the single-file deliverable." -f ($stagedSize / 1MB), ($stagedSize / 1KB)) -ForegroundColor Green
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow

