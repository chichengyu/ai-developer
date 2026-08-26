<#
.SYNOPSIS
    Set up iOS code signing via Fastlane match.

.DESCRIPTION
    Interactively creates development, ad-hoc, and App Store
    certificates and provisioning profiles, stored in a git repo
    configured by -GitUrl or an existing Matchfile. Run once per
    developer machine; CI uses the same cert repo.

.PARAMETER GitUrl
    Git URL of the cert repo (e.g., git@github.com:org/certs.git).
    Optional if a Matchfile already exists.

.PARAMETER Readonly
    Skip certificate creation; only fetch existing certs.

.EXAMPLE
    pwsh setup_ios_signing.ps1 -GitUrl "git@github.com:acme/certs.git"

.EXAMPLE
    pwsh setup_ios_signing.ps1 -Readonly
#>

[CmdletBinding()]
param(
    [string] $GitUrl,
    [switch] $Readonly
)

$ErrorActionPreference = "Stop"

if ($IsWindows -or $IsLinux) {
    throw "setup_ios_signing.ps1 requires macOS. Detected host: $($PSVersionTable.OS)."
}

if (-not (Get-Command fastlane -ErrorAction SilentlyContinue)) {
    throw "fastlane not installed. Install with 'brew install fastlane'."
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git not installed. Install Xcode CLT or 'brew install git'."
}

# ---- Init match repo ----------------------------------------------------
if (-not $Readonly -and $GitUrl) {
    Write-Host "==> fastlane match init" -ForegroundColor Cyan
    & fastlane match init --git_url $GitUrl
    if ($LASTEXITCODE -ne 0) { throw "fastlane match init failed." }
}
if ($Readonly -and -not $GitUrl) {
    if (-not (Test-Path "Matchfile")) {
        throw "Readonly mode requires -GitUrl or an existing Matchfile."
    }
}
if (-not $GitUrl -and -not (Test-Path "Matchfile")) {
    throw "Pass -GitUrl (or create a Matchfile) before running match."
}

# ---- Match per cert type ------------------------------------------------
$types = @("development", "adhoc", "appstore")

foreach ($type in $types) {
    Write-Host "==> fastlane match $type" -ForegroundColor Cyan
    $matchArgs = @("match", $type)
    if ($Readonly) { $matchArgs += "--readonly" }
    if ($GitUrl)  { $matchArgs += "--git_url", $GitUrl }
    & fastlane @matchArgs
    if ($LASTEXITCODE -ne 0) { Write-Warning "fastlane match $type failed; continue." }
}

# ---- Output -------------------------------------------------------------
Write-Host ""
Write-Host "Done. Certificates and profiles are installed." -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  - Open Xcode and let it auto-sign, OR"
Write-Host "  - Run: xcodebuild -resolvePackageDependencies"
Write-Host "  - For CI: secrets needed are MATCH_PASSWORD, MATCH_GIT_BASIC_AUTHORIZATION"
