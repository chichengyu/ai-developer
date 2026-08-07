<#
.SYNOPSIS
    Build an iOS / iPadOS / watchOS / visionOS app via xcodebuild.

.DESCRIPTION
    Cleans, archives, and exports an iOS app to an IPA. Supports any
    Xcode project / workspace / scheme.

    Requires macOS + Xcode 15+. Will refuse to run on Windows / Linux.

.PARAMETER Workspace
    Xcode workspace (.xcworkspace) to build. Required for CocoaPods / SPM
    projects. If both Workspace and Project are passed, Workspace wins.

.PARAMETER Project
    Xcode project (.xcodeproj) to build. Used for non-CocoaPods projects.

.PARAMETER Scheme
    Build scheme. Defaults to the only scheme if the project has one.

.PARAMETER Configuration
    Debug or Release. Default Release.

.PARAMETER Arch
    arm64 (device) or x86_64 (simulator on Intel Mac). Default arm64.

.PARAMETER Destination
    Optional xcodebuild destination string. Defaults to a generic
    platform-specific destination matching Arch.

.PARAMETER OutputDir
    Output directory for the .xcarchive and exported .ipa. Defaults
    to ./build.

.PARAMETER ExportOptionsPlist
    Path to an ExportOptions.plist. Defaults to ./ExportOptions.plist.

.PARAMETER SkipArchive
    Skip archive + export; only run a build (useful for smoke tests).

.PARAMETER SkipTests
    Skip xcodebuild build-for-testing (smoke). Default false.

.PARAMETER Verbose
    Print every xcodebuild command verbatim.

.EXAMPLE
    pwsh build_swift_ios.ps1 `
        -Workspace MyApp.xcworkspace `
        -Scheme MyApp `
        -Configuration Release `
        -Arch arm64

.EXAMPLE
    pwsh build_swift_ios.ps1 `
        -Project MyApp.xcodeproj `
        -Scheme MyApp `
        -SkipArchive -SkipTests `
        -Destination 'platform=iOS Simulator,name=iPhone 14'

.NOTES
    Host requirement: macOS only.
#>

[CmdletBinding()]
param(
    [string] $Workspace,
    [string] $Project,
    [string] $Scheme,
    [ValidateSet("Debug", "Release")]
    [string] $Configuration = "Release",
    [ValidateSet("arm64", "x86_64")]
    [string] $Arch = "arm64",
    [string] $Destination,
    [string] $OutputDir = "./build",
    [string] $ExportOptionsPlist = "./ExportOptions.plist",
    [switch] $SkipArchive,
    [switch] $SkipTests,
    [switch] $VerboseXcodebuild
)

$ErrorActionPreference = "Stop"

function Invoke-Xcodebuild {
    param([string[]] $Arguments)
    if ($VerboseXcodebuild) {
        Write-Host "xcodebuild $($Arguments -join ' ')" -ForegroundColor Magenta
    }
    & xcodebuild @Arguments
}

# ---- Guard: macOS only --------------------------------------------------
if ($IsWindows -or $IsLinux) {
    throw "build_swift_ios.ps1 requires macOS. Detected host: $($PSVersionTable.OS)."
}
if (-not (Get-Command xcodebuild -ErrorAction SilentlyContinue)) {
    throw "xcodebuild not on PATH. Install Xcode 15+ and run from a Terminal session with developer tools selected."
}

# ---- Validate project inputs --------------------------------------------
if (-not $Workspace -and -not $Project) {
    throw "Pass either -Workspace or -Project."
}
if (-not $Scheme) {
    throw "Pass -Scheme (e.g., MyApp)."
}

# ---- Resolve destination ------------------------------------------------
if (-not $Destination) {
    if ($Arch -eq "arm64") {
        $Destination = "generic/platform=iOS"
    } else {
        $Destination = "generic/platform=iOS Simulator"
    }
}
if ($Destination -match "Simulator" -and -not $SkipArchive) {
    throw "xcodebuild archive requires a device destination; pass -SkipArchive for simulator builds."
}

