# build_dotnet.ps1 -- .NET self-contained publish with ReadyToRun + optional Costura.Fody.
# Usage: powershell -File build_dotnet.ps1 -Project src/MyApp/MyApp.csproj -Rid win-x64
#        powershell -File build_dotnet.ps1 -Project src/MyApp/MyApp.csproj -BackupSource
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Project,
    [ValidateSet("win-x64", "win-arm64", "win-x86")]
    [Alias("Arch")]
    [string] $Rid = "win-x64",
    [string] $Configuration = "Release",
    [switch] $NativeAot,
    [switch] $Costura,
    [switch] $BackupSource,          # timestamped source zip before publishing
    [string] $OutputDir = ""         # explicit publish output dir
)

$ErrorActionPreference = "Stop"

# .NET RID list at https://learn.microsoft.com/dotnet/core/rid-catalog
# NativeAOT is x64-only on .NET 8.
if ($NativeAot -and $Rid -ne "win-x64") {
    throw "NativeAOT requires -Rid win-x64 (got `$Rid)."
}

# Read the actual TFM so the publish-path fallback does not hardcode net8.0.
if (-not (Test-Path -LiteralPath $Project)) { throw "Project not found: $Project" }
$tfm = "net8.0"
$csprojText = Get-Content -LiteralPath $Project -Raw
if ($csprojText -match "<TargetFrameworks>\s*([^<;]+)") {
    $tfm = $Matches[1].Trim()
} elseif ($csprojText -match "<TargetFramework>\s*([^<]+)") {
    $tfm = $Matches[1].Trim()
}

if ($BackupSource) {
    $name = [System.IO.Path]::GetFileNameWithoutExtension($Project)
    Write-Host "==> Backing up source before publishing" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "backup_source.ps1") `
        -SourcePath (Get-Location).Path `
        -OutputDir "source_backup" `
        -Name $name
    if ($LASTEXITCODE -ne 0) { throw "Source backup failed" }
}

$pubArgs = @(
    "publish", $Project,
    "-c", $Configuration,
    "-r", $Rid,
    "--self-contained", "true",
    "-p:PublishSingleFile=true",
    "-p:IncludeNativeLibrariesForSelfExtract=true"
)
if ($OutputDir) {
    $pubArgs += "-o"
    $pubArgs += $OutputDir
}

if (-not $NativeAot) {
    $pubArgs += "-p:PublishReadyToRun=true"
} else {
    $pubArgs += "-p:PublishAot=true"
    Write-Host "==> NativeAOT enabled (smallest EXE, requires .NET 8+)" -ForegroundColor Cyan
}

Write-Host "==> dotnet publish" -ForegroundColor Cyan
dotnet @pubArgs
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }

$binPath = if ($OutputDir) {
    $OutputDir
} else {
    $publishRoot = Join-Path (Split-Path $Project -Parent) "bin/$Configuration"
    $found = Get-ChildItem -Path $publishRoot -Recurse -Directory -Filter "publish" `
                 -ErrorAction SilentlyContinue |
             Where-Object { $_.FullName -match [regex]::Escape($Rid) } |
             Select-Object -First 1
    if ($found) { $found.FullName } else { Join-Path $publishRoot "$tfm/$Rid/publish" }
}
Write-Host "==> Output: $binPath" -ForegroundColor Green
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow


