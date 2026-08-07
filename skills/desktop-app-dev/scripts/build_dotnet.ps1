# build_dotnet.ps1 -- .NET self-contained publish with ReadyToRun + optional Costura.Fody.
# Usage: powershell -File build_dotnet.ps1 -Project src/MyApp/MyApp.csproj -Rid win-x64
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Project,
    [ValidateSet("win-x64", "win-arm64", "win-x86")]
    [Alias("Arch")]
    [string] $Rid = "win-x64",
    [string] $Configuration = "Release",
    [switch] $NativeAot,
    [switch] $Costura
)

$ErrorActionPreference = "Stop"

# .NET RID list at https://learn.microsoft.com/dotnet/core/rid-catalog
# NativeAOT is x64-only on .NET 8.
if ($NativeAot -and $Rid -ne "win-x64") {
    throw "NativeAOT requires -Rid win-x64 (got `$Rid)."
}

$pubArgs = @(
    "publish", $Project,
    "-c", $Configuration,
    "-r", $Rid,
    "--self-contained", "true",
    "-p:PublishSingleFile=true",
    "-p:IncludeNativeLibrariesForSelfExtract=true"
)

if (-not $NativeAot) {
    $pubArgs += "-p:PublishReadyToRun=true"
} else {
    $pubArgs += "-p:PublishAot=true"
    Write-Host "==> NativeAOT enabled (smallest EXE, requires .NET 8+)" -ForegroundColor Cyan
}

Write-Host "==> dotnet publish" -ForegroundColor Cyan
dotnet @pubArgs
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }

$binPath = Join-Path (Split-Path $Project -Parent) "bin/$Configuration/net8.0/$Rid/publish"
Write-Host "==> Output: $binPath" -ForegroundColor Green
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow


