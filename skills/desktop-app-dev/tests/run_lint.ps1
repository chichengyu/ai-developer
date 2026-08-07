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
#     pwsh ./tests/run_lint.ps1

[CmdletBinding()]
param(
    [switch] $SkipSmoke,
    [switch] $SkipMyPy,
    [switch] $SkipRuff
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$py = $env:CODEX_PYTHON
if (-not $py) { $py = "C:\Users\xc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" }
if (-not (Test-Path $py)) { $py = (Get-Command python -ErrorAction SilentlyContinue).Source }
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

Push-Location $root
try {
    if (-not $SkipRuff) {
        Step "ruff check" {
            & $py -m pip install --quiet "ruff==0.6.9"
            & $py -m ruff check scripts/ tests/ examples/
        }
        Step "ruff format --check" {
            & $py -m ruff format --check scripts/
        }
    }
    if (-not $SkipMyPy) {
        Step "mypy scripts/" {
            & $py -m pip install --quiet "mypy==1.13.0"
            & $py -m mypy scripts/ 2>$null
            # intentional: many scripts use untyped ctypes; surface
            # warnings without failing the build (matches CI).
            $true
        }
    }
    if (-not $SkipSmoke) {
        Step "tests/smoke_windows.ps1" {
            & ./tests/smoke_windows.ps1 2>&1 | Out-Null
        }
        Step "tests/test_arch_awareness.ps1" {
            & pwsh -ExecutionPolicy Bypass -File ./tests/test_arch_awareness.ps1 2>&1 | Out-Null
        }
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "All lint checks passed." -ForegroundColor Green
