# build_dotnet_nativeaot.ps1 -- build a .NET 8 app as a NativeAOT single-file EXE.
#
# NativeAOT produces a self-contained native binary with **no .NET runtime
# required** on the target. Typical sizes for a minimal app:
#
#   * Console hello-world           ~ 1 MB
#   * WinForms hello-world          ~ 5 MB    <-- this example
#   * WPF (NOT supported by NativeAOT)
#   * WinUI 3 (NOT supported by NativeAOT)
#
# Trade-offs:
#   * No reflection, no dynamic loading. Trim-incompatible NuGet packages fail.
#   * Cold start < 50 ms (no JIT, no runtime init).
#   * x64 only on Windows. arm64 NativeAOT ships with .NET 9 preview only.
#
# Usage:
#   powershell -File build_dotnet_nativeaot.ps1 -Project examples/nativeaot-winforms/NativeAotWinFormsDemo.csproj

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Project,
    [ValidateSet("win-x64")]
    [Alias("Arch")]
    [string] $Rid = "win-x64",
    [string] $Configuration = "Release",
    [string] $OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

# NativeAOT on Windows is x64-only as of .NET 8 GA.
if ($Rid -ne "win-x64") {
    throw "NativeAOT requires -Rid win-x64 (got $Rid)."
}

# Sanity: ensure the project opted in. Otherwise the publish is just ReadyToRun.
$csprojText = Get-Content $Project -Raw
if ($csprojText -notmatch "<PublishAot>\s*true\s*</PublishAot>") {
    throw "$Project does not set <PublishAot>true</PublishAot>. This script only builds AOT projects."
}

if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory $OutputDir | Out-Null }

# Pre-flight: warn if the project pulls in packages known to be reflection-heavy.
# (Caller can ignore; this is informational only.)
$reflectionHints = @("Newtonsoft.Json", "System.Reflection.Emit", "AutoMapper", "MediatR")
foreach ($pkg in $reflectionHints) {
    if ($csprojText -match [regex]::Escape($pkg)) {
        Write-Warning "Project references '$pkg'. NativeAOT may emit trim warnings at publish."
    }
}

Write-Host "==> dotnet publish (NativeAOT, $Rid, $Configuration)" -ForegroundColor Cyan
$pubArgs = @(
    "publish", $Project,
    "-c", $Configuration,
    "-r", $Rid,
    "--self-contained", "true",
    "-p:PublishAot=true",
    "-p:PublishSingleFile=true",
    "-p:OptimizationPreference=Size",
    "-p:IlcOptimizationPreference=Size",
    "-o", $OutputDir
)
dotnet @pubArgs
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed (check IL warnings above)" }

# Report the size -- the whole point of NativeAOT is that it is small.
$exe = Join-Path $OutputDir ([System.IO.Path]::GetFileNameWithoutExtension($Project) + ".exe")
if (Test-Path $exe) {
    $size = (Get-Item $exe).Length
    Write-Host ("==> Built: {0}  ({1:N1} KB)" -f $exe, ($size / 1KB)) -ForegroundColor Green
} else {
    Write-Host "==> Built under $OutputDir (EXE name differs from project name)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Next: copy the EXE to a clean Windows VM (no .NET installed) and run." -ForegroundColor Yellow
Write-Host "For a meaningful comparison, build the same UI as WPF: ~70 MB unpacked, ~5 MB with NativeAOT." -ForegroundColor Yellow
