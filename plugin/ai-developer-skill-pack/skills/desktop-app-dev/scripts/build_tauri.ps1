# build_tauri.ps1 -- Tauri bundle (single NSIS installer by default; MSI opt-in).
#
# Usage: powershell -File build_tauri.ps1
#        powershell -File build_tauri.ps1 -Arch arm64
#        powershell -File build_tauri.ps1 -Install
[CmdletBinding()]
param(
    [switch] $NoBundle,
    [string[]] $Targets = @("nsis"),   # one single-file installer by default
    [ValidateSet("x64", "arm64", "x86")]
    [string] $Arch = "x64",
    [switch] $Install,               # install missing tauri-cli / Rust target; default is check-only
    [switch] $BackupSource,          # timestamped source zip before packaging
    [switch] $NoSizeProfile          # disable the size-optimized Rust release profile
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

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) { throw "cargo not on PATH. Install Rust from https://rustup.rs" }
if (-not (Get-Command cargo-tauri -ErrorAction SilentlyContinue)) {
    if (-not $Install) {
        throw "cargo-tauri is not installed. Run with -Install to install it, or run: cargo install tauri-cli --version '^2.0' --locked"
    }
    Write-Host "==> Installing tauri-cli" -ForegroundColor Cyan
    cargo install tauri-cli --version "^2.0" --locked
}

# Map our friendly Arch to a Rust target triple.
$rustTarget = @{
    "x64"   = "x86_64-pc-windows-msvc"
    "arm64" = "aarch64-pc-windows-msvc"
    "x86"   = "i686-pc-windows-msvc"
}[$Arch]
Write-Host "==> Target triple: $rustTarget (Arch=$Arch)" -ForegroundColor Cyan

# Cargo reads these env vars as [profile.release] overrides, so the script
# can shrink the binary without editing the project's Cargo.toml.
if (-not $NoSizeProfile) {
    $env:CARGO_PROFILE_RELEASE_OPT_LEVEL = "z"
    $env:CARGO_PROFILE_RELEASE_LTO = "true"
    $env:CARGO_PROFILE_RELEASE_CODEGEN_UNITS = "1"
    $env:CARGO_PROFILE_RELEASE_PANIC = "abort"
    $env:CARGO_PROFILE_RELEASE_STRIP = "true"
    Write-Host "==> Size profile: opt-level=z, lto=true, codegen-units=1, panic=abort, strip=true" -ForegroundColor Cyan
}

# Ensure the target is installed; only install when explicitly requested.
if ($Install) {
    & rustup target add $rustTarget
} else {
    Write-Host "==> Ensure Rust target is installed: rustup target add $rustTarget (or pass -Install)" -ForegroundColor Yellow
}

$bundleArgs = @("tauri", "build", "--target", $rustTarget)
if (-not $NoBundle) {
    foreach ($t in $Targets) { $bundleArgs += "--bundles"; $bundleArgs += $t }
}

Write-Host "==> cargo tauri build" -ForegroundColor Cyan
& cargo @bundleArgs
if ($LASTEXITCODE -ne 0) { throw "tauri build failed" }

$bundlePath = "src-tauri/target/$rustTarget/release/bundle"
Write-Host "==> Bundles in: $bundlePath" -ForegroundColor Green
Get-ChildItem -Path $bundlePath -Recurse -Include *.exe,*.msi -ErrorAction SilentlyContinue |
    ForEach-Object {
        $size = $_.Length
        Write-Host ("==> Artifact: {0}  ({1:N1} MB / {2:N0} KB)" -f $_.FullName, ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
    }
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow
