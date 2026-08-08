# build_python.ps1 -- PyInstaller packaging for a Python desktop app.
#
# Python resolution is shared with the other skill scripts via
# scripts/find_python.ps1 (Get-ProjectPython):
#   -PythonExe -> CODEX_PYTHON -> PYTHON -> Codex runtime -> PATH.
#
# Usage: powershell -ExecutionPolicy Bypass -File build_python.ps1 -Entry app.py -Name MyApp
#        powershell -ExecutionPolicy Bypass -File build_python.ps1 -Entry app.py -Name MyApp -BackupSource
#        powershell -ExecutionPolicy Bypass -File build_python.ps1 -Entry app.py -Name MyApp -Install
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
    [string[]] $ExcludeModules = @("unittest", "pydoc", "pydoc_data", "tkinter.test", "setuptools", "distutils"),
    [string] $OutDir = "dist",
    [switch] $BackupSource,          # timestamped source zip before packaging
    [switch] $Install,               # install missing PyInstaller; default is check-only
    [switch] $Upx                    # opt-in UPX compression; may increase AV false positives
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "find_python.ps1")

function Resolve-Python {
    param([string]$Explicit)
    $py = Get-ProjectPython -Explicit $Explicit
    if (-not $py) {
        throw "No Python interpreter found. Set -PythonExe, CODEX_PYTHON, or PYTHON, or install Python on PATH."
    }
    Write-Host "==> Using Python: $py" -ForegroundColor Cyan
    return $py
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

if ($BackupSource) {
    Write-Host "==> Backing up source before packaging" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "backup_source.ps1") `
        -SourcePath (Get-Location).Path `
        -OutputDir (Join-Path $OutDir "source_backup") `
        -Name $Name
    if ($LASTEXITCODE -ne 0) { throw "Source backup failed" }
}

# Ensure PyInstaller is available
& $py -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    if (-not $Install) {
        throw "PyInstaller is not installed. Run with -Install to install it, or run: $py -m pip install pyinstaller"
    }
    Write-Host "==> Installing PyInstaller" -ForegroundColor Cyan
    & $py -m pip install --upgrade pip
    & $py -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed" }
}

$pyiArgs = @("--onefile", "--windowed", "--name", $Name,
             "--distpath", $OutDir, "--workpath", "build", "--specpath", "build")
if (-not $Upx) {
    # UPX-packed EXEs are more likely to trip SmartScreen/AV; keep the
    # default artifact clean and deterministic unless the caller opts in.
    $pyiArgs += "--noupx"
}
foreach ($m in $ExcludeModules) {
    if ($m) { $pyiArgs += @("--exclude-module", $m) }
}

if ($Icon -and (Test-Path $Icon)) { $pyiArgs += @("--icon", $Icon) }
foreach ($h in $HiddenImports) { $pyiArgs += @("--hidden-import", $h) }
foreach ($d in $AddData) { $pyiArgs += @("--add-data", $d) }

if ($Upx) {
    Write-Host "==> NOTE: UPX enabled. Test the EXE on a clean VM; UPX can trigger AV false positives." -ForegroundColor Yellow
}

Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
& $py -m PyInstaller @pyiArgs $Entry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $OutDir "$Name.exe"
if (-not (Test-Path $exe)) { throw "Expected $exe not produced" }
$size = (Get-Item $exe).Length
Write-Host ("==> Built: {0}  ({1:N1} MB / {2:N0} KB)" -f $exe, ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
Write-Host "Next: sign with signtool, then test on a clean Windows VM (no Python installed)." -ForegroundColor Yellow


