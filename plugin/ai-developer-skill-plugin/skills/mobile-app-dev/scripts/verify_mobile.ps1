<#
.SYNOPSIS
    Run framework smoke checks and write a verification report.

.DESCRIPTION
    Runs the unit/test pass and basic static checks for the selected
    mobile framework, then writes verification_report.md into OutputDir.

.PARAMETER Framework
    flutter, react-native, compose, swiftui, maui, kmp, capacitor, or tauri.

.PARAMETER ProjectDir
    Project root. Defaults to the current directory.

.PARAMETER OutputDir
    Where verification_report.md is written. Defaults to ./build/verification.

.PARAMETER SkipTests
    Skip the framework test command.

.EXAMPLE
    pwsh verify_mobile.ps1 -Framework flutter -ProjectDir ./my_app
#>

[CmdletBinding()]
param(
    [ValidateSet("flutter", "react-native", "compose", "swiftui", "maui", "kmp", "capacitor", "tauri")]
    [string] $Framework,
    [string] $ProjectDir = ".",
    [string] $OutputDir = "./build/verification",
    [switch] $SkipTests
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ProjectDir)) {
    throw "ProjectDir not found: $ProjectDir"
}

$report = [System.Collections.Generic.List[string]]::new()
$failed = $false

function Add-Check {
    param([string] $Name, [bool] $Pass)
    $script:report.Add(("  [{0}] {1}" -f ($(if ($Pass) { "PASS" } else { "FAIL" })), $Name))
    if (-not $Pass) {
        $script:failed = $true
    }
}

function Invoke-Check {
    param([string] $Name, [scriptblock] $Body)
    try {
        & $Body
        Add-Check $Name ($LASTEXITCODE -eq 0)
    } catch {
        Add-Check "$Name ($($_.Exception.Message))" $false
    }
}

$report.Add("# Verification report")
$report.Add("")
$report.Add("- Framework: $Framework")
$report.Add("- Project: $ProjectDir")
$report.Add("- Date: $(Get-Date -Format o)")
$report.Add("")

switch ($Framework) {
    "flutter" {
        Invoke-Check "flutter analyze" { & flutter analyze }
        if (-not $SkipTests) {
            Invoke-Check "flutter test" { & flutter test }
        }
    }
    "react-native" {
        if (Test-Path (Join-Path $ProjectDir "tsconfig.json")) {
            Invoke-Check "tsc --noEmit" { & npx tsc --noEmit }
        }
        if (-not $SkipTests) {
            Invoke-Check "npm test" { & npm test -- --watchAll=false }
        }
    }
    "compose" {
        $gradlew = Join-Path $ProjectDir "gradlew.bat"
        if (-not (Test-Path $gradlew)) {
            $gradlew = Join-Path $ProjectDir "gradlew"
        }
        if (Test-Path $gradlew) {
            Invoke-Check "gradle test" { & $gradlew -p $ProjectDir test }
        } else {
            Add-Check "gradle test (wrapper missing)" $false
        }
    }
    "swiftui" {
        $project = Get-ChildItem -Path $ProjectDir -Filter "*.xcodeproj" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($project) {
            Invoke-Check "xcodebuild -list" { & xcodebuild -project $project.FullName -list }
        } else {
            Add-Check "xcodebuild -list (project missing)" $false
        }
    }
    "maui" {
        $csproj = Get-ChildItem -Path $ProjectDir -Filter "*.csproj" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($csproj) {
            Invoke-Check "dotnet test" { & dotnet test $csproj.FullName }
        } else {
            Add-Check "dotnet test (csproj missing)" $false
        }
    }
    "kmp" {
        $gradlew = Join-Path $ProjectDir "gradlew.bat"
        if (-not (Test-Path $gradlew)) {
            $gradlew = Join-Path $ProjectDir "gradlew"
        }
        if (Test-Path $gradlew) {
            Invoke-Check "gradle allTests" { & $gradlew -p $ProjectDir :shared:allTests }
        } else {
            Add-Check "gradle allTests (wrapper missing)" $false
        }
    }
    "capacitor" {
        if (Test-Path (Join-Path $ProjectDir "capacitor.config.json")) {
            Invoke-Check "cap sync" { & npx cap sync }
        } else {
            Add-Check "cap sync (config missing)" $false
        }
    }
    "tauri" {
        if (Test-Path (Join-Path $ProjectDir "src-tauri")) {
            Invoke-Check "cargo check" { & cargo check --manifest-path (Join-Path $ProjectDir "src-tauri/Cargo.toml") }
        } else {
            Add-Check "cargo check (src-tauri missing)" $false
        }
    }
}

$template = Join-Path $PSScriptRoot "..\templates\verification_report.md"
if (Test-Path $template) {
    $report.Add("")
    $report.Add("## Step 5 checklist")
    $report.Add((Get-Content -Raw $template))
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$reportPath = Join-Path $OutputDir "verification_report.md"
[System.IO.File]::WriteAllText($reportPath, ($report -join "`n"), [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote $reportPath" -ForegroundColor Green

if ($failed) {
    exit 1
}
