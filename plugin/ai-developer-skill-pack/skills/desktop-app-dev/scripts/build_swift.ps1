# build_swift.ps1 -- Swift on Windows packaging.
#
# Requires Swift toolchain for Windows installed:
#     https://www.swift.org/install/windows/
#     (Add C:\Program Files\Swift\Toolchains\*\usr\bin to PATH)
#
# Usage: powershell -ExecutionPolicy Bypass -File build_swift.ps1
[CmdletBinding()]
param(
    [string] $Config = "release",
    [bool] $Osize = $true,           # optimize for size (-Osize)
    [switch] $Static,
    [ValidateSet("x64", "arm64")]
    [string] $Arch = "x64",
    [switch] $BackupSource             # timestamped source zip before packaging
)

$ErrorActionPreference = "Stop"

if ($BackupSource) {
    Write-Host "==> Backing up source before packaging" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "backup_source.ps1") `
        -SourcePath (Get-Location).Path `
        -OutputDir "source_backup" `
        -Name (Split-Path -Leaf (Get-Location).Path)
    if ($LASTEXITCODE -ne 0) { throw "Source backup failed" }
}

if (-not (Get-Command swift -ErrorAction SilentlyContinue)) {
    throw "swift not on PATH. Install the Swift toolchain for Windows from https://www.swift.org/install/windows/"
}

# Swift on Windows uses --triple to select the target.
$triple = @{ "x64" = "x86_64-unknown-windows-msvc"; "arm64" = "aarch64-unknown-windows-msvc" }[$Arch]
Write-Host "==> swift build --triple $triple" -ForegroundColor Cyan

$buildArgs = @("build", "-c", $Config, "--triple", $triple)
if ($Osize) { $buildArgs += "-Xswiftc", "-Osize" }
if ($Static) { $buildArgs += "-Xswiftc", "-static-stdlib" }

Write-Host "==> swift build $($buildArgs -join ' ')" -ForegroundColor Cyan
& swift @buildArgs
if ($LASTEXITCODE -ne 0) { throw "swift build failed" }

# Locate produced EXE
$binDir = ".build" + [System.IO.Path]::DirectorySeparatorChar + $Config
$exe = Get-ChildItem -Path $binDir -Filter *.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
if ($exe) {
    $size = (Get-Item $exe).Length
    Write-Host ("==> Built: {0} ({1:N1} MB / {2:N0} KB)" -f $exe, ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
    Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow
} else {
    Write-Host "Build complete but no .exe found in $binDir. Verify Package.swift has a Windows executable target." -ForegroundColor Yellow
}
