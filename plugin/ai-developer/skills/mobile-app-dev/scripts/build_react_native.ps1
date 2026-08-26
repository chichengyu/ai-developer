<#
.SYNOPSIS
    Build a React Native app for iOS and/or Android.

.DESCRIPTION
    Bare-workflow React Native. Runs `npx react-native build-ios` for
    iOS and `gradle :app:bundleRelease` for Android. Supports Expo with
    `eas build` via -UseEas.

.PARAMETER Platform
    ios, android, or both. Default both.

.PARAMETER Configuration
    Debug or Release. Default Release.

.PARAMETER UseEas
    Use EAS Build instead of local build (Expo only).

.PARAMETER ProjectDir
    Android project directory containing gradlew. Defaults to ./android.

.PARAMETER OutputDir
    Where to copy the produced artifact. Defaults to ./build/rn.

.PARAMETER SkipTests
    Skip jest.

.PARAMETER Offline
    npm ci --offline + --no-network for gradle.

.EXAMPLE
    pwsh build_react_native.ps1 -Platform ios -Configuration Release

.EXAMPLE
    pwsh build_react_native.ps1 -UseEas -Platform both
#>

[CmdletBinding()]
param(
    [ValidateSet("ios", "android", "both")]
    [string] $Platform = "both",
    [ValidateSet("Debug", "Release")]
    [string] $Configuration = "Release",
    [switch] $UseEas,
    [string] $ProjectDir = "./android",
    [string] $OutputDir = "./build/rn",
    [switch] $SkipTests,
    [switch] $Offline
)

$ErrorActionPreference = "Stop"

# ---- EAS path -----------------------------------------------------------
if ($UseEas) {
    if (-not (Get-Command eas -ErrorAction SilentlyContinue)) {
        throw "eas CLI not found. Install with 'npm install -g eas-cli'."
    }
    $easPlatform = if ($Platform -eq "both") { "all" } else { $Platform.ToLower() }
    $easArgs = @("build", "--platform", $easPlatform, "--non-interactive")
    Write-Host "==> eas $easArgs" -ForegroundColor Cyan
    & eas @easArgs
    if ($LASTEXITCODE -ne 0) { throw "eas build failed." }
    return
}

# ---- Tests (optional) ---------------------------------------------------
if (-not $SkipTests) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm not on PATH; cannot run jest tests. Pass -SkipTests to skip."
    }
    Write-Host "==> npm test (jest)" -ForegroundColor Cyan
    & npm test -- --watchAll=false
    if ($LASTEXITCODE -ne 0) { throw "npm test failed." }
}

# ---- iOS ----------------------------------------------------------------
$ipaPath = $null
$aabPath = $null

if ($Platform -in "ios", "both") {
    Write-Host "==> npx react-native build-ios --mode $Configuration" -ForegroundColor Cyan
    $rnArgs = @("react-native", "build-ios", "--mode", $Configuration.ToLower())
    if ($Offline) { $rnArgs += "--no-packager" }
    & npx @rnArgs
    if ($LASTEXITCODE -ne 0) { throw "react-native build-ios failed." }

    $src = Get-ChildItem -Recurse -Path "./build/ios", "./ios/build" -Include "*.ipa", "*.app" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($src) {
        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        $ipaPath = Join-Path $OutputDir $src.Name
        Copy-Item $src.FullName $ipaPath -Force
        Write-Host "IPA: $ipaPath" -ForegroundColor Green
    }
}

# ---- Android ------------------------------------------------------------
if ($Platform -in "android", "both") {
    $isWindows = $IsWindows -or ($env:OS -eq "Windows_NT")
    $gradlew = if ($isWindows) { Join-Path $ProjectDir "gradlew.bat" } else { Join-Path $ProjectDir "gradlew" }
    if (-not (Test-Path $gradlew)) {
        throw "Gradle wrapper not found at $ProjectDir."
    }

    $gradleTask = ":app:bundle$($Configuration)"
    Write-Host "==> $gradlew -p $ProjectDir $gradleTask" -ForegroundColor Cyan
    $gradleArgs = @("-p", $ProjectDir, $gradleTask)
    if ($Offline) { $gradleArgs += "--offline" }
    & $gradlew @gradleArgs
    if ($LASTEXITCODE -ne 0) { throw "gradle $gradleTask failed." }

    $src = Get-ChildItem -Recurse (Join-Path $ProjectDir "app/build/outputs/bundle") -Filter "*.aab" -ErrorAction SilentlyContinue | Select-Object -First 1
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
if ($ipaPath) { Write-Host "  IPA: $ipaPath" }
if ($aabPath) { Write-Host "  AAB: $aabPath" }
