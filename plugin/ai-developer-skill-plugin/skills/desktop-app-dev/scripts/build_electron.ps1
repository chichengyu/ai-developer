# build_electron.ps1 -- Electron packaging via electron-builder (NSIS + MSI + portable).
#
# Usage: powershell -ExecutionPolicy Bypass -File build_electron.ps1 -Target win
#        powershell -ExecutionPolicy Bypass -File build_electron.ps1 -Install
[CmdletBinding()]
param(
    [ValidateSet("win", "nsis", "msi", "portable", "all")]
    [string] $Target = "win",              # win | nsis | msi | portable | all
    [ValidateSet("x64", "arm64", "ia32")]
    [string] $Arch = "x64",                # x64 | arm64 | ia32
    [string] $Config = "",                 # path to electron-builder.yml (default: ./electron-builder.yml)
    [switch] $Publish = $false,            # upload to the configured publish provider
    [string] $OutputDir = "dist",
    [switch] $Install,                     # install missing npm deps / electron-builder; default is check-only
    [switch] $BackupSource                 # timestamped source zip before packaging
)

$ErrorActionPreference = "Stop"

Write-Host "==> NOTE: Electron bundles Chromium; expect 80-150 MB and roughly 150-400 MB RAM." -ForegroundColor Yellow
Write-Host "    If EXE size and idle memory are hard budgets, prefer Tauri or .NET NativeAOT." -ForegroundColor Yellow

if ($BackupSource) {
    Write-Host "==> Backing up source before packaging" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "backup_source.ps1") `
        -SourcePath (Get-Location).Path `
        -OutputDir (Join-Path $OutputDir "source_backup") `
        -Name (Split-Path -Leaf (Get-Location).Path)
    if ($LASTEXITCODE -ne 0) { throw "Source backup failed" }
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm not on PATH. Install Node.js LTS from https://nodejs.org/"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "node not on PATH. Install Node.js LTS from https://nodejs.org/"
}

# 1. Install dependencies if node_modules is missing (only with -Install)
if (-not (Test-Path "node_modules")) {
    if (-not $Install) {
        throw "node_modules is missing. Run with -Install to run npm ci, or run npm ci yourself."
    }
    Write-Host "==> npm ci" -ForegroundColor Cyan
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
}

# 2. Production build (Vite/webpack/etc.). Skipped silently if no build script.
$pkg = Get-Content "package.json" -Raw | ConvertFrom-Json -ErrorAction Stop
if ($pkg.scripts.build) {
    Write-Host "==> npm run build" -ForegroundColor Cyan
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} else {
    Write-Host "No 'build' script in package.json; skipping frontend build." -ForegroundColor Yellow
}

# 3. Run electron-builder
$ebArgs = @("-c.compression=maximum", "-c.asar=true", "-c.npmRebuild=false", "-c.directories.output=$OutputDir")
if ($Config) { $ebArgs += "--config"; $ebArgs += $Config }
if ($Target -eq "all") {
    $ebArgs += "--win"; $ebArgs += "nsis"; $ebArgs += "msi"; $ebArgs += "portable"
} else {
    $ebArgs += "--win"; $ebArgs += $Target
}
if ($Arch) { $ebArgs += "--$Arch" }
if ($Publish) { $ebArgs += "--publish"; $ebArgs += "always" }

if (-not (Test-Path "node_modules\.bin\electron-builder.cmd")) {
    if (-not $Install) {
        throw "electron-builder is missing. Run with -Install to install it, or run: npm install --save-dev electron-builder"
    }
    Write-Host "==> Installing electron-builder" -ForegroundColor Cyan
    & npm install --save-dev electron-builder
    if ($LASTEXITCODE -ne 0) { throw "electron-builder install failed" }
}

Write-Host "==> electron-builder $ebArgs" -ForegroundColor Cyan
& node_modules\.bin\electron-builder.cmd @ebArgs
if ($LASTEXITCODE -ne 0) { throw "electron-builder failed" }

# 4. Collect
if (Test-Path -LiteralPath $OutputDir) {
    Get-ChildItem -LiteralPath $OutputDir -File -Recurse | ForEach-Object {
        $size = $_.Length
        Write-Host ("==> Artifact: {0}  ({1:N1} MB / {2:N0} KB)" -f $_.FullName, ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
    }
}
Write-Host "==> Done. Output under $OutputDir" -ForegroundColor Green
Write-Host "Next: sign the EXE with signtool, then test on a clean Windows VM." -ForegroundColor Yellow

