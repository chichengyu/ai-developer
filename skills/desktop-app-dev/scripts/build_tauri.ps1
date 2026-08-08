# build_tauri.ps1 -- Tauri bundle (NSIS + MSI targets by default).
#
# Usage: powershell -File build_tauri.ps1
#        powershell -File build_tauri.ps1 -Arch arm64
#        powershell -File build_tauri.ps1 -Install
[CmdletBinding()]
param(
    [switch] $NoBundle,
    [string[]] $Targets = @("nsis", "msi"),
    [ValidateSet("x64", "arm64", "x86")]
    [string] $Arch = "x64",
    [switch] $Install                # install missing tauri-cli / Rust target; default is check-only
)

$ErrorActionPreference = "Stop"

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
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow
