# build_neutralino.ps1 -- Neutralino.js (TypeScript, no Chromium bundled) packaging.
#
# Install: npm install -g @neutralinojs/neu
#
# Usage: powershell -ExecutionPolicy Bypass -File build_neutralino.ps1
[CmdletBinding()]
param(
    [string] $Mode = "release",   # "release" or "dev"
    [string] $Version = "",
    [ValidateSet("any", "x64", "arm64", "x86")]
    [string] $Arch = "any",       # Neutralino is JS+WebView; arch is decided by the WebView runtime at install time.
    [switch] $BackupSource        # timestamped source zip before packaging
)

$ErrorActionPreference = "Stop"

if ($BackupSource) {
    Write-Host "==> Backing up source before packaging" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "backup_source.ps1") `
        -SourcePath (Get-Location).Path `
        -OutputDir "source_backup" `
        -Name (Split-Path -Leaf (Get-Location).Path)
    if ($LASTEXITCODE -ne 0) { throw "Source backup failed" }
}

if (-not (Get-Command neu -ErrorAction SilentlyContinue)) {
    throw "neu (Neutralino CLI) not on PATH. Install with: npm install -g @neutralinojs/neu"
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm not on PATH. Install Node.js LTS from https://nodejs.org/"
}

Write-Host "==> Neutralino arch: $Arch (Neutralino bundles WebView2; arch follows the user's installed WebView runtime)" -ForegroundColor Cyan
$buildArgs = @("build", "--mode=$Mode")
if ($Version) { $buildArgs += "--app-version=$Version" }

Write-Host "==> neu build --mode=$Mode" -ForegroundColor Cyan
& neu @buildArgs
if ($LASTEXITCODE -ne 0) { throw "neu build failed" }

# Locate produced bundle
$distDir = "dist\$Mode"
if (Test-Path $distDir) {
    Write-Host "==> Bundle: $((Resolve-Path $distDir).Path)" -ForegroundColor Green
    Get-ChildItem $distDir -File | ForEach-Object {
        $size = $_.Length
        Write-Host ("==> Artifact: {0} ({1:N1} MB / {2:N0} KB)" -f $_.FullName, ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
    }
}
Write-Host "Next: zip the $distDir folder into a single archive, optionally sign with signtool, then distribute." -ForegroundColor Yellow