# ---- Resolve build target -----------------------------------------------
$buildTarget = if ($Workspace) { "-workspace" } else { "-project" }
$buildArg    = if ($Workspace) { $Workspace } else { $Project }

# ---- Ensure output dir --------------------------------------------------
$archiveRoot = Join-Path $OutputDir "archives"
$ipaRoot     = Join-Path $OutputDir "ipa"
New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ipaRoot | Out-Null

$archiveName = "$Scheme-$Configuration-$Arch-$(Get-Date -Format yyyyMMdd-HHmmss).xcarchive"
$archivePath = Join-Path $archiveRoot $archiveName

# ---- Clean --------------------------------------------------------------
Write-Host "==> xcodebuild clean" -ForegroundColor Cyan
$cleanArgs = @($buildTarget, $buildArg, "-scheme", $Scheme, "-configuration", $Configuration, "clean")
Invoke-Xcodebuild -Arguments $cleanArgs | Out-Null
if ($LASTEXITCODE -ne 0) { throw "xcodebuild clean failed." }

# ---- Tests (optional) ---------------------------------------------------
if (-not $SkipTests) {
    Write-Host "==> xcodebuild build-for-testing" -ForegroundColor Cyan
    $testArgs = @(
        $buildTarget, $buildArg,
        "-scheme", $Scheme,
        "-configuration", $Configuration,
        "-destination", $Destination,
        "build-for-testing"
    )
    Invoke-Xcodebuild -Arguments $testArgs
    if ($LASTEXITCODE -ne 0) { throw "xcodebuild build-for-testing failed." }
} else {
    Write-Host "==> xcodebuild build (skipping tests)" -ForegroundColor Cyan
    $buildArgs = @(
        $buildTarget, $buildArg,
        "-scheme", $Scheme,
        "-configuration", $Configuration,
        "-destination", $Destination,
        "-derivedDataPath", "$OutputDir/DerivedData",
        "build"
    )
    Invoke-Xcodebuild -Arguments $buildArgs
    if ($LASTEXITCODE -ne 0) { throw "xcodebuild build failed." }
}

# ---- Archive + export ---------------------------------------------------
if (-not $SkipArchive) {
    Write-Host "==> xcodebuild archive -> $archivePath" -ForegroundColor Cyan
    $archiveArgs = @(
        $buildTarget, $buildArg,
        "-scheme", $Scheme,
        "-configuration", $Configuration,
        "-destination", $Destination,
        "-archivePath", $archivePath,
        "archive"
    )
    Invoke-Xcodebuild -Arguments $archiveArgs
    if ($LASTEXITCODE -ne 0) { throw "xcodebuild archive failed." }

    if (-not (Test-Path $ExportOptionsPlist)) {
        throw "ExportOptions.plist not found at $ExportOptionsPlist. Create one (see references/distribution_playbook.md)."
    }

    Write-Host "==> xcodebuild -exportArchive" -ForegroundColor Cyan
    $exportArgs = @(
        "-exportArchive",
        "-archivePath", $archivePath,
        "-exportPath", $ipaRoot,
        "-exportOptionsPlist", $ExportOptionsPlist
    )
    Invoke-Xcodebuild -Arguments $exportArgs
    if ($LASTEXITCODE -ne 0) { throw "xcodebuild -exportArchive failed." }
}

# ---- Done ---------------------------------------------------------------
Write-Host ""
Write-Host "Build artifacts:" -ForegroundColor Green
if (-not $SkipArchive) {
    Write-Host "  $archivePath"
    Get-ChildItem $ipaRoot -Filter "*.ipa" | ForEach-Object { Write-Host "  $($_.FullName)" }
}
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  - Upload to TestFlight: fastlane pilot upload --ipa $ipaRoot/*.ipa"
Write-Host "  - Upload to App Store:  fastlane deliver"
Write-Host "  - Local install:        xcrun simctl install booted $ipaRoot/*.app"
