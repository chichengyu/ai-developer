# build_python.ps1 -- PyInstaller packaging for a Python desktop app.
#
# Resolution order for the Python executable:
#   1. -PythonExe parameter (explicit override)
#   2. $env:CODEX_PYTHON / $env:PYTHON  (env vars)
#   3. Codex primary runtime at C:\Users\xc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
#   4. python / python3 / py -3 on PATH
#
# Usage: powershell -ExecutionPolicy Bypass -File build_python.ps1 -Entry app.py -Name MyApp
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Entry,
    [Parameter(Mandatory)] [string] $Name,
    [string] $Icon = "",
    [string[]] $HiddenImports = @(),
    [string[]] $AddData = @(),       # "src;dest" pairs
    [string] $PythonExe = "",        # blank => auto-resolve
    [ValidateSet("auto", "x64", "arm64", "x86")]
    [string] $Arch = "auto",         # PyInstaller is host-bound; "auto" uses host arch
    [string] $OutDir = "dist"
)

$ErrorActionPreference = "Stop"

function Resolve-Python {
    param([string]$Explicit)
    $candidates = @()

    if ($Explicit) { $candidates += $Explicit }
    if ($env:CODEX_PYTHON) { $candidates += $env:CODEX_PYTHON }
    if ($env:PYTHON)        { $candidates += $env:PYTHON }

    # Codex primary runtime (well-known location)
    $codexRt = "C:\Users\xc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $codexRt) { $candidates += $codexRt }

    # PATH fallbacks
    foreach ($name in @("python","python3","py")) {
        $p = Get-Command $name -ErrorAction SilentlyContinue
        if ($p) { $candidates += $p.Source }
    }

    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) {
            Write-Host "==> Using Python: $c" -ForegroundColor Cyan
            return $c
        }
    }
    throw "No Python interpreter found. Set -PythonExe, CODEX_PYTHON, or PYTHON, or install Python on PATH."
}

$py = Resolve-Python -Explicit $PythonExe

# Verify -Arch matches the build host when explicitly requested.
# Fall back to $env:PROCESSOR_ARCHITECTURE so this works on Windows
# PowerShell 5.1 (which lacks RuntimeInformation).
if ($Arch -ne "auto") {
    $hostArch = $null
    try {
        $rtType = [System.Runtime.InteropServices.RuntimeInformation]
        if ($rtType -ne $null -and $rtType.ProcessArchitecture -eq "Arm64") {
            $hostArch = "arm64"
        }
    } catch { }
    if (-not $hostArch) {
        if (-not [System.Environment]::Is64BitOperatingSystem) {
            $hostArch = "x86"
        } elseif ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") {
            $hostArch = "arm64"
        } else {
            $hostArch = "x64"
        }
    }
    if ($Arch -ne $hostArch) {
        Write-Host ("==> WARNING: -Arch {0} requested but host is {1}. PyInstaller cannot cross-compile; the output EXE will be {1}." -f $Arch, $hostArch) -ForegroundColor Yellow
    }
}

# Ensure PyInstaller is available
& $py -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "==> Installing PyInstaller" -ForegroundColor Cyan
    & $py -m pip install --upgrade pip
    & $py -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed" }
}

$pyiArgs = @("--onefile", "--windowed", "--name", $Name,
             "--distpath", $OutDir, "--workpath", "build", "--specpath", "build")

if ($Icon -and (Test-Path $Icon)) { $pyiArgs += @("--icon", $Icon) }
foreach ($h in $HiddenImports) { $pyiArgs += @("--hidden-import", $h) }
foreach ($d in $AddData) { $pyiArgs += @("--add-data", $d) }

Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
& $py -m PyInstaller @pyiArgs $Entry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $OutDir "$Name.exe"
if (-not (Test-Path $exe)) { throw "Expected $exe not produced" }
Write-Host "==> Built: $exe" -ForegroundColor Green
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow


