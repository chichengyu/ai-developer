<#
.SYNOPSIS
    Build a Capacitor app for iOS and/or Android.

.DESCRIPTION
    Runs npm install, capacitor sync, then the native Xcode/Gradle build.

.PARAMETER Platform
    ios, android, or both. Default both.

.PARAMETER Configuration
    Debug or Release. Default Release.

.PARAMETER ProjectDir
    Capacitor project root. Defaults to the current directory.

.PARAMETER OutputDir
    Where produced artifacts are copied. Defaults to ./build/capacitor.

.PARAMETER SkipTests
    Skip npm test.

.EXAMPLE
    pwsh build_capacitor.ps1 -Platform android -Configuration Release
#>

[CmdletBinding()]
param(
    [ValidateSet("ios", "android", "both")]
    [string] $Platform = "both",
    [ValidateSet("Debug", "Release")]
    [string] $Configuration = "Release",
    [string] $ProjectDir = ".",
    [string] $OutputDir = "./build/capacitor",
    [switch] $SkipTests
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm not on PATH. Install Node.js first."
}
if (-not (Test-Path (Join-Path $ProjectDir "package.json"))) {
    throw "package.json not found in $ProjectDir."
}

Push-Location $ProjectDir
try {
    Write-Host "==> npm ci" -ForegroundColor Cyan
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }

    if (-not $SkipTests) {
        Write-Host "==> npm test" -ForegroundColor Cyan
        & npm test -- --watchAll=false
        if ($LASTEXITCODE -ne 0) { throw "npm test failed." }
    }

    Write-Host "==> npx cap sync" -ForegroundColor Cyan
    & npx cap sync
    if ($LASTEXITCODE -ne 0) { throw "npx cap sync failed." }
}
finally {
    Pop-Location
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

if ($Platform -in "ios", "both") {
    if ($IsWindows -or $IsLinux) {
        throw "Capacitor iOS build requires macOS."
    }
    $workspace = Join-Path $ProjectDir "ios/App/App.xcworkspace"
    if (-not (Test-Path $workspace)) {
        throw "Workspace not found: $workspace. Run 'npx cap add ios' first."
    }
    Write-Host "==> xcodebuild archive (Capacitor iOS)" -ForegroundColor Cyan
    & xcodebuild -workspace $workspace `
        -scheme App `
        -configuration $Configuration `
        -destination "generic/platform=iOS" `
        -archivePath (Join-Path $OutputDir "App.xcarchive") `
        archive
    if ($LASTEXITCODE -ne 0) { throw "xcodebuild archive failed." }
}

if ($Platform -in "android", "both") {
    $androidDir = Join-Path $ProjectDir "android"
    if (-not (Test-Path $androidDir)) {
        throw "Android project not found: $androidDir. Run 'npx cap add android' first."
    }
    $gradlew = Join-Path $androidDir "gradlew.bat"
    if (-not (Test-Path $gradlew)) {
        $gradlew = Join-Path $androidDir "gradlew"
    }
    Write-Host "==> gradle assembleRelease (Capacitor Android)" -ForegroundColor Cyan
    & $gradlew -p $androidDir ":app:assemble$($Configuration)"
    if ($LASTEXITCODE -ne 0) { throw "Capacitor Android build failed." }

    $apk = Get-ChildItem -Recurse (Join-Path $androidDir "app/build/outputs/apk") -Filter "*.apk" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($apk) {
        Copy-Item $apk.FullName (Join-Path $OutputDir $apk.Name) -Force
        Write-Host "APK: $OutputDir/$($apk.Name)" -ForegroundColor Green
    }
}
