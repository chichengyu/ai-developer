# build_linux.ps1 -- Cross-compile or natively build a Linux desktop app.
#
# Supports dotnet, cargo, go, pyinstaller. This script must run on a
# machine with the Linux toolchain installed -- typically a Linux host or
# a CI runner with Linux as the OS. Cross-compiling from Windows is
# possible but limited; native build on the target distro is the
# recommended path.
#
# Usage:
#   powershell -File build_linux.ps1 -Tool dotnet -Project src/MyApp -Arch x64
#   powershell -File build_linux.ps1 -Tool cargo  -Project src-tauri -Arch arm64
#   powershell -File build_linux.ps1 -Tool go     -Project . -Arch arm64
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateSet("dotnet","cargo","go","python")] [string] $Tool,
    [string] $Project = ".",
    [ValidateSet("x64","arm64")]
    [string] $Arch = "x64",
    [string] $Configuration = "Release",
    [string] $OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

# Map friendly Arch to dotnet RID and Rust triple.
$archMap = @{
    "x64"   = @{ Triple = "x86_64-unknown-linux-gnu";   Rid = "linux-x64";   GoArch = "amd64" }
    "arm64" = @{ Triple = "aarch64-unknown-linux-gnu";  Rid = "linux-arm64"; GoArch = "arm64" }
}

if (-not $archMap.ContainsKey($Arch)) { throw "Unknown Arch: $Arch" }
$entry = $archMap[$Arch]
Write-Host "==> Linux build: Tool=$Tool  Arch=$Arch  ($($entry.Triple))" -ForegroundColor Cyan

if ($Tool -eq "dotnet") {
    if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
        throw "dotnet not on PATH. Install .NET SDK from https://dot.net/download"
    }
    Write-Host "==> dotnet publish -r $($entry.Rid)" -ForegroundColor Cyan
    dotnet publish $Project -c $Configuration -r $entry.Rid --self-contained true `
        -p:PublishSingleFile=true -o $OutputDir
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }
}
elseif ($Tool -eq "cargo") {
    if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
        throw "cargo not on PATH. Install Rust from https://rustup.rs"
    }
    if (-not (Get-Command cargo-tauri -ErrorAction SilentlyContinue)) {
        Write-Host "==> Installing tauri-cli" -ForegroundColor Cyan
        cargo install tauri-cli --version "^2.0" --locked
    }
    rustup target add $entry.Triple 2>$null
    Push-Location $Project
    try {
        & cargo tauri build --target $entry.Triple
        if ($LASTEXITCODE -ne 0) { throw "tauri build failed" }
    } finally { Pop-Location }
}
elseif ($Tool -eq "go") {
    if (-not (Get-Command go -ErrorAction SilentlyContinue)) {
        throw "go not on PATH. Install Go from https://go.dev/dl/"
    }
    $env:GOOS = "linux"
    $env:GOARCH = $entry.GoArch
    Write-Host "==> GOOS=linux GOARCH=$($entry.GoArch) go build" -ForegroundColor Cyan
    Push-Location $Project
    try {
        & go build -ldflags "-s -w -H windowsgui" -o "$OutputDir/myapp"
        if ($LASTEXITCODE -ne 0) { throw "go build failed" }
    } finally { Pop-Location }
}
elseif ($Tool -eq "python") {
    Write-Host "==> PyInstaller is host-bound; on Linux it produces a Linux ELF." -ForegroundColor Cyan
    Write-Host "==> Run this script on the Linux target, not from Windows." -ForegroundColor Yellow
    if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
        throw "pyinstaller not on PATH. pip install pyinstaller on the target."
    }
    & pyinstaller --onefile --name myapp $Project
}

Write-Host "==> Done. Next: package as .deb / .rpm / AppImage / Flatpak / Snap" -ForegroundColor Green
Write-Host "  See scripts/build_appimage.sh, scripts/build_deb.sh." -ForegroundColor Yellow