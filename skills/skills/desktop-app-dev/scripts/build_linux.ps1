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
#   powershell -File build_linux.ps1 -Tool cargo  -Project src-tauri -Install
#   powershell -File build_linux.ps1 -Tool python -Project src/app.py -Install
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateSet("dotnet","cargo","go","python")] [string] $Tool,
    [string] $Project = ".",
    [ValidateSet("x64","arm64")]
    [string] $Arch = "x64",
    [string] $Configuration = "Release",
    [string] $OutputDir = "dist",
    [switch] $Install,                 # install missing tauri-cli / Rust target / PyInstaller; default is check-only
    [switch] $BackupSource             # timestamped source zip before packaging
)

$ErrorActionPreference = "Stop"

$backupName = if ($Project -and $Project -ne ".") { Split-Path -Leaf $Project } else { Split-Path -Leaf (Get-Location).Path }
if ($BackupSource) {
    Write-Host "==> Backing up source before packaging" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "backup_source.ps1") `
        -SourcePath (Get-Location).Path `
        -OutputDir (Join-Path $OutputDir "source_backup") `
        -Name $backupName
    if ($LASTEXITCODE -ne 0) { throw "Source backup failed" }
}

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
        -p:PublishSingleFile=true `
        -p:EnableCompressionInSingleFile=true `
        -p:DebugType=None -p:DebugSymbols=false `
        -o $OutputDir
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }
}
elseif ($Tool -eq "cargo") {
    if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
        throw "cargo not on PATH. Install Rust from https://rustup.rs"
    }
    if (-not (Get-Command cargo-tauri -ErrorAction SilentlyContinue)) {
        if (-not $Install) {
            throw "cargo-tauri is not installed. Run with -Install to install it, or run: cargo install tauri-cli --version '^2.0' --locked"
        }
        Write-Host "==> Installing tauri-cli" -ForegroundColor Cyan
        cargo install tauri-cli --version "^2.0" --locked
    }
    if ($Install) {
        rustup target add $entry.Triple
    } else {
        Write-Host "==> Ensure Rust target is installed: rustup target add $($entry.Triple) (or pass -Install)" -ForegroundColor Yellow
    }
    $env:CARGO_PROFILE_RELEASE_OPT_LEVEL = "z"
    $env:CARGO_PROFILE_RELEASE_LTO = "true"
    $env:CARGO_PROFILE_RELEASE_CODEGEN_UNITS = "1"
    $env:CARGO_PROFILE_RELEASE_PANIC = "abort"
    $env:CARGO_PROFILE_RELEASE_STRIP = "true"
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
    $env:GOFLAGS = "$($env:GOFLAGS) -trimpath -buildvcs=false"
    Write-Host "==> GOOS=linux GOARCH=$($entry.GoArch) go build" -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    }
    Push-Location $Project
    try {
        & go build -ldflags "-s -w" -o "$OutputDir/myapp"
        if ($LASTEXITCODE -ne 0) { throw "go build failed" }
    } finally { Pop-Location }
}
elseif ($Tool -eq "python") {
    Write-Host "==> PyInstaller is host-bound; on Linux it produces a Linux ELF." -ForegroundColor Cyan
    Write-Host "==> Run this script on the Linux target, not from Windows." -ForegroundColor Yellow
    $py3 = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $py3) { throw "python3 not on PATH. Install Python 3 on the target." }
    & $py3.Source -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        if (-not $Install) {
            throw "PyInstaller is not installed. Run with -Install to install it, or run: $($py3.Source) -m pip install pyinstaller"
        }
        Write-Host "==> Installing PyInstaller" -ForegroundColor Cyan
        & $py3.Source -m pip install pyinstaller
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed" }
    }
    if (-not (Test-Path -LiteralPath $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    }
    $pyName = [System.IO.Path]::GetFileNameWithoutExtension($Project)
    if (-not $pyName) { $pyName = "myapp" }
    & $py3.Source -m PyInstaller --onefile --windowed --noupx --name $pyName `
        --distpath $OutputDir --workpath build --specpath build $Project
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
}

Get-ChildItem -Path $OutputDir -Recurse -File -ErrorAction SilentlyContinue |
    ForEach-Object {
        $size = $_.Length
        Write-Host ("==> Artifact: {0} ({1:N1} MB / {2:N0} KB)" -f $_.FullName, ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
    }
Write-Host "==> Done. Next: package as .deb / .rpm / AppImage / Flatpak / Snap" -ForegroundColor Green
Write-Host "  See scripts/build_appimage.sh, scripts/build_deb.sh." -ForegroundColor Yellow
