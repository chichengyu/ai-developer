# build_go_fyne.ps1 -- Fyne packaging for a Go desktop app.
#
# Usage: powershell -ExecutionPolicy Bypass -File build_go_fyne.ps1
#        powershell -File build_go_fyne.ps1 -Arch arm64
#        powershell -File build_go_fyne.ps1 -Install
[CmdletBinding()]
param(
    [string] $AppId = "com.example.myapp",
    [string] $Version = "0.1.0",
    [string] $Icon = "",
    [switch] $NoConsole,
    [switch] $Strip,
    [ValidateSet("x64", "arm64", "x86")]
    [string] $Arch = "x64",
    [switch] $Install                  # install missing fyne CLI; default is check-only
)

$ErrorActionPreference = "Stop"

# Map Arch to GOARCH for the optional rebuild step.
$goArch = @{ "x64" = "amd64"; "arm64" = "arm64"; "x86" = "386" }[$Arch]
$env:GOARCH = $goArch
Write-Host "==> Building GOARCH=$goArch (Arch=$Arch)" -ForegroundColor Cyan

if (-not (Get-Command go -ErrorAction SilentlyContinue)) { throw "go not on PATH. Install Go from https://go.dev/dl/" }
if (-not (Get-Command fyne -ErrorAction SilentlyContinue)) {
    if (-not $Install) {
        throw "fyne CLI is not installed. Run with -Install to install it, or run: go install fyne.io/fyne/v2/cmd/fyne@latest"
    }
    Write-Host "==> Installing fyne CLI" -ForegroundColor Cyan
    go install fyne.io/fyne/v2/cmd/fyne@latest
    $env:PATH = "$env:USERPROFILE\go\bin;$env:PATH"
}

$pkgArgs = @("package")
if ($Icon -and (Test-Path $Icon)) { $pkgArgs += @("-icon", $Icon) }
$pkgArgs += @("-appID", $AppId, "-appVersion", $Version, "-os", "windows")

Write-Host "==> fyne package" -ForegroundColor Cyan
& fyne @pkgArgs
if ($LASTEXITCODE -ne 0) { throw "fyne package failed" }

# Optionally strip debug info and hide console
if ($Strip -or $NoConsole) {
    $exe = ($AppId -split '\.')[-1] + ".exe"
    if (-not (Test-Path $exe)) {
        Get-ChildItem -Filter *.exe | Select-Object -First 1 | ForEach-Object { $exe = $_.Name }
    }
    if (Test-Path $exe) {
        $ldflags = "-s -w"
        if ($NoConsole) { $ldflags += " -H windowsgui" }
        Write-Host "==> Rebuilding with ldflags `"$ldflags`"" -ForegroundColor Cyan
        go build -ldflags "$ldflags" -o $exe .
    }
}

Write-Host "==> Built. Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Green
