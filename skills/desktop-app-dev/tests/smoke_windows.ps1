# smoke_windows.ps1 -- runnable smoke test for the Windows-side scripts
# in this skill. Designed for `windows-latest` GitHub Actions runners
# and runnable locally on any Windows host with PowerShell 5+.
#
# Tests:
#   1. PowerShell parse (AST) on every .ps1 in the skill.
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
. (Join-Path $scriptsDir "find_python.ps1")

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

# Locate Python using the shared resolver (CODEX_PYTHON -> PYTHON -> Codex runtime -> PATH).
$py = Get-ProjectPython
if (-not $py) {
    Write-Host "  [WARN] python not found; skipping python-based tests" -ForegroundColor Yellow
}

# 1. PowerShell parse every .ps1 in the skill (scripts, tests, examples)
Write-Host "--- powershell parse ---"
Get-ChildItem $root -Recurse -Filter "*.ps1" | ForEach-Object {
    Run-Test "$($_.FullName.Substring($root.Length + 1)) parse" {
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
    Run-Test "test_media_pipeline.py" {
        $previous = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $py "$root\tests\test_media_pipeline.py" 2>&1 | Out-Null
        $code = $LASTEXITCODE
        $ErrorActionPreference = $previous
        $code -eq 0
    }
    Run-Test "test_no_bom.py" {
        & $py "$root\tests\test_no_bom.py" 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    }
    Run-Test "test_threading_templates.py" {
        & $py "$root\tests\test_threading_templates.py" 2>&1 | Out-Null
        $LASTEXITCODE -eq 0
    }
    Run-Test "test_threading_concurrency.py" {
        & $py "$root\tests\test_threading_concurrency.py" 2>&1 | Out-Null
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

# 2.5 Shared Python resolver regression
if ($py) {
    Write-Host ""
    Write-Host "--- shared python resolver ---"
    Run-Test "find_python.ps1 resolves an interpreter" {
        $resolved = Get-ProjectPython
        [bool]$resolved -and (Test-Path -LiteralPath $resolved)
    }
    Run-Test "find_python.ps1 honors PYTHON env" {
        $real = Get-ProjectPython
        if (-not $real) { $false } else {
            $oldCodex = $env:CODEX_PYTHON
            $oldPython = $env:PYTHON
            $env:CODEX_PYTHON = Join-Path $env:TEMP "missing-codex-python.exe"
            $env:PYTHON = $real
            try {
                (Get-ProjectPython) -eq $real
            } finally {
                $env:CODEX_PYTHON = $oldCodex
                $env:PYTHON = $oldPython
            }
        }
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
    Run-Test "bootstrap_environment.ps1 dry-run wins over -Install" {
        $out = powershell -ExecutionPolicy Bypass -File "$root\scripts\bootstrap_environment.ps1" `
            -Framework python -DryRun -Install -PythonPackages "__never_installed__" 2>&1
        $exit = $LASTEXITCODE
        $text = $out -join "`n"
        $exit -eq 0 -and $text -match "Dry run finished" -and
        $text -notmatch "==> pip install" -and
        $text -notmatch "==> winget install"
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

# 3.5 Source preservation
Write-Host ""
Write-Host "--- source preservation ---"
Run-Test "backup_source.ps1 zips fixtures" {
    $tmp = Join-Path $env:TEMP ("backup-test-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $backupDir = Join-Path $tmp "out"
        powershell -ExecutionPolicy Bypass -File (Join-Path $scriptsDir "backup_source.ps1") `
            -SourcePath (Join-Path $root "tests\fixtures") `
            -OutputDir $backupDir `
            -Name fixtures 2>&1 | Out-Null
        $exit = $LASTEXITCODE
        $zip = Get-ChildItem $backupDir -Filter "fixtures_source_*.zip" -ErrorAction SilentlyContinue |
               Select-Object -First 1
        if ($exit -ne 0 -or -not $zip -or $zip.Length -eq 0) { $false } else { $true }
    } finally {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
    }
}
Run-Test "backup_source.ps1 excludes exact segment names only" {
    $tmp = Join-Path $env:TEMP ("backup-seg-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path (Join-Path $tmp "src\build") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $tmp "src\mybuild") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $tmp "out") -Force | Out-Null
    try {
        Set-Content -LiteralPath (Join-Path $tmp "src\keep.txt") -Value "keep" -NoNewline
        Set-Content -LiteralPath (Join-Path $tmp "src\build\exclude.txt") -Value "exclude" -NoNewline
        Set-Content -LiteralPath (Join-Path $tmp "src\mybuild\keep.txt") -Value "keep2" -NoNewline
        powershell -ExecutionPolicy Bypass -File (Join-Path $scriptsDir "backup_source.ps1") `
            -SourcePath (Join-Path $tmp "src") `
            -OutputDir (Join-Path $tmp "out") `
            -Name segtest 2>&1 | Out-Null
        $exit = $LASTEXITCODE
        $zip = Get-ChildItem (Join-Path $tmp "out") -Filter "segtest_source_*.zip" -ErrorAction SilentlyContinue |
               Select-Object -First 1
        $foundKeep = $false
        $foundBuild = $false
        if ($exit -eq 0 -and $zip) {
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $archive = [System.IO.Compression.ZipFile]::OpenRead($zip.FullName)
            try {
                $names = @($archive.Entries | ForEach-Object { $_.FullName })
                $foundKeep = [bool]($names | Where-Object { $_ -match 'mybuild[/\\]keep\.txt$' })
                $foundBuild = [bool]($names | Where-Object { $_ -match 'build[/\\]exclude\.txt$' })
            } finally {
                $archive.Dispose()
            }
        }
        if ($exit -ne 0 -or -not $zip -or -not $foundKeep -or $foundBuild) { $false } else { $true }
    } finally {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
    }
}
Run-Test "all build_*.ps1 support -BackupSource" {
    $missing = Get-ChildItem "$scriptsDir" -Filter "build_*.ps1" | Where-Object {
        $text = Get-Content $_.FullName -Raw
        $text -notmatch '\[switch\] \$BackupSource' -or $text -notmatch 'backup_source\.ps1'
    }
    $missing.Count -eq 0
}
Run-Test "build_qt.ps1 refuses staging removal over source" {
    $text = Get-Content (Join-Path $scriptsDir "build_qt.ps1") -Raw
    $text -match 'Refusing to remove'
}

# 3.6 Packaging optimization defaults (single-file / no runtime / size / RAM)
Write-Host ""
Write-Host "--- packaging optimization ---"
Run-Test "build_python.ps1 onefile + size defaults" {
    $text = Get-Content (Join-Path $scriptsDir "build_python.ps1") -Raw
    $text -match '"--onefile"' -and $text -match '"--windowed"' -and
    $text -match '--noupx' -and $text -match '--exclude-module' -and
    $text -match 'Built:'
}
Run-Test "build_dotnet.ps1 size defaults + R2R opt-in" {
    $text = Get-Content (Join-Path $scriptsDir "build_dotnet.ps1") -Raw
    $text -match 'EnableCompressionInSingleFile' -and $text -match 'DebugType=None' -and
    $text -match 'InvariantGlobalization' -and $text -match 'if \(\$ReadyToRun\)'
}
Run-Test "build_dotnet_nativeaot.ps1 size + invariant globalization" {
    $text = Get-Content (Join-Path $scriptsDir "build_dotnet_nativeaot.ps1") -Raw
    $text -match 'IlcOptimizationPreference=Size' -and $text -match 'InvariantGlobalization' -and
    $text -match 'DebugType=None'
}
Run-Test "build_qt.ps1 minimal deploy flags" {
    $text = Get-Content (Join-Path $scriptsDir "build_qt.ps1") -Raw
    $text -match '--no-translations' -and $text -match '--no-compiler-runtime' -and
    $text -match 'Portable folder size'
}
Run-Test "build_tauri.ps1 nsis default + size profile" {
    $text = Get-Content (Join-Path $scriptsDir "build_tauri.ps1") -Raw
    $text -match 'Targets = @\("nsis"\)' -and $text -match 'CARGO_PROFILE_RELEASE_OPT_LEVEL' -and
    $text -match 'Artifact:'
}
Run-Test "build_electron.ps1 compression + asar + warning" {
    $text = Get-Content (Join-Path $scriptsDir "build_electron.ps1") -Raw
    $text -match '-c.compression=maximum' -and $text -match '-c.asar=true' -and
    $text -match 'prefer Tauri'
}
Run-Test "build_go_wails.ps1 strip/trimpath defaults" {
    $text = Get-Content (Join-Path $scriptsDir "build_go_wails.ps1") -Raw
    $text -match '\$Ldflags = "-s -w"' -and $text -match '\$Trimpath = \$true' -and
    $text -match '-trimpath'
}
Run-Test "build_go_fyne.ps1 strip/no-console defaults" {
    $text = Get-Content (Join-Path $scriptsDir "build_go_fyne.ps1") -Raw
    $text -match '\[bool\] \$NoConsole = \$true' -and $text -match '\[bool\] \$Strip = \$true' -and
    $text -match '-trimpath'
}
Run-Test "build_go_gio.ps1 strip/no-console defaults" {
    $text = Get-Content (Join-Path $scriptsDir "build_go_gio.ps1") -Raw
    $text -match '\[bool\] \$NoConsole = \$true' -and $text -match '\[bool\] \$Strip = \$true' -and
    $text -match '-trimpath'
}
Run-Test "build_macos/linux size flags" {
    $mac = Get-Content (Join-Path $scriptsDir "build_macos.ps1") -Raw
    $linux = Get-Content (Join-Path $scriptsDir "build_linux.ps1") -Raw
    $mac -match 'EnableCompressionInSingleFile' -and $linux -match 'EnableCompressionInSingleFile' -and
    $linux -match '--noupx'
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
    Get-ChildItem "$root\examples" -Recurse -Filter "*.py" | ForEach-Object {
        Run-Test "$($_.FullName.Substring($root.Length + 1)) ast.parse" {
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
Run-Test "build_linux.ps1 uses Linux-compatible Go flags" {
    $text = Get-Content (Join-Path $scriptsDir "build_linux.ps1") -Raw
    $text -notmatch '-H windowsgui'
}
Run-Test "build_go_fyne.ps1 derives EXE name from AppId" {
    $text = Get-Content (Join-Path $scriptsDir "build_go_fyne.ps1") -Raw
    $text -notmatch 'env:AppId.*Substring'
}

# 6.5 Documented count sync. This check is not counted as a test because
# it compares the final total with the numbers in tests/README.md and
# SKILL.md, which must be updated whenever the suite changes.
$readmeCount = [regex]::Match((Get-Content (Join-Path $root "tests\README.md") -Raw), "Passed:\s*(\d+)")
$skillCount = [regex]::Match((Get-Content (Join-Path $root "SKILL.md") -Raw), "\((\d+)\s*/\s*\d+ currently pass")
$docsMatch = $false
if ($readmeCount.Success -and $skillCount.Success) {
    $docsMatch = [int]$readmeCount.Groups[1].Value -eq $script:passes -and
                 [int]$skillCount.Groups[1].Value -eq $script:passes
}
if ($docsMatch) {
    Write-Host "  [OK]   documented Windows smoke count ($($script:passes))"
} else {
    Write-Host "  [FAIL] documented Windows smoke count: README/SKILL.md must report $($script:passes)" -ForegroundColor Red
    $script:failures++
    $script:failedTests += "documented Windows smoke count matches actual"
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
