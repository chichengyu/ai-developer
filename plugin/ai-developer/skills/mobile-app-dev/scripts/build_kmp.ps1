<#
.SYNOPSIS
    Build a Kotlin Multiplatform app for iOS and/or Android.

.DESCRIPTION
    KMP apps share the KMP module via .xcframework (iOS) and Gradle
    artifact (Android). The iOS app consumes the .xcframework via
    CocoaPods or Swift Package Manager.

.PARAMETER Platform
    ios, android, or both. Default both.

.PARAMETER Configuration
    Debug or Release. Default Release.

.PARAMETER KmpModule
    Path to the shared KMP module. Defaults to ./shared.

.PARAMETER SharedModule
    Gradle name of the shared KMP module. Defaults to shared.

.PARAMETER IosProject
    Path to the iOS Xcode project. Defaults to ./iosApp.

.PARAMETER IosScheme
    Xcode scheme used for the iOS app. Defaults to iosApp.

.PARAMETER AndroidProject
    Path to the Android Gradle project. Defaults to ./androidApp.

.PARAMETER AndroidModule
    Android Gradle module that contains the app. Defaults to composeApp.

.PARAMETER OutputDir
    Where to copy produced artifacts. Defaults to ./build/kmp.

.EXAMPLE
    pwsh build_kmp.ps1 -Platform ios

.EXAMPLE
    pwsh build_kmp.ps1 -Platform android -SkipTests
#>

[CmdletBinding()]
param(
    [ValidateSet("ios", "android", "both")]
    [string] $Platform = "both",
    [ValidateSet("Debug", "Release")]
    [string] $Configuration = "Release",
    [string] $KmpModule = "./shared",
    [string] $SharedModule = "shared",
    [string] $IosProject = "./iosApp",
    [string] $IosScheme = "iosApp",
    [string] $AndroidProject = "./androidApp",
    [string] $AndroidModule = "composeApp",
    [string] $OutputDir = "./build/kmp",
    [switch] $SkipTests
)

$ErrorActionPreference = "Stop"
$isWindowsHost = $IsWindows -or ($env:OS -eq "Windows_NT")

# ---- Shared tests (optional) -------------------------------------------
if (-not $SkipTests) {
    $testGradlew = if ($isWindowsHost) {
        Join-Path $KmpModule "gradlew.bat"
    } else {
        Join-Path $KmpModule "gradlew"
    }
    if (-not (Test-Path $testGradlew)) {
        throw "KMP Gradle wrapper not found at $KmpModule."
    }
    Write-Host "==> KMP shared -> $SharedModule:allTests" -ForegroundColor Cyan
    & $testGradlew -p $KmpModule ":$SharedModule:allTests"
    if ($LASTEXITCODE -ne 0) { throw "KMP $SharedModule:allTests failed." }
}

# ---- Build the shared .xcframework (for iOS) ---------------------------
if ($Platform -in "ios", "both") {
    if ($isWindowsHost -or $IsLinux) {
        throw "KMP iOS build requires macOS. Detected host: $($PSVersionTable.OS)."
    }

    $gradlew = Join-Path $KmpModule "gradlew"
    if (-not (Test-Path $gradlew)) {
        throw "KMP Gradle wrapper not found at $KmpModule."
    }

    Write-Host "==> KMP shared -> $SharedModule:assembleXCFramework" -ForegroundColor Cyan
    & $gradlew -p $KmpModule ":$SharedModule:assembleXCFramework"
    if ($LASTEXITCODE -ne 0) { throw "KMP $SharedModule:assembleXCFramework failed." }
}

# ---- iOS app build ------------------------------------------------------
$ipaPath = $null
$aabPath = $null

if ($Platform -in "ios", "both") {
    $xcodeProj = Get-ChildItem -Path $IosProject -Filter "*.xcodeproj" -ErrorAction SilentlyContinue | Select-Object -First 1
    $xcodeWs   = Get-ChildItem -Path $IosProject -Filter "*.xcworkspace" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $xcodeProj -and -not $xcodeWs) {
        throw "No .xcodeproj or .xcworkspace found in $IosProject."
    }
    $targetArgs = if ($xcodeWs) {
        @("-workspace", $xcodeWs.FullName)
    } else {
        @("-project", $xcodeProj.FullName)
    }

    Write-Host "==> xcodebuild archive" -ForegroundColor Cyan
    & xcodebuild @targetArgs `
        -scheme $IosScheme `
        -configuration $Configuration `
        -destination "generic/platform=iOS" `
        -archivePath "$OutputDir/iosApp.xcarchive" `
        archive
    if ($LASTEXITCODE -ne 0) { throw "xcodebuild archive failed." }
    $ipaPath = "$OutputDir/iosApp.xcarchive"
}

# ---- Android app build --------------------------------------------------
if ($Platform -in "android", "both") {
    $gradlew = Join-Path $AndroidProject "gradlew.bat"
    if (-not (Test-Path $gradlew)) {
        $gradlew = Join-Path $AndroidProject "gradlew"
    }
    if (-not (Test-Path $gradlew)) {
        throw "Android Gradle wrapper not found at $AndroidProject."
    }

    $androidTask = ":$AndroidModule:bundle$Configuration"
    Write-Host "==> gradle $androidTask" -ForegroundColor Cyan
    & $gradlew -p $AndroidProject $androidTask
    if ($LASTEXITCODE -ne 0) { throw "gradle $androidTask failed." }

    $src = Get-ChildItem -Recurse "$AndroidProject/$AndroidModule/build/outputs/bundle" -Filter "*.aab" -ErrorAction SilentlyContinue | Select-Object -First 1
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
if ($ipaPath) { Write-Host "  Xcode archive: $ipaPath" }
if ($aabPath) { Write-Host "  AAB: $aabPath" }
