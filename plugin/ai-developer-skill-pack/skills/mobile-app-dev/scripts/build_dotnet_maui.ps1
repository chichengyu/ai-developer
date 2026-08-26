<#
.SYNOPSIS
    Build a .NET MAUI app for iOS and/or Android.

.DESCRIPTION
    Runs `dotnet publish` with the matching target framework moniker.
    For iOS, runs on macOS; for Android, runs anywhere with Android SDK.

.PARAMETER Platform
    ios, android, or both. Default both.

.PARAMETER Configuration
    Debug or Release. Default Release.

.PARAMETER TargetFramework
    Target framework moniker (e.g., net8.0-ios, net8.0-android).
    Default is selected based on Platform.

.PARAMETER ProjectDir
    Directory containing the MAUI .csproj. Defaults to ./src/MyApp.

.PARAMETER OutputDir
    Output directory. Defaults to ./build/maui.

.PARAMETER SkipTests
    Skip `dotnet test`.

.EXAMPLE
    pwsh build_dotnet_maui.ps1 -Platform ios

.EXAMPLE
    pwsh build_dotnet_maui.ps1 -Platform android -SkipTests
#>

[CmdletBinding()]
param(
    [ValidateSet("ios", "android", "both")]
    [string] $Platform = "both",
    [ValidateSet("Debug", "Release")]
    [string] $Configuration = "Release",
    [string] $TargetFramework,
    [string] $ProjectDir = "./src/MyApp",
    [string] $OutputDir = "./build/maui",
    [switch] $SkipTests
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw "dotnet SDK not on PATH. Install .NET 8+ SDK + MAUI workload."
}

$projectFile = Get-ChildItem -Path $ProjectDir -Filter "*.csproj" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $projectFile) {
    throw "No .csproj file found in $ProjectDir."
}

# ---- Tests --------------------------------------------------------------
if (-not $SkipTests) {
    Write-Host "==> dotnet test" -ForegroundColor Cyan
    & dotnet test $projectFile.FullName --configuration $Configuration
    if ($LASTEXITCODE -ne 0) { throw "dotnet test failed." }
}

# ---- iOS ----------------------------------------------------------------
$ipaPath = $null
$aabPath = $null

if ($Platform -in "ios", "both") {
    if ($IsWindows -or $IsLinux) {
        throw "Building MAUI for iOS requires macOS. Detected host: $($PSVersionTable.OS)."
    }
    $tfm = if ($TargetFramework) { $TargetFramework } else { "net8.0-ios" }
    Write-Host "==> dotnet publish -f $tfm -c $Configuration" -ForegroundColor Cyan
    & dotnet publish $projectFile.FullName -f $tfm -c $Configuration -p:RuntimeIdentifier=ios-arm64
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish ($tfm) failed." }

    $src = Get-ChildItem -Recurse "$ProjectDir/bin/$Configuration/$tfm/ios-arm64/publish" -Filter "*.app" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($src) {
        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        $dst = Join-Path $OutputDir $src.Name
        Copy-Item $src.FullName $dst -Recurse -Force
        Write-Host "App bundle: $dst" -ForegroundColor Green
        $ipaPath = $dst
    }
}

# ---- Android ------------------------------------------------------------
if ($Platform -in "android", "both") {
    $tfm = if ($TargetFramework) { $TargetFramework } else { "net8.0-android" }
    Write-Host "==> dotnet publish -f $tfm -c $Configuration" -ForegroundColor Cyan
    & dotnet publish $projectFile.FullName -f $tfm -c $Configuration -p:RuntimeIdentifier=android-arm64
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish ($tfm) failed." }

    $src = Get-ChildItem -Recurse "$ProjectDir/bin/$Configuration/$tfm/android-arm64/publish" -Filter "*-Signed.apk" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $src) {
        $src = Get-ChildItem -Recurse "$ProjectDir/bin/$Configuration/$tfm/android-arm64/publish" -Filter "*.apk" -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if ($src) {
        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        $aabPath = Join-Path $OutputDir $src.Name
        Copy-Item $src.FullName $aabPath -Force
        Write-Host "APK: $aabPath" -ForegroundColor Green
    }
}

# ---- Done ---------------------------------------------------------------
Write-Host ""
Write-Host "Done." -ForegroundColor Green
if ($ipaPath) { Write-Host "  App bundle: $ipaPath" }
if ($aabPath) { Write-Host "  APK: $aabPath" }
