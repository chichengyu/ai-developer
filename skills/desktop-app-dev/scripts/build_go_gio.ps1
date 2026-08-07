# build_go_gio.ps1 -- Gio (Go, GPU) packaging. Gio has no special packager;
# this wraps the standard Go build flags that work well for Gio apps.
#
# Usage: powershell -ExecutionPolicy Bypass -File build_go_gio.ps1
[CmdletBinding()]
param(
    [string] $Output = "myapp.exe",
    [switch] $NoConsole,
    [switch] $Strip,
    [switch] $Upx,
    [ValidateSet("x64", "arm64", "x86")]
    [string] $Arch = "x64"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command go -ErrorAction SilentlyContinue)) { throw "go not on PATH. Install Go from https://go.dev/dl/" }

$goArch = @{ "x64" = "amd64"; "arm64" = "arm64"; "x86" = "386" }[$Arch]
$env:GOOS = "windows"
$env:GOARCH = $goArch
Write-Host "==> Building GOOS=windows GOARCH=$goArch" -ForegroundColor Cyan

$flags = @()
if ($NoConsole) { $flags += "-H windowsgui" }
if ($Strip)      { $flags += "-s"; $flags += "-w" }
$ldflags = ($flags -join " ")

Write-Host "==> go build -ldflags `"$ldflags`" -o $Output ." -ForegroundColor Cyan
go build -ldflags "$ldflags" -o $Output .
if ($LASTEXITCODE -ne 0) { throw "go build failed" }

if ($Upx) {
    if (-not (Get-Command upx -ErrorAction SilentlyContinue)) { throw "UPX not found. Install from https://upx.github.io/" }
    Write-Host "==> upx --best --lzma $Output" -ForegroundColor Cyan
    upx --best --lzma $Output
}

$exePath = Resolve-Path $Output
$size = (Get-Item $exePath).Length
Write-Host ("==> Built: {0} ({1:N0} bytes / {2:N1} KB)" -f $exePath, $size, ($size / 1KB)) -ForegroundColor Green
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow
