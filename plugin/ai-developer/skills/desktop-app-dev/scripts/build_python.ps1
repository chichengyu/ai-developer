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
    [string[]] $Paths = @(),         # extra module search paths for PyInstaller
    [ValidateSet("auto", "x64", "arm64", "x86")]
    [string] $Arch = "auto",         # PyInstaller is host-bound; "auto" uses host arch
    [string[]] $ExcludeModules = @("unittest", "pydoc", "pydoc_data", "tkinter.test", "setuptools", "distutils"),
    [string] $OutDir = "dist",
    [ValidateSet("OneFile", "OneDir")]
    [string] $Mode = "OneFile",
    [switch] $FastStart,             # faster cold start + leaner PySide6 bundle
    [switch] $InstallDeps,           # pip install requirements.txt before building
    [string[]] $Requirements = @(),  # explicit requirements files for -InstallDeps
    [string[]] $FastExcludeModules = @(
        "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
        "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtDesigner",
        "PySide6.QtHelp", "PySide6.QtLocation", "PySide6.QtLottie",
        "PySide6.QtMultimedia", "PySide6.QtNetwork", "PySide6.QtPdf",
        "PySide6.QtPrintSupport", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.QtSql", "PySide6.QtSvg", "PySide6.QtTest",
        "PySide6.QtWebChannel", "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets", "PySide6.QtXml"
    ),
    [switch] $BackupSource,          # timestamped source zip before packaging
    [switch] $Install,               # install missing PyInstaller; default is check-only
    [switch] $Upx                    # opt-in UPX compression; may increase AV false positives
)

$ErrorActionPreference = "Stop"

# -File invocations pass comma-separated values as one string; normalize
# them so -HiddenImports/-ExcludeModules still work from docs/README.
foreach ($listName in @("HiddenImports", "ExcludeModules", "FastExcludeModules", "Requirements", "Paths")) {
    $normalized = @()
    foreach ($value in (Get-Variable $listName -ValueOnly)) {
        foreach ($part in ($value -split '[,;]')) {
            $part = $part.Trim()
            if ($part) { $normalized += $part }
        }
    }
    Set-Variable -Name $listName -Value $normalized
}

# -FastStart means fast cold start unless the caller explicitly requested
# the single-file -Mode OneFile output.
if ($FastStart -and -not $PSBoundParameters.ContainsKey("Mode")) {
    $Mode = "OneDir"
}

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

if ($InstallDeps) {
    $reqFiles = @($Requirements)
    if ($reqFiles.Count -eq 0) {
        $entryDir = Split-Path -Parent $Entry
        if (-not $entryDir) { $entryDir = "." }
        $entryRequirements = Join-Path $entryDir "requirements.txt"
        if (Test-Path $entryRequirements) {
            $reqFiles = @($entryRequirements)
        } elseif (Test-Path "requirements.txt") {
            $reqFiles = @("requirements.txt")
        }
    }
    foreach ($req in $reqFiles) {
        if (-not (Test-Path $req)) {
            throw "Requirements file not found: $req"
        }
        Write-Host "==> Installing dependencies from $req" -ForegroundColor Cyan
        & $py -m pip install --disable-pip-version-check -r $req
        if ($LASTEXITCODE -ne 0) { throw "Dependency install failed for $req" }
    }
}

$pyiArgs = @("--windowed", "--name", $Name,
             "--distpath", $OutDir, "--workpath", "build", "--specpath", "build")
if ($Mode -eq "OneFile") {
    $pyiArgs += "--onefile"
} else {
    $pyiArgs += "--onedir"
}
if ($FastStart) {
    $pyiArgs += @("--clean", "--noconfirm", "--disable-windowed-traceback", "--optimize", "1")
    foreach ($m in $FastExcludeModules) {
        if ($m) { $pyiArgs += @("--exclude-module", $m) }
    }
    if ($Mode -eq "OneFile") {
        Write-Host "==> NOTE: -FastStart with -Mode OneFile still extracts to temp on launch; -Mode OneDir starts faster." -ForegroundColor Yellow
    } else {
        Write-Host "==> FastStart: OneDir output, lean PySide6 excludes, no windowed traceback." -ForegroundColor Cyan
    }
}
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
foreach ($p in $Paths) { $pyiArgs += @("--paths", $p) }
foreach ($addEntry in $AddData) {
    foreach ($d in ($addEntry -split ',')) {
        $sep = $d.IndexOf(';')
        if ($sep -lt 0) { throw "AddData must use SOURCE;DEST syntax: $d" }
        $src = $d.Substring(0, $sep)
        $dest = $d.Substring($sep + 1)
        if (-not [System.IO.Path]::IsPathRooted($src)) {
            $src = Join-Path (Get-Location).Path $src
        }
        $pyiArgs += ("--add-data={0}:{1}" -f $src, $dest)
    }
}

if ($Upx) {
    Write-Host "==> NOTE: UPX enabled. Test the EXE on a clean VM; UPX can trigger AV false positives." -ForegroundColor Yellow
}

Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
& $py -m PyInstaller @pyiArgs $Entry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

if ($Mode -eq "OneDir") {
    $exe = Join-Path $OutDir "$Name\$Name.exe"
} else {
    $exe = Join-Path $OutDir "$Name.exe"
}
if (-not (Test-Path $exe)) { throw "Expected $exe not produced" }
if ($Mode -eq "OneDir") {
    $size = (Get-ChildItem (Split-Path $exe -Parent) -Recurse -File | Measure-Object Length -Sum).Sum
} else {
    $size = (Get-Item $exe).Length
}
Write-Host ("==> Built: {0}  ({1:N1} MB / {2:N0} KB)" -f $exe, ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
Write-Host "Next: sign with signtool, then test on a clean Windows VM (no Python installed)." -ForegroundColor Yellow
exit 0


