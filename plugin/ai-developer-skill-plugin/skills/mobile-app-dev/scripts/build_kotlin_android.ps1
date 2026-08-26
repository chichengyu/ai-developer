<#
.SYNOPSIS
    Build an Android app via Gradle.

.DESCRIPTION
    Runs assemble (APK) and/or bundle (AAB) for the selected flavor +
    build type. Supports keystore signing via key.properties.

    Requires JDK 17+ and Android SDK (set ANDROID_HOME / ANDROID_SDK_ROOT).

.PARAMETER ProjectDir
    Directory containing the Gradle wrapper. Defaults to ./android.

.PARAMETER Flavor
    Optional product flavor (e.g., dev, staging, production). If omitted,
    no flavor is used (useDebug / useRelease).

.PARAMETER BuildType
    Debug or Release. Default Release.

.PARAMETER OutputFormat
    apk, aab, or both. Default both.

.PARAMETER SkipTests
    Skip unit tests.

.PARAMETER OutputDir
    Where to copy the produced APK / AAB. Defaults to ./build/android.

.PARAMETER Offline
    Use --offline so Gradle never hits Maven Central / Google Maven.

.EXAMPLE
    pwsh build_kotlin_android.ps1 -Flavor production -BuildType Release

.EXAMPLE
    pwsh build_kotlin_android.ps1 -OutputFormat apk -SkipTests -Offline
#>

[CmdletBinding()]
param(
    [string] $ProjectDir = "./android",
    [string] $Flavor,
    [ValidateSet("Debug", "Release")]
    [string] $BuildType = "Release",
    [ValidateSet("apk", "aab", "both")]
    [string] $OutputFormat = "both",
    [switch] $SkipTests,
    [string] $OutputDir = "./build/android",
    [switch] $Offline
)

$ErrorActionPreference = "Stop"

# ---- Guard: gradle wrapper present --------------------------------------
$gradlew = Join-Path $ProjectDir "gradlew.bat"
$gradlewSh = Join-Path $ProjectDir "gradlew"
if (-not (Test-Path $gradlew) -and -not (Test-Path $gradlewSh)) {
    throw "Gradle wrapper not found at $ProjectDir. Run 'gradle wrapper' or 'flutter create' / 'npx react-native init' first."
}

$isWindows = $IsWindows -or ($env:OS -eq "Windows_NT")
$gradlewCmd = if ($isWindows -and (Test-Path $gradlew)) { $gradlew } else { $gradlewSh }
if (-not (Test-Path $gradlewCmd)) {
    throw "Gradle wrapper not found: $gradlewCmd"
}

# ---- Guard: ANDROID_HOME / SDK ------------------------------------------
if (-not $env:ANDROID_HOME -and -not $env:ANDROID_SDK_ROOT) {
    $localSdk = "$env:LOCALAPPDATA\Android\Sdk"
    if (Test-Path $localSdk) {
        $env:ANDROID_HOME = $localSdk
        Write-Host "Using ANDROID_HOME=$localSdk" -ForegroundColor Yellow
    } else {
        throw "ANDROID_HOME / ANDROID_SDK_ROOT not set and no local Android SDK found."
    }
}

# ---- Build task names ---------------------------------------------------
$flavorTask = if ($Flavor) {
    $Flavor.Substring(0, 1).ToUpperInvariant() + $Flavor.Substring(1)
} else {
    ""
}
$assembleTask = "assemble$flavorTask$BuildType"
$bundleTask   = "bundle$flavorTask$BuildType"

# ---- Compose gradle args ------------------------------------------------
$gradleArgs = @()
if ($SkipTests) { $gradleArgs += "-x", "test" }
if ($Offline)   { $gradleArgs += "--offline" }

# ---- Run unit tests (optional) ------------------------------------------
if (-not $SkipTests) {
    $testArgs = @()
    if ($Offline) { $testArgs += "--offline" }
    Write-Host "==> ./gradlew test" -ForegroundColor Cyan
    & $gradlewCmd -p $ProjectDir test @testArgs
    if ($LASTEXITCODE -ne 0) { throw "gradle test failed." }
}

# ---- Run assemble (APK) ------------------------------------------------
$apkPath = $null
$aabPath = $null

if ($OutputFormat -in "apk", "both") {
    Write-Host "==> ./gradlew $assembleTask" -ForegroundColor Cyan
    & $gradlewCmd -p $ProjectDir $assembleTask @gradleArgs
    if ($LASTEXITCODE -ne 0) { throw "$assembleTask failed." }

    $apkSrc = Get-ChildItem -Recurse "$ProjectDir/build/outputs/apk" -Filter "*.apk" -ErrorAction SilentlyContinue |
              Where-Object { $_.Name -like "*$Flavor*$BuildType*" } |
              Select-Object -First 1
    if ($apkSrc) {
        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        $apkPath = Join-Path $OutputDir $apkSrc.Name
        Copy-Item $apkSrc.FullName $apkPath -Force
        Write-Host "APK: $apkPath" -ForegroundColor Green
    } else {
        throw "No APK artifact found after $assembleTask."
    }
}

# ---- Run bundle (AAB) --------------------------------------------------
if ($OutputFormat -in "aab", "both") {
    Write-Host "==> ./gradlew $bundleTask" -ForegroundColor Cyan
    & $gradlewCmd -p $ProjectDir $bundleTask @gradleArgs
    if ($LASTEXITCODE -ne 0) { throw "$bundleTask failed." }

    $aabSrc = Get-ChildItem -Recurse "$ProjectDir/build/outputs/bundle" -Filter "*.aab" -ErrorAction SilentlyContinue |
              Where-Object { $_.Name -like "*$Flavor*$BuildType*" } |
              Select-Object -First 1
    if ($aabSrc) {
        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        $aabPath = Join-Path $OutputDir $aabSrc.Name
        Copy-Item $aabSrc.FullName $aabPath -Force
        Write-Host "AAB: $aabPath" -ForegroundColor Green
    } else {
        throw "No AAB artifact found after $bundleTask."
    }
}

# ---- Done ---------------------------------------------------------------
Write-Host ""
Write-Host "Done." -ForegroundColor Green
if ($apkPath) {
    Write-Host "  APK: $apkPath"
    Write-Host "  Install: adb install -r $apkPath"
}
if ($aabPath) {
    Write-Host "  AAB: $aabPath"
    Write-Host "  Upload: fastlane supply --aab $aabPath --track production --json_key api-key.json"
}
