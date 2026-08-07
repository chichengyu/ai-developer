# auto_update_squirrel.ps1 -- Squirrel.Windows release helper for .NET / Electron.
#
# Squirrel.Windows is git-diff based: each release is a delta against the
# previous nupkg. Use with C# (via NuGet package `Squirrel`) or Electron
# (electron-builder supports Squirrel as a target).
#
# Install Squirrel CLI:
#   dotnet tool install -g squirrel.windows
#
# For Electron, prefer electron-builder --win squirrel which produces the
# RELEASES + nupkg pair out of the box.
#
# Usage: powershell -ExecutionPolicy Bypass -File auto_update_squirrel.ps1
param(
    [Parameter(Mandatory)] [string] $Version,
    [Parameter(Mandatory)] [string] $MainExe,
    [string] $Title = "",
    [string] $IconPath = "",
    [string] $OutputDir = "dist\squirrel"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command squirrel -ErrorAction SilentlyContinue)) {
    throw "squirrel not on PATH. Install: dotnet tool install -g squirrel.windows"
}

if (-not (Test-Path $MainExe)) { throw "MainExe not found: $MainExe" }
$MainExe = (Resolve-Path $MainExe).Path
$Title = if ($Title) { $Title } else { [System.IO.Path]::GetFileNameWithoutExtension($MainExe) }

# Squirrel expects the binary in a stable folder per release.
$stage = Join-Path $OutputDir "app-$Version"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item (Split-Path $MainExe -Parent) $stage -Recurse -Force

# The exe MUST be named the same as the package id, so rename if needed.
$target = Join-Path $stage "$Title.exe"
if ($MainExe -ne $target) {
    Move-Item -Path $MainExe -Destination $target -Force
}

$relArgs = @("--releasify", $stage,
    "--releaseDir", $OutputDir,
    "--packagesDir", (Join-Path $OutputDir "packages"),
    "--bootstrapperExe", "$Title.exe",
    "--splashScreen", "")
if ($IconPath -and (Test-Path $IconPath)) {
    $relArgs += "--icon"; $relArgs += $IconPath
}

Write-Host "==> squirrel --releasify" -ForegroundColor Cyan
& squirrel @relArgs
if ($LASTEXITCODE -ne 0) { throw "squirrel --releasify failed" }

Get-ChildItem $OutputDir | Select-Object Name, Length | Format-Table -AutoSize
Write-Host "==> Squirrel release produced. Upload RELEASES + *.nupkg to your update server." -ForegroundColor Green
