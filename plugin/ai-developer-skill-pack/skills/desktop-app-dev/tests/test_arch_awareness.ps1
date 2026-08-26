# test_arch_awareness.ps1 -- verify that all build_*.ps1 scripts accept
# the standard -Arch / -Rid parameter, and that ValidateSet constraints
# include x64 / arm64 / x86 (or the framework's native equivalent).
#
# This is a structural test -- it does not actually invoke cargo / dotnet /
# npm. It only checks the parameter blocks.
#
# Run:
#   powershell -ExecutionPolicy Bypass -File tests/test_arch_awareness.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$scriptsDir = Join-Path $root "scripts"

$failures = 0
$passes = 0

function Test-ArchParam {
    param(
        [string] $ScriptPath,
        [string[]] $ExpectedArches   # e.g. @("x64","arm64","x86")
    )

    $name = Split-Path -Leaf $ScriptPath
    if (-not (Test-Path $ScriptPath)) {
        Write-Host "  [FAIL] $name -- file missing" -ForegroundColor Red
        $script:failures++; return
    }
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$null, [ref]$null)

    # Find the param block.
    $paramBlock = $ast.ParamBlock
    if (-not $paramBlock) {
        Write-Host "  [FAIL] $name -- no param() block" -ForegroundColor Red
        $script:failures++; return
    }
    $paramNames = $paramBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath }

    # Check for either $Arch or $Rid parameter.
    $hasArch = "Arch" -in $paramNames
    $hasRid  = "Rid"  -in $paramNames
    if (-not ($hasArch -or $hasRid)) {
        Write-Host "  [FAIL] $name -- missing -Arch or -Rid parameter" -ForegroundColor Red
        $script:failures++; return
    }

    # Find ValidateSet attributes on the Arch / Rid parameter via TypeName.
    $archParam = $paramBlock.Parameters | Where-Object {
        $_.Name.VariablePath.UserPath -in @("Arch","Rid")
    } | Select-Object -First 1
    $vsAst = $archParam.Attributes |
             Where-Object { $_.TypeName.Name -eq "ValidateSet" } |
             Select-Object -First 1
    if (-not $vsAst) {
        Write-Host "  [FAIL] $name -- $($archParam.Name.VariablePath.UserPath) parameter has no [ValidateSet(...)]" -ForegroundColor Red
        $script:failures++; return
    }

    # Positional arguments of ValidateSet are the allowed values.
    $vsValues = $vsAst.PositionalArguments |
                ForEach-Object { $_.Value }
    foreach ($expected in $ExpectedArches) {
        $hit = $false
        foreach ($v in $vsValues) {
            # Match win-x64 -> x64, x86_64 -> x64, etc.
            if ($v -match $expected) { $hit = $true; break }
        }
        if (-not $hit) {
            Write-Host "  [FAIL] $name -- ValidateSet '$($vsValues -join ", ")' missing arch '$expected'" -ForegroundColor Red
            $script:failures++; return
        }
    }

    Write-Host "  [OK]  $name -- $($archParam.Name) accepts $($vsValues -join ", ")" -ForegroundColor Green
    $script:passes++
}

Write-Host "=== -Arch / -Rid coverage ==="

Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_dotnet.ps1")        -ExpectedArches @("x64","arm64","x86")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_dotnet_nativeaot.ps1") -ExpectedArches @("win-x64")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_tauri.ps1")         -ExpectedArches @("x64","arm64","x86")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_electron.ps1")     -ExpectedArches @("x64","arm64","ia32")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_qt.ps1")           -ExpectedArches @("x64","arm64","x86")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_python.ps1")       -ExpectedArches @("x64","arm64","x86")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_go_wails.ps1")     -ExpectedArches @("x64","arm64","x86")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_go_fyne.ps1")      -ExpectedArches @("x64","arm64","x86")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_go_gio.ps1")       -ExpectedArches @("x64","arm64","x86")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_kotlin_compose.ps1") -ExpectedArches @("x64","arm64","x86")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_swift.ps1")        -ExpectedArches @("x64","arm64")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_neutralino.ps1")   -ExpectedArches @("any","x64","arm64","x86")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_macos.ps1")        -ExpectedArches @("x64","arm64")
Test-ArchParam -ScriptPath (Join-Path $scriptsDir "build_linux.ps1")        -ExpectedArches @("x64","arm64")

Write-Host ""
Write-Host "=== Host architecture ==="
$hostArch = if ([System.Environment]::Is64BitOperatingSystem) {
    try {
        if ([System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -eq "Arm64") { "arm64" }
        else { "x64" }
    } catch {
        if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }
    }
} else { "x86" }
Write-Host "  Build host arch: $hostArch"

Write-Host ""

Write-Host ""
Write-Host "=== auto_update_*.ps1 parse ==="
Get-ChildItem -Path (Join-Path $scriptsDir "auto_update_*.ps1") -ErrorAction SilentlyContinue | ForEach-Object {
    $tokens=$null; $errors=$null
    [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors) | Out-Null
    $name = $_.Name
    Write-Host ("  {0,-30} {1}" -f $name, $(if ($errors) {"FAIL"} else {"OK"}))
    if (-not $errors) { $script:passes++ } else { $script:failures++ }
}

Write-Host "=== Summary ==="
Write-Host "  Passed:   $passes"
Write-Host "  Failures: $failures"
if ($script:failures -gt 0) { exit 1 } else { exit 0 }


