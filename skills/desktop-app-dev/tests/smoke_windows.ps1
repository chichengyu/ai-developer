# smoke_windows.ps1 -- runnable smoke test for the Windows-side scripts
# in this skill. Designed for `windows-latest` GitHub Actions runners
# and runnable locally on any Windows host with PowerShell 5+.
#
# Tests:
#   1. PowerShell parse (AST) on every build_*.ps1 + auto_update_*.ps1.
#   2. Python module imports for sendinput_python.py and
#      window_enum_python.py (smoke checks the import path).
#   3. JSON / XML / TOML fixture validity.
#   4. tests/test_arch_awareness.ps1 (the 14-script -Arch / -Rid check).
#   5. Python AST parse for all .py in scripts/.
#   6. SendInput templates: down/up must not be batched into one call.
#
# Exits non-zero on any failure.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$scriptsDir = Join-Path $root "scripts"

$script:passes = 0
$script:failures = 0
$script:failedTests = @()

function Run-Test {
    param([string] $Name, [scriptblock] $Block)
    try {
        if (& $Block) {
            Write-Host "  [OK]   $Name"
            $script:passes++
        } else {
            Write-Host "  [FAIL] $Name" -ForegroundColor Red
            $script:failures++
            $script:failedTests += $Name
        }
    } catch {
        Write-Host "  [FAIL] $Name -- $($_.Exception.Message)" -ForegroundColor Red
        $script:failures++
        $script:failedTests += $Name
    }
}

Write-Host "=== smoke_windows.ps1 ==="
Write-Host "Skill root: $root"
Write-Host ""

# Locate Python (Codex runtime first, then PATH).
$py = $env:CODEX_PYTHON
if (-not $py) { $py = "C:\Users\xc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" }
if (-not (Test-Path $py)) {
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $py) {
    Write-Host "  [WARN] python not found; skipping python-based tests" -ForegroundColor Yellow
}

# 1. PowerShell parse all build_*.ps1 + auto_update_*.ps1
Write-Host "--- powershell parse ---"
Get-ChildItem "$scriptsDir" -Filter "build_*.ps1" | ForEach-Object {
    Run-Test "$($_.Name) parse" {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$errors) | Out-Null
        -not $errors
    }
}
Get-ChildItem "$scriptsDir" -Filter "auto_update_*.ps1" | ForEach-Object {
    Run-Test "$($_.Name) parse" {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$errors) | Out-Null
        -not $errors
    }
}
Get-ChildItem "$scriptsDir" -Filter "sign_*.ps1" | ForEach-Object {
    Run-Test "$($_.Name) parse" {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$errors) | Out-Null
        -not $errors
    }
}
Get-ChildItem "$scriptsDir" -Filter "bootstrap_*.ps1" | ForEach-Object {
    Run-Test "$($_.Name) parse" {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$errors) | Out-Null
        -not $errors
    }
}

# 2. Python import smoke test
Write-Host ""
Write-Host "--- python imports ---"
if ($py) {
    Run-Test "sendinput_python.py VK entries" {
        & $py "$scriptsDir\sendinput_python.py" 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    }
    Run-Test "window_enum_python.py imports" {
        $script = @"
import importlib.util
spec = importlib.util.spec_from_file_location('we', r'$scriptsDir\window_enum_python.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('OK')
"@
        & $py -c $script 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    }
    Run-Test "select_framework.py --self-test" {
        & $py "$scriptsDir\select_framework.py" --self-test 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    }
    Run-Test "check_vk_tables.py" {
        & $py "$scriptsDir\check_vk_tables.py" 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    }
    Run-Test "test_docs.py" {
        & $py "$root\tests\test_docs.py" 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    }
    Run-Test "game-automation example imports" {
        $script = @"
import importlib.util
spec = importlib.util.spec_from_file_location('app', r'$root\examples\game-automation\app\app.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('OK')
"@
        & $py -c $script 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    }
}

# 3. Fixture validity
Write-Host ""
Write-Host "--- fixtures ---"
if ($py) {
    Run-Test "sample_config.json + toolchain_map.json + sample_brief.json" {
        & $py -c "import json; [json.load(open(p, encoding='utf-8')) for p in [r'$root\tests\fixtures\sample_config.json', r'$root\scripts\toolchain_map.json', r'$root\tests\fixtures\sample_brief.json']]"
        $LASTEXITCODE -eq 0
    }
    Run-Test "bootstrap_environment.ps1 dry-run (python)" {
        powershell -ExecutionPolicy Bypass -File "$root\scripts\bootstrap_environment.ps1" -Framework python -DryRun 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    }
    Run-Test "C# template compile (dotnet, skipped if absent)" {
        $dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
        if (-not $dotnet) {
            Write-Host "  [SKIP] dotnet not found"
            $true
        } else {
            & $dotnet.Source build "$root\tests\fixtures\csharp-smoke\CSharpSmoke.csproj" -c Release --nologo 2>&1 | Out-Null
            $LASTEXITCODE -eq 0
        }
    }
    Run-Test "pyproject.toml" {
        & $py -c "import tomllib; tomllib.load(open(r'$root\pyproject.toml','rb'))"
        $LASTEXITCODE -eq 0
    }
    Run-Test "dpi_manifest.xml + AppxManifest.xml" {
        & $py -c "import xml.etree.ElementTree as ET; ET.parse(r'$root\templates\dpi_manifest.xml'); ET.parse(r'$root\tests\fixtures\AppxManifest.xml')"
        $LASTEXITCODE -eq 0
    }
}

# 4. test_arch_awareness.ps1
Write-Host ""
Write-Host "--- arch awareness ---"
$test = Join-Path $root "tests\test_arch_awareness.ps1"
if (Test-Path $test) {
    Run-Test "test_arch_awareness.ps1" {
        powershell -ExecutionPolicy Bypass -File $test 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    }
}

# 5. Python AST parse all .py
Write-Host ""
Write-Host "--- python AST parse all .py ---"
if ($py) {
    Get-ChildItem "$scriptsDir" -Filter "*.py" | ForEach-Object {
        Run-Test "$($_.Name) ast.parse" {
            & $py -c "import ast; ast.parse(open(r'$($_.FullName)', encoding='utf-8').read())"
            $LASTEXITCODE -eq 0
        }
    }
    Get-ChildItem "$root\tests" -Filter "*.py" | ForEach-Object {
        Run-Test "$($_.Name) ast.parse" {
            & $py -c "import ast; ast.parse(open(r'$($_.FullName)', encoding='utf-8').read())"
            $LASTEXITCODE -eq 0
        }
    }
}

# 6. SendInput template semantics (source-level regression guard)
Write-Host ""
Write-Host "--- sendinput template semantics ---"
Run-Test "sendinput templates: down/up not batched" {
    $bad = @()
    Get-ChildItem "$scriptsDir" -Filter "sendinput_*" | ForEach-Object {
        $text = Get-Content $_.FullName -Raw
        if ($text -match 'SendInput\(2\s*,' -or
            $text -match '_pressPair\(' -or
            $text -match '\bpressPair\(' -or
            $text -match 'triggerPair\[' -or
            $text -match 'arrayOf\(press\([^)]*false\)\s*,\s*press\([^)]*true\)' -or
            $text -match 'pressOne\(triggerVk, false\)\s*\r?\n\s*pressOne\(triggerVk, true\)') {
            $bad += $_.Name
        }
    }
    if ($bad.Count -eq 0) { $true } else {
        Write-Host "  Batching in: $($bad -join ', ')"
        $false
    }
}

# Summary
Write-Host ""
Write-Host "=== Summary ==="
Write-Host "  Passed: $($script:passes)"
Write-Host "  Failed: $($script:failures)"
if ($script:failures -gt 0) {
    Write-Host "  Failed tests:"
    foreach ($t in $script:failedTests) { Write-Host "    - $t" }
    exit 1
}
exit 0
