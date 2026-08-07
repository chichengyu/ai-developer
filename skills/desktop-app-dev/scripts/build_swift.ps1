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
    [switch] $Static,
    [ValidateSet("x64", "arm64")]
    [string] $Arch = "x64"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command swift -ErrorAction SilentlyContinue)) {
    throw "swift not on PATH. Install the Swift toolchain for Windows from https://www.swift.org/install/windows/"
}

# Swift on Windows uses --triple to select the target.
$triple = @{ "x64" = "x86_64-unknown-windows-msvc"; "arm64" = "aarch64-unknown-windows-msvc" }[$Arch]
Write-Host "==> swift build --triple $triple" -ForegroundColor Cyan

$buildArgs = @("build", "-c", $Config, "--triple", $triple)
if ($Static) { $buildArgs += "-Xswiftc", "-static-stdlib" }

Write-Host "==> swift build $($buildArgs -join ' ')" -ForegroundColor Cyan
& swift @buildArgs
if ($LASTEXITCODE -ne 0) { throw "swift build failed" }

# Locate produced EXE
$binDir = ".build" + [System.IO.Path]::DirectorySeparatorChar + $Config
$exe = Get-ChildItem -Path $binDir -Filter *.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
if ($exe) {
    Write-Host "==> Built: $exe" -ForegroundColor Green
    Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow
} else {
    Write-Host "Build complete but no .exe found in $binDir. Verify Package.swift has a Windows executable target." -ForegroundColor Yellow
}
