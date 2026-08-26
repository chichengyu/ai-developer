<#
.SYNOPSIS
    Build a Tauri Mobile app.

.DESCRIPTION
    Runs npm install and the Tauri CLI mobile build for the selected
    platform. Requires Rust, Tauri CLI, and the platform toolchain.

.PARAMETER Platform
    ios, android, or both. Default both.

.PARAMETER ProjectDir
    Tauri project root. Defaults to the current directory.

.PARAMETER OutputDir
    Where build output is reported. Defaults to ./build/tauri.

.PARAMETER SkipTests
    Skip npm test.

.EXAMPLE
    pwsh build_tauri_mobile.ps1 -Platform android
#>

[CmdletBinding()]
param(
    [ValidateSet("ios", "android", "both")]
    [string] $Platform = "both",
    [string] $ProjectDir = ".",
    [string] $OutputDir = "./build/tauri",
    [switch] $SkipTests
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm not on PATH. Install Node.js first."
}
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "cargo not on PATH. Install Rust first."
}
if (-not (Test-Path (Join-Path $ProjectDir "src-tauri"))) {
    throw "src-tauri not found in $ProjectDir."
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
}
finally {
    Pop-Location
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

if ($Platform -in "ios", "both") {
    if ($IsWindows -or $IsLinux) {
        throw "Tauri iOS build requires macOS."
    }
    Write-Host "==> npx tauri ios build" -ForegroundColor Cyan
    Push-Location $ProjectDir
    try {
        & npx tauri ios build
    }
    finally {
        Pop-Location
    }
    if ($LASTEXITCODE -ne 0) { throw "tauri ios build failed." }
}

if ($Platform -in "android", "both") {
    Write-Host "==> npx tauri android build" -ForegroundColor Cyan
    Push-Location $ProjectDir
    try {
        & npx tauri android build
    }
    finally {
        Pop-Location
    }
    if ($LASTEXITCODE -ne 0) { throw "tauri android build failed." }
}

Write-Host "Tauri mobile build output: $OutputDir" -ForegroundColor Green
