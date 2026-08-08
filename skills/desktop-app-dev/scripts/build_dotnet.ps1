# build_dotnet.ps1 -- .NET self-contained single-file publish (size-lean by default; R2R / trim opt-in).
# Usage: powershell -File build_dotnet.ps1 -Project src/MyApp/MyApp.csproj -Rid win-x64
#        powershell -File build_dotnet.ps1 -Project src/MyApp/MyApp.csproj -BackupSource
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Project,
    [ValidateSet("win-x64", "win-arm64", "win-x86")]
    [Alias("Arch")]
    [string] $Rid = "win-x64",
    [string] $Configuration = "Release",
    [switch] $NativeAot,             # NativeAOT publish (smaller, no JIT)
    [switch] $ReadyToRun,            # opt-in R2R; adds size, improves cold start
    [switch] $Trim,                  # opt-in trimming; may break reflection-heavy code
    [ValidateSet("copyused", "partial", "full")]
    [string] $TrimMode = "partial",
    [bool] $InvariantGlobalization = $true,   # drop ICU data; disable for localized apps
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
    "-p:IncludeNativeLibrariesForSelfExtract=true",
    "-p:EnableCompressionInSingleFile=true",
    "-p:DebugType=None",
    "-p:DebugSymbols=false"
)
if ($OutputDir) {
    $pubArgs += "-o"
    $pubArgs += $OutputDir
}

if ($InvariantGlobalization) {
    $pubArgs += "-p:InvariantGlobalization=true"
}
if ($Trim) {
    $pubArgs += "-p:PublishTrimmed=true"
    $pubArgs += "-p:TrimMode=$TrimMode"
}
if ($NativeAot) {
    $pubArgs += "-p:PublishAot=true"
    $pubArgs += "-p:OptimizationPreference=Size"
    $pubArgs += "-p:IlcOptimizationPreference=Size"
    Write-Host "==> NativeAOT enabled (smallest EXE, requires .NET 8+)" -ForegroundColor Cyan
} elseif ($ReadyToRun) {
    $pubArgs += "-p:PublishReadyToRun=true"
    Write-Host "==> ReadyToRun enabled (larger EXE, faster cold start)" -ForegroundColor Cyan
} else {
    Write-Host "==> Size-optimized publish: compression on, symbols off, no R2R. Pass -ReadyToRun to opt in." -ForegroundColor Cyan
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
$exe = Get-ChildItem -Path $binPath -Filter *.exe -ErrorAction SilentlyContinue |
       Select-Object -First 1
if ($exe) {
    $size = $exe.Length
    Write-Host ("==> Output: {0}  ({1:N1} MB / {2:N0} KB)" -f $exe.FullName, ($size / 1MB), ($size / 1KB)) -ForegroundColor Green
} else {
    Write-Host "==> Output: $binPath" -ForegroundColor Green
}
Write-Host "Next: sign with signtool, then test on a clean Windows VM." -ForegroundColor Yellow


