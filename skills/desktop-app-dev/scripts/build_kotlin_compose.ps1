# build_kotlin_compose.ps1 -- Compose Multiplatform (Kotlin) desktop packaging.
#
# Usage: powershell -ExecutionPolicy Bypass -File build_kotlin_compose.ps1
[CmdletBinding()]
param(
    [string] $ProjectDir = ".",
    [string] $Target = "packageDistributionForCurrentOS",
    [switch] $Release,
    [ValidateSet("x64", "arm64", "x86")]
    [string] $Arch = "x64"
)

# Map Arch to a hint for the gradle property (Compose Desktop honours
# org.gradle.jvmargs + nativeArch via the Kotlin Multiplatform plugin).
$nativeArch = @{ "x64" = "x64"; "arm64" = "aarch64"; "x86" = "x86" }[$Arch]
Write-Host "==> Compose nativeArch: $nativeArch (Arch=$Arch)" -ForegroundColor Cyan

$ErrorActionPreference = "Stop"

if (-not (Get-Command gradle -ErrorAction SilentlyContinue)) {
    throw "gradle not on PATH. Install via 'gradle wrapper' from the project, or download from https://gradle.org/install/"
}
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    throw "JDK not on PATH. Install JDK 17+ (Temurin or Zulu recommended for Compose Desktop)."
}

$gradleArgs = @($Target)
if ($Release) { $gradleArgs = @($Target, "-Pcompose.desktop.release=true") }

Write-Host "==> gradle $($gradleArgs -join ' ')" -ForegroundColor Cyan
Push-Location $ProjectDir
try {
    & gradle @gradleArgs
    if ($LASTEXITCODE -ne 0) { throw "gradle failed" }
} finally { Pop-Location }

# Find output MSI / EXE
$msiDir = Join-Path $ProjectDir "build/compose/binaries/main-release/msi"
$exeDir = Join-Path $ProjectDir "build/compose/binaries/main-release/app"
if (Test-Path $msiDir) { Write-Host "==> MSI: $(Get-ChildItem $msiDir/*.msi -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)" -ForegroundColor Green }
if (Test-Path $exeDir) { Write-Host "==> EXE: $(Get-ChildItem $exeDir/*.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)" -ForegroundColor Green }
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow
