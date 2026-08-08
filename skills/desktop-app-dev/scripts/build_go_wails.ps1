# build_go_wails.ps1 -- Wails v2 packaging for a Go desktop app.
#
# Usage: powershell -ExecutionPolicy Bypass -File build_go_wails.ps1
#        powershell -File build_go_wails.ps1 -Arch arm64
#        powershell -File build_go_wails.ps1 -Install
[CmdletBinding()]
param(
    [ValidateSet("x64", "arm64", "x86")]
    [string] $Arch = "x64",
    [switch] $Nsis,                  # build NSIS installer (add -Nsis to enable)
    [switch] $Clean,
    [string] $Ldflags = "-s -w",     # strip DWARF debug info
    [bool] $Trimpath = $true,        # reproducible, smaller binaries
    [string] $WailsExe = "wails",
    [switch] $Install,               # install missing wails CLI; default is check-only
    [switch] $BackupSource           # timestamped source zip before packaging
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

if (-not (Get-Command go -ErrorAction SilentlyContinue)) { throw "go not on PATH. Install Go from https://go.dev/dl/" }
if (-not (Get-Command $WailsExe -ErrorAction SilentlyContinue)) {
    if (-not $Install) {
        throw "wails CLI is not installed. Run with -Install to install it, or run: go install github.com/wailsapp/wails/v2/cmd/wails@latest"
    }
    Write-Host "==> Installing wails CLI" -ForegroundColor Cyan
    go install github.com/wailsapp/wails/v2/cmd/wails@latest
    $env:PATH = "$env:USERPROFILE\go\bin;$env:PATH"
}

if ($Trimpath) {
    $env:GOFLAGS = "$($env:GOFLAGS) -trimpath -buildvcs=false"
}

if ($Clean) {
    Write-Host "==> Cleaning build/bin and build/darwin" -ForegroundColor Cyan
    Remove-Item -LiteralPath "build/bin" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "build/darwin" -Recurse -Force -ErrorAction SilentlyContinue
}

# Map our friendly Arch to Wails' GOOS/GOARCH.
$Platform = @{
    "x64"   = "windows/amd64"
    "arm64" = "windows/arm64"
    "x86"   = "windows/386"
}[$Arch]
Write-Host "==> Wails platform: $Platform (Arch=$Arch)" -ForegroundColor Cyan

$buildArgs = @("build", "-platform", $Platform)
$buildArgs += "-ldflags", $Ldflags
if ($Nsis) { $buildArgs += "-nsis" }

Write-Host "==> wails build" -ForegroundColor Cyan
& $WailsExe @buildArgs
if ($LASTEXITCODE -ne 0) { throw "wails build failed" }

$exe = Get-ChildItem -Path "build/bin" -Filter *.exe -ErrorAction SilentlyContinue |
       Where-Object { $_.Name -notmatch 'installer' } |
       Select-Object -First 1 -ExpandProperty FullName
if (-not $exe) {
    Write-Host "==> Looking for built EXE in build/bin/ ..." -ForegroundColor Yellow
    Get-ChildItem build/bin/ -ErrorAction SilentlyContinue
} else {
    Write-Host "==> Built EXE: $exe" -ForegroundColor Green
}
$nsis = Get-ChildItem -Path "build/bin" -Filter *.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'installer' } |
        Select-Object -First 1 -ExpandProperty FullName
if ($nsis) { Write-Host "==> NSIS installer: $nsis" -ForegroundColor Green }
if ($exe) {
    $size = (Get-Item $exe).Length
    Write-Host ("==> EXE size: {0:N1} MB / {1:N0} KB" -f ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
}
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow
