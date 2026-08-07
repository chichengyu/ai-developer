# build_tauri.ps1 -- Tauri bundle (NSIS + MSI targets by default).
#
# Usage: powershell -File build_tauri.ps1
#        powershell -File build_tauri.ps1 -Arch arm64
[CmdletBinding()]
param(
    [switch] $NoBundle,
    [string[]] $Targets = @("nsis", "msi"),
    [ValidateSet("x64", "arm64", "x86")]
    [string] $Arch = "x64"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) { throw "cargo not on PATH. Install Rust from https://rustup.rs" }
if (-not (Get-Command cargo-tauri -ErrorAction SilentlyContinue)) {
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

# Ensure the target is installed (non-fatal if already present).
& rustup target add $rustTarget 2>$null

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