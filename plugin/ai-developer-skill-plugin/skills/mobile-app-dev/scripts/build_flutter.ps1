<#
.SYNOPSIS
    Build a Flutter app for iOS and/or Android.

.DESCRIPTION
    Runs `flutter build ipa` and/or `flutter build appbundle`. Honors
    Flutter --flavor (which maps to iOS scheme + Android product flavor).

.PARAMETER Platform
    ios, android, or both. Default both.

.PARAMETER Flavor
    Optional Flutter --flavor.

.PARAMETER BuildMode
    release, profile, or debug. Default release.

.PARAMETER OutputDir
    Where to copy the produced IPA / AAB. Defaults to ./build/flutter.

.PARAMETER SkipTests
    Skip `flutter test`.

.PARAMETER Offline
    Run `flutter pub get --offline` before building.

.EXAMPLE
    pwsh build_flutter.ps1 -Platform ios

.EXAMPLE
    pwsh build_flutter.ps1 -Platform both -Flavor production -BuildMode release
#>

[CmdletBinding()]
param(
    [ValidateSet("ios", "android", "both")]
    [string] $Platform = "both",
    [string] $Flavor,
    [ValidateSet("release", "profile", "debug")]
    [string] $BuildMode = "release",
    [string] $OutputDir = "./build/flutter",
    [switch] $SkipTests,
    [switch] $Offline
)

$ErrorActionPreference = "Stop"

# ---- Guard: flutter on PATH ---------------------------------------------
if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    throw "flutter not on PATH. Install Flutter SDK and ensure it's on PATH."
}

$isWindowsHost = $IsWindows -or ($env:OS -eq "Windows_NT")

# ---- Restore dependencies before building ------------------------------
if ($Offline) {
    Write-Host "==> flutter pub get --offline" -ForegroundColor Cyan
    & flutter pub get --offline
    if ($LASTEXITCODE -ne 0) { throw "flutter pub get --offline failed." }
}

# ---- Compose flutter args -----------------------------------------------
$flutterArgs = @()
if ($Flavor)   { $flutterArgs += "--flavor", $Flavor }
if ($BuildMode) { $flutterArgs += "--" + $BuildMode }

# ---- Tests (optional) ---------------------------------------------------
if (-not $SkipTests) {
    Write-Host "==> flutter test" -ForegroundColor Cyan
    & flutter test
    if ($LASTEXITCODE -ne 0) { throw "flutter test failed." }
}

# ---- iOS ----------------------------------------------------------------
$ipaPath = $null
$aabPath = $null

if ($Platform -in "ios", "both") {
    if ($isWindowsHost -or $IsLinux) {
        throw "flutter build ipa requires macOS. Detected host: $($PSVersionTable.OS)."
    }
    Write-Host "==> flutter build ipa" -ForegroundColor Cyan
    & flutter build ipa @flutterArgs
    if ($LASTEXITCODE -ne 0) { throw "flutter build ipa failed." }

    $src = Get-ChildItem -Recurse "./build/ios/ipa" -Filter "*.ipa" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($src) {
        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        $ipaPath = Join-Path $OutputDir $src.Name
        Copy-Item $src.FullName $ipaPath -Force
        Write-Host "IPA: $ipaPath" -ForegroundColor Green
    }
}

# ---- Android ------------------------------------------------------------
if ($Platform -in "android", "both") {
    Write-Host "==> flutter build appbundle" -ForegroundColor Cyan
    & flutter build appbundle @flutterArgs
    if ($LASTEXITCODE -ne 0) { throw "flutter build appbundle failed." }

    $src = Get-ChildItem -Recurse "./build/app/outputs/bundle" -Filter "*.aab" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($src) {
        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        $aabPath = Join-Path $OutputDir $src.Name
        Copy-Item $src.FullName $aabPath -Force
        Write-Host "AAB: $aabPath" -ForegroundColor Green
    }
}

# ---- Done ---------------------------------------------------------------
Write-Host ""
Write-Host "Done." -ForegroundColor Green
if ($ipaPath) {
    Write-Host "  IPA: $ipaPath"
    Write-Host "  Upload to TestFlight: fastlane pilot upload --ipa $ipaPath"
}
if ($aabPath) {
    Write-Host "  AAB: $aabPath"
    Write-Host "  Upload to Play: fastlane supply --aab $aabPath --track production --json_key api-key.json"
}
