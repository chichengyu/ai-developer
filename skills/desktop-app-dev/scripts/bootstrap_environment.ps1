# bootstrap_environment.ps1 -- detect and install the toolchain for a framework.
#
# Usage:
#   powershell -File scripts/bootstrap_environment.ps1 -Framework python -DryRun
#   powershell -File scripts/bootstrap_environment.ps1 -Framework tauri -Install
#   powershell -File scripts/bootstrap_environment.ps1 -Brief brief.json -Install
#
# Auto selection runs scripts/select_framework.py against the brief and
# installs the winning framework's toolchain. Install actions use winget
# and pip, so they need network access and user consent. -DryRun always
# wins over -Install: it only reports what would be installed.

[CmdletBinding()]
param(
    [string] $Framework = "auto",
    [string] $Brief = "",
    [switch] $Install,
    [switch] $DryRun,
    [string[]] $PythonPackages = @()
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $PSScriptRoot "find_python.ps1")
$map = Get-Content -LiteralPath (Join-Path $root "toolchain_map.json") -Raw | ConvertFrom-Json

if ($DryRun -and $Install) {
    Write-Host "Dry run requested: install actions will be skipped." -ForegroundColor Cyan
    $Install = $false
}

function Test-Toolchain {
    param($Toolchain)
    if (-not $Toolchain -or -not $Toolchain.check -or $Toolchain.check.Count -eq 0) {
        return $false
    }
    if ($Toolchain.check[0] -eq "python") {
        return [bool](Get-ProjectPython)
    }
    $cmd = $Toolchain.check[0]
    $cmdArgs = @($Toolchain.check | Select-Object -Skip 1)
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if (-not $found) { return $false }
    try {
        & $found.Source @cmdArgs *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Install-Toolchain {
    param($Toolchain)
    if (-not $Toolchain.winget) {
        Write-Warning "No winget package for $($Toolchain.name); install manually."
        return $false
    }
    Write-Host "==> winget install $($Toolchain.winget)" -ForegroundColor Cyan
    winget install --id $Toolchain.winget --accept-source-agreements --accept-package-agreements
    return $LASTEXITCODE -eq 0
}

if ($Framework -eq "auto") {
    if (-not $Brief) {
        throw "Auto selection requires -Brief <requirements.json|yaml>."
    }
    $py = Get-ProjectPython
    if (-not $py) { throw "python not found; set CODEX_PYTHON or PYTHON, or add python to PATH." }
    $json = & $py (Join-Path $root "select_framework.py") --json $Brief | ConvertFrom-Json
    $Framework = $json.ranked[0].framework
    Write-Host "Auto-selected framework: $Framework" -ForegroundColor Green
}

if (-not $map.framework_toolchains.$Framework) {
    throw "Unknown framework or language: $Framework"
}

$toolchainNames = @($map.framework_toolchains.$Framework)
$missing = @()
$pipFailed = $false
foreach ($name in $toolchainNames) {
    $tc = $map.toolchains.$name
    if (-not $tc) {
        Write-Warning "No toolchain definition for '$name'."
        continue
    }
    if (Test-Toolchain $tc) {
        Write-Host "  [OK] $($tc.name)" -ForegroundColor Green
    } else {
        $missing += $name
        $installHint = if ($tc.winget) { "winget install $($tc.winget)" } else { "manual install" }
        Write-Host "  [MISSING] $($tc.name) -> $installHint" -ForegroundColor Yellow
        if ($Install) {
            $ok = Install-Toolchain $tc
            if ($ok -and (Test-Toolchain $tc)) {
                Write-Host "  [OK after install] $($tc.name)" -ForegroundColor Green
                $missing = @($missing | Where-Object { $_ -ne $name })
            } else {
                Write-Warning "Still missing after install: $($tc.name)"
            }
        }
    }
}

$needPython = $toolchainNames -contains "python"
$allPackages = @()
if ($needPython) { $allPackages += @($map.toolchains.python.packages) }
$allPackages += $PythonPackages
if ($Install -and $allPackages.Count -gt 0 -and (Test-Toolchain $map.toolchains.python)) {
    $py = Get-ProjectPython
    Write-Host "==> pip install $($allPackages -join ' ')" -ForegroundColor Cyan
    & $py -m pip install $allPackages
    if ($LASTEXITCODE -ne 0) {
        $pipFailed = $true
        Write-Warning "pip install failed for: $($allPackages -join ' ')"
    }
}

if ($DryRun) {
    if ($allPackages.Count -gt 0) {
        if (Test-Toolchain $map.toolchains.python) {
            Write-Host "Would run: pip install $($allPackages -join ' ')" -ForegroundColor Cyan
        } else {
            Write-Host "Would need Python first, then run: pip install $($allPackages -join ' ')" -ForegroundColor Yellow
        }
    }
    Write-Host ""
    Write-Host "Dry run finished; no changes were made." -ForegroundColor Cyan
    exit 0
}

if ($missing.Count -gt 0 -or $pipFailed) {
    Write-Host ""
    Write-Host "Environment setup incomplete: missing toolchains ($($missing -join ', ')) or pip install failed. Re-run with -Install." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Environment bootstrap complete." -ForegroundColor Green
exit 0
