# heavy_desktop_verify.ps1 -- sample a desktop app's cold start, memory, and CPU.
#
# Usage:
#   powershell -File scripts/heavy_desktop_verify.ps1 -AppPath .\dist\MyApp.exe -SampleSeconds 60
#   powershell -File scripts/heavy_desktop_verify.ps1 -ProcessName MyApp -SampleSeconds 30 -OutputJson report.json
#   powershell -File scripts/heavy_desktop_verify.ps1 -SelfTest
#
# With -AppPath the script starts the app, waits for a main window, samples
# the process, and reports working set / private memory / CPU. Use
# -ProcessName to attach to an already-running app. -StopAfterSample closes
# only processes that this script started.

[CmdletBinding()]
param(
    [string] $AppPath = "",
    [string] $ProcessName = "",
    [int] $StartupTimeoutSec = 30,
    [int] $SampleSeconds = 10,
    [int] $SampleIntervalMs = 500,
    [string] $OutputJson = "",
    [switch] $SelfTest,
    [switch] $StopAfterSample
)

$ErrorActionPreference = "Stop"

function Get-TargetProcess {
    param([string] $Path, [string] $Name)
    if ($Name) {
        $proc = Get-Process -Name $Name -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $proc) { throw "No process named '$Name' is running." }
        return $proc
    }
    if ($Path) {
        if (-not (Test-Path -LiteralPath $Path)) { throw "AppPath not found: $Path" }
        return Start-Process -FilePath (Resolve-Path -LiteralPath $Path).Path -PassThru
    }
    throw "Provide -AppPath or -ProcessName."
}

function Get-ProcessSnapshot {
    param($Process)
    $Process.Refresh()
    [pscustomobject]@{
        WorkingSetMB = [math]::Round($Process.WorkingSet64 / 1MB, 1)
        PrivateMemoryMB = [math]::Round($Process.PrivateMemorySize64 / 1MB, 1)
        CpuSeconds = $Process.TotalProcessorTime.TotalSeconds
    }
}

function New-HeavyDesktopResult {
    param(
        [string] $AppPath,
        [string] $ProcessName,
        [double] $ColdStartMs,
        [double] $SampleSeconds,
        [object[]] $Samples,
        [double] $CpuPercent,
        [bool] $StartedHere
    )
    $avgWorkingSet = ($Samples | Measure-Object -Property WorkingSetMB -Average).Average
    $peakWorkingSet = ($Samples | Measure-Object -Property WorkingSetMB -Maximum).Maximum
    $avgPrivate = ($Samples | Measure-Object -Property PrivateMemoryMB -Average).Average
    [pscustomobject]@{
        AppPath = $AppPath
        ProcessName = $ProcessName
        ColdStartMs = [math]::Round($ColdStartMs, 0)
        SampleSeconds = [math]::Round($SampleSeconds, 1)
        AvgWorkingSetMB = [math]::Round($avgWorkingSet, 1)
        PeakWorkingSetMB = [math]::Round($peakWorkingSet, 1)
        AvgPrivateMemoryMB = [math]::Round($avgPrivate, 1)
        CpuPercent = [math]::Round($CpuPercent, 1)
        StartedHere = $StartedHere
    }
}

if ($SelfTest) {
    Write-Host "==> heavy_desktop_verify.ps1 self-test" -ForegroundColor Cyan
    $proc = Get-Process -Id $PID
    $samples = @()
    foreach ($i in 1..3) {
        $samples += Get-ProcessSnapshot -Process $proc
        Start-Sleep -Milliseconds 50
    }
    $result = New-HeavyDesktopResult -AppPath "" -ProcessName $proc.ProcessName `
        -ColdStartMs 0 -SampleSeconds 0 -Samples $samples -CpuPercent 0 -StartedHere $false
    $result | Format-List
    Write-Host "Self-test OK" -ForegroundColor Green
    exit 0
}

$startedHere = [bool]$AppPath
$proc = Get-TargetProcess -Path $AppPath -Name $ProcessName

$sw = [System.Diagnostics.Stopwatch]::StartNew()
if ($startedHere) {
    while ($sw.Elapsed.TotalSeconds -lt $StartupTimeoutSec) {
        $proc.Refresh()
        if ($proc.MainWindowHandle -ne 0) { break }
        Start-Sleep -Milliseconds 200
    }
}
$coldStartMs = $sw.Elapsed.TotalMilliseconds

if ($SampleSeconds -lt 1) { $SampleSeconds = 1 }
if ($SampleIntervalMs -lt 50) { $SampleIntervalMs = 50 }
$count = [int][math]::Floor(($SampleSeconds * 1000) / $SampleIntervalMs)
if ($count -lt 1) { $count = 1 }

$first = Get-ProcessSnapshot -Process $proc
$samples = @($first)
for ($i = 1; $i -lt $count; $i++) {
    Start-Sleep -Milliseconds $SampleIntervalMs
    $samples += Get-ProcessSnapshot -Process $proc
}
$last = $samples[-1]
$wallSec = ($count * $SampleIntervalMs) / 1000.0
$cpuPercent = if ($wallSec -gt 0) {
    (($last.CpuSeconds - $first.CpuSeconds) / $wallSec) * 100
} else {
    0
}

$result = New-HeavyDesktopResult -AppPath $AppPath -ProcessName $proc.ProcessName `
    -ColdStartMs $coldStartMs -SampleSeconds $wallSec -Samples $samples `
    -CpuPercent $cpuPercent -StartedHere $startedHere

if ($OutputJson) {
    $outFull = [System.IO.Path]::GetFullPath($OutputJson)
    $outDir = Split-Path -Parent $outFull
    if ($outDir -and -not (Test-Path -LiteralPath $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }
    $json = $result | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($outFull, $json, [System.Text.UTF8Encoding]::new($false))
    Write-Host "==> Report written: $outFull" -ForegroundColor Green
}

$result | Format-List
Write-Host "Next: compare cold start / memory / CPU against Step 0 budgets." -ForegroundColor Yellow

if ($StopAfterSample -and $startedHere) {
    Stop-Process -Id $proc.Id -Force
    Write-Host "==> Stopped sampled process (StopAfterSample)." -ForegroundColor Yellow
}
