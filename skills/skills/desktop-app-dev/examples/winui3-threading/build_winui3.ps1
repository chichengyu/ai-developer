# build_winui3.ps1 -- build the WinUI 3 threading example as a self-contained EXE.
#
# WinUI 3 has two distribution shapes:
#   * Unpackaged (WindowsPackageType=None) -- single EXE, no MSIX, no Store.
#     This is the right choice for recipients who double-click and run.
#   * Packaged (MSIX) -- needed for the Microsoft Store, deep Windows
#     integration (Package.Identity), and per-user clean install.
#     See examples/msix-packaging/ for that path.
#
# Usage:
#   powershell -File build_winui3.ps1                    # default: win-x64 unpackaged
#   powershell -File build_winui3.ps1 -Arch win-arm64    # Snapdragon X / Surface Pro X
#
# Requirements:
#   * .NET 8 SDK
#   * Windows App SDK 1.5+ (NuGet-restore pulls this automatically)
#   * Windows 10 1809+ build host (the WinUI 3 tooling requires it)

[CmdletBinding()]
param(
    [ValidateSet("win-x64", "win-arm64")]
    [string] $Arch = "win-x64",
    [string] $Configuration = "Release",
    [string] $OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$project = Join-Path $root "app\WinUIThreadingDemo.csproj"

if (-not (Test-Path $project)) {
    throw "Project not found: $project. Run from examples/winui3-threading/."
}

if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory $OutputDir | Out-Null }

Write-Host "==> dotnet publish (WinUI 3, self-contained, unpackaged)" -ForegroundColor Cyan
$pubArgs = @(
    "publish", $project,
    "-c", $Configuration,
    "-r", $Arch,
    "--self-contained", "true",
    "-p:PublishSingleFile=false",       # WinUI 3 needs the side-by-side DLLs (MRT, WinUI runtime)
    "-p:WindowsAppSDKSelfContained=true",
    "-p:WindowsPackageType=None",        # unpackaged single-machine install
    "-p:PublishReadyToRun=true",
    "-o", $OutputDir
)
dotnet @pubArgs
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }

Write-Host ""
Write-Host "==> Built: $OutputDir\WinUIThreadingDemo.exe" -ForegroundColor Green
Write-Host "First-run note: WinUI 3 unpackaged apps need the Windows App SDK runtime" -ForegroundColor Yellow
Write-Host "either pre-installed (winget install Microsoft.WindowsAppRuntime.1.5) or" -ForegroundColor Yellow
Write-Host "self-contained (set -p:WindowsAppSDKSelfContained=true, which is the default here)." -ForegroundColor Yellow
Write-Host "Test on a clean Windows 11 VM before shipping." -ForegroundColor Yellow
