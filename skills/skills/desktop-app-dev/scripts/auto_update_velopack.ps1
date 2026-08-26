# auto_update_velopack.ps1 -- build + release using Velopack for any framework.
#
# Velopack works for .NET, Rust, Python (via vpk install), Electron. It
# produces delta updates, Windows installers, and portable bundles.
# https://velopack.io/
#
# Install Velopack CLI:
#   winget install velopack.velopack
#   # or: dotnet tool install -g vpk
#   # or download from https://aka.ms/velopack-release
#
# Usage:
#   1. Publish your build artifact (EXE for portable, or installer for setup)
#   2. Run this script with -Version 1.0.1 to pack + upload to the channel
param(
    [Parameter(Mandatory)] [string] $Version,        # e.g. "1.0.1"
    [Parameter(Mandatory)] [string] $MainExe,        # path to the EXE that Velopack should launch
    [string] $Channel = "stable",                   # stable | beta | alpha
    [string] $Title = "",                           # display name (defaults to MainExe base name)
    [string] $IconPath = "",                        # .ico for shortcuts
    [string[]] $Runtimes = @(),                     # e.g. @("net6","net7") for .NET self-contained
    [string] $ReleaseDir = "dist",
    [string] $FeedUrl = "",                         # https URL Velopack uploads deltas to
    [string[]] $DeltaFromVersions = @()             # previous versions to compute deltas against
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command vpk -ErrorAction SilentlyContinue)) {
    throw "vpk not on PATH. Install Velopack: winget install velopack.velopack"
}

if (-not (Test-Path $MainExe)) { throw "MainExe not found: $MainExe" }
$MainExe = (Resolve-Path $MainExe).Path
$Title = if ($Title) { $Title } else { [System.IO.Path]::GetFileNameWithoutExtension($MainExe) }

# 1. Pack into a Velopack release directory.
$packArgs = @("pack",
    "--packId",    ($Title -replace '\s','.').ToLower(),
    "--packVersion", $Version,
    "--packDir",   (Split-Path $MainExe -Parent),
    "--packTitle", $Title,
    "--mainExe",   $MainExe,
    "--channel",   $Channel,
    "--outputDir", $ReleaseDir
)
foreach ($r in $Runtimes) { $packArgs += "--runtime"; $packArgs += $r }
if ($IconPath -and (Test-Path $IconPath)) {
    $packArgs += "--icon"; $packArgs += $IconPath
}
foreach ($dv in $DeltaFromVersions) {
    $packArgs += "--deltaFromVersion"; $packArgs += $dv
}

Write-Host "==> vpk pack $Version" -ForegroundColor Cyan
& vpk @packArgs
if ($LASTEXITCODE -ne 0) { throw "vpk pack failed" }

# 2. Upload (if FeedUrl given).
if ($FeedUrl) {
    $releasePath = Join-Path $ReleaseDir "$Channel"
    if (Test-Path $releasePath) {
        Write-Host "==> Uploading to $FeedUrl" -ForegroundColor Cyan
        # Velopack upload via vpk upload <dir> --url <feed>. The exact flag set
        # depends on your host; replace this with `aws s3 sync`, `azcopy`,
        # `gsutil rsync`, or a custom API POST.
        & vpk upload $releasePath --url $FeedUrl
        if ($LASTEXITCODE -ne 0) { throw "upload failed" }
    } else {
        Write-Host "Release path $releasePath not found; skipping upload." -ForegroundColor Yellow
    }
}

# 3. Print summary
Get-ChildItem $ReleaseDir -Recurse -File | Select-Object FullName, Length | Format-Table -AutoSize
Write-Host "==> Velopack release ready under $ReleaseDir\$Channel" -ForegroundColor Green
Write-Host "Next: clients auto-discover via the feed URL on next launch." -ForegroundColor Yellow
