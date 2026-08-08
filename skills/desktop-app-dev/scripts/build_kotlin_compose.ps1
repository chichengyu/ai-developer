# build_kotlin_compose.ps1 -- Compose Multiplatform (Kotlin) desktop packaging.
#
# Usage: powershell -ExecutionPolicy Bypass -File build_kotlin_compose.ps1
[CmdletBinding()]
param(
    [string] $ProjectDir = ".",
    [string] $Target = "packageDistributionForCurrentOS",
    [switch] $Release,
    [ValidateSet("x64", "arm64", "x86")]
    [string] $Arch = "x64",
    [switch] $BackupSource             # timestamped source zip before packaging
)

# Map Arch to a hint for the gradle property (Compose Desktop honours
# org.gradle.jvmargs + nativeArch via the Kotlin Multiplatform plugin).
$nativeArch = @{ "x64" = "x64"; "arm64" = "aarch64"; "x86" = "x86" }[$Arch]
Write-Host "==> Compose nativeArch: $nativeArch (Arch=$Arch)" -ForegroundColor Cyan

$ErrorActionPreference = "Stop"

Write-Host "==> NOTE: Compose Desktop usually bundles a JBR; keep only required jlink modules in nativeDistributions.modules(...) to reduce size." -ForegroundColor Yellow

if ($BackupSource) {
    $backupName = if ($ProjectDir -and $ProjectDir -ne ".") { Split-Path -Leaf $ProjectDir } else { Split-Path -Leaf (Get-Location).Path }
    Write-Host "==> Backing up source before packaging" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "backup_source.ps1") `
        -SourcePath (Get-Location).Path `
        -OutputDir "source_backup" `
        -Name $backupName
    if ($LASTEXITCODE -ne 0) { throw "Source backup failed" }
}

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
if (Test-Path $msiDir) {
    Get-ChildItem $msiDir -Filter *.msi -ErrorAction SilentlyContinue | ForEach-Object {
        $size = $_.Length
        Write-Host ("==> MSI: {0} ({1:N1} MB / {2:N0} KB)" -f $_.FullName, ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
    }
}
if (Test-Path $exeDir) {
    Get-ChildItem $exeDir -Filter *.exe -ErrorAction SilentlyContinue | ForEach-Object {
        $size = $_.Length
        Write-Host ("==> EXE: {0} ({1:N1} MB / {2:N0} KB)" -f $_.FullName, ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
    }
}
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow
