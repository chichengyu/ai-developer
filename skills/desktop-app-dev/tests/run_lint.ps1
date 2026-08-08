# run_lint.ps1 -- run ruff + mypy + smoke_windows.ps1 locally before
# pushing. Designed for Windows (where the developer typically runs
# pre-commit). On macOS / Linux, the equivalent is:
#
#     pip install ruff mypy
#     ruff check scripts/ tests/ examples/
#     mypy scripts/
#     bash tests/smoke_macos.sh
#
# Usage (Windows):
#     powershell -File tests/run_lint.ps1                  # check-only
#     powershell -File tests/run_lint.ps1 -InstallDeps     # install missing ruff/mypy

[CmdletBinding()]
param(
    [switch] $SkipSmoke,
    [switch] $SkipMyPy,
    [switch] $SkipRuff,
    [switch] $InstallDeps
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
. (Join-Path $root "scripts/find_python.ps1")
$py = Get-ProjectPython
if (-not $py) { Write-Host "python not found" -ForegroundColor Red; exit 1 }

function Step($name, $block) {
    Write-Host "==> $name" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] $name" -ForegroundColor Red
        exit 1
    }
    Write-Host "  [OK]   $name" -ForegroundColor Green
}

function Get-DevRequirement {
    param([string] $Module)
    $spec = Get-Content (Join-Path $root "requirements-dev.txt") |
        Where-Object { $_ -and $_.Trim() -like "$Module*" } |
        Select-Object -First 1
    if (-not $spec) {
        throw "requirements-dev.txt missing entry for $Module"
    }
    $spec.Trim()
}

function Ensure-Tool {
    param([string] $Module, [string] $Spec)
    $expectedMatch = [regex]::Match($Spec, "==(.+)$")
    $expected = if ($expectedMatch.Success) { $expectedMatch.Groups[1].Value.Trim() } else { $null }
    $pipShow = & $py -m pip show $Module 2>&1 | Out-String
    $versionMatch = [regex]::Match($pipShow, "(?m)^Version:\s*(\S+)")
    $ok = $versionMatch.Success -and (-not $expected -or $versionMatch.Groups[1].Value -eq $expected)
    if (-not $ok) {
        if (-not $InstallDeps) {
            Write-Host "  [MISSING] $Spec. Re-run with -InstallDeps or run: & `"$py`" -m pip install `"$Spec`"" -ForegroundColor Yellow
            exit 1
        }
        & $py -m pip install --quiet "$Spec"
        if ($LASTEXITCODE -ne 0) { throw "pip install failed for $Spec" }
    }
}

Push-Location $root
try {
    $psShell = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
    if (-not $psShell) { $psShell = (Get-Command powershell -ErrorAction SilentlyContinue).Source }
    if (-not $psShell) { throw "PowerShell not found for tests/test_arch_awareness.ps1" }
    if (-not $SkipRuff) {
        Ensure-Tool "ruff" (Get-DevRequirement "ruff")
        Step "ruff check" {
            & $py -m ruff check scripts/ tests/ examples/
        }
        Step "ruff format --check" {
            & $py -m ruff format --check scripts/ tests/ examples/
        }
    }
    if (-not $SkipMyPy) {
        Ensure-Tool "mypy" (Get-DevRequirement "mypy")
        Ensure-Tool "types-requests" (Get-DevRequirement "types-requests")
        Step "mypy scripts/" {
            & $py -m mypy scripts/
        }
    }
    if (-not $SkipSmoke) {
        Step "tests/smoke_windows.ps1" {
            & ./tests/smoke_windows.ps1 2>&1 | Out-Null
        }
        Step "tests/test_arch_awareness.ps1" {
            & $psShell -NoProfile -ExecutionPolicy Bypass -File ./tests/test_arch_awareness.ps1 2>&1 | Out-Null
        }
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "All lint checks passed." -ForegroundColor Green
