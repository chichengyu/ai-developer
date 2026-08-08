# build_macos.ps1 -- Cross-compile or natively build a macOS desktop app.
#
# Supports the same toolkit as the Windows side: dotnet publish, cargo
# build (Tauri/Rust), xcodebuild (Swift/SwiftUI). This script must run
# on a machine with the macOS toolchain installed -- typically a macOS
# host or a CI runner with macOS as the OS.
#
# Usage:
#   powershell -File build_macos.ps1 -Tool dotnet -Project src/MyApp -Arch arm64
#   powershell -File build_macos.ps1 -Tool cargo  -Project src-tauri -Arch arm64
#   powershell -File build_macos.ps1 -Tool xcode  -Project MyApp.xcodeproj -Arch arm64
#   powershell -File build_macos.ps1 -Tool cargo  -Project src-tauri -Install
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidateSet("dotnet","cargo","xcode")] [string] $Tool,
    [Parameter(Mandatory)] [string] $Project,
    [ValidateSet("x64","arm64")]
    [string] $Arch = "arm64",
    [string] $Configuration = "Release",
    [string] $OutputDir = "dist",
    [switch] $Install                  # install missing tauri-cli / Rust target; default is check-only
)

$ErrorActionPreference = "Stop"

# Map our friendly Arch to Apple target triples and dotnet RIDs.
$archMap = @{
    "x64"   = @{ Triple = "x86_64-apple-darwin";    Rid = "osx-x64";   Xcode = "x86_64" }
    "arm64" = @{ Triple = "aarch64-apple-darwin";   Rid = "osx-arm64"; Xcode = "arm64"   }
}

if (-not $archMap.ContainsKey($Arch)) { throw "Unknown Arch: $Arch" }
$entry = $archMap[$Arch]
Write-Host "==> macOS build: Tool=$Tool  Arch=$Arch  ($($entry.Triple))" -ForegroundColor Cyan

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
        if (-not $Install) {
            throw "cargo-tauri is not installed. Run with -Install to install it, or run: cargo install tauri-cli --version '^2.0' --locked"
        }
        Write-Host "==> Installing tauri-cli" -ForegroundColor Cyan
        cargo install tauri-cli --version "^2.0" --locked
    }
    # Ensure target installed; only install when explicitly requested.
    if ($Install) {
        rustup target add $entry.Triple
    } else {
        Write-Host "==> Ensure Rust target is installed: rustup target add $($entry.Triple) (or pass -Install)" -ForegroundColor Yellow
    }
    Push-Location $Project
    try {
        & cargo tauri build --target $entry.Triple
        if ($LASTEXITCODE -ne 0) { throw "tauri build failed" }
    } finally { Pop-Location }
}
elseif ($Tool -eq "xcode") {
    if (-not (Get-Command xcodebuild -ErrorAction SilentlyContinue)) {
        throw "xcodebuild not on PATH. Install Xcode from the App Store."
    }
    & xcodebuild -project $Project -scheme (Split-Path $Project -LeafBase) -configuration $Configuration `
        -destination "generic/platform=$(if ($Arch -eq 'arm64') {'macOS'} else {'macOS'}),arch=$($entry.Xcode)" `
        -derivedDataPath "$OutputDir/derived"
    if ($LASTEXITCODE -ne 0) { throw "xcodebuild failed" }
}

Write-Host "==> Done. Next: code-sign + notarize + DMG" -ForegroundColor Green
Write-Host "  See scripts/build_dmg.sh for packaging." -ForegroundColor Yellow
