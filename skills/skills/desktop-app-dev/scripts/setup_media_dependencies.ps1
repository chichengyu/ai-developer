# setup_media_dependencies.ps1 -- check or install the media pipeline runtime.
#
# Default is check-only. Pass -Install to actually download/install:
#   powershell -File scripts/setup_media_dependencies.ps1
#   powershell -File scripts/setup_media_dependencies.ps1 -Install

[CmdletBinding()]
param(
    [switch] $Install,
    [string] $RuntimeDir = "",
    [string] $FfmpegUrl = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $PSScriptRoot "find_python.ps1")
$py = Get-ProjectPython
if (-not $py) {
    throw "python not found. Set CODEX_PYTHON or PYTHON, or add python to PATH."
}

$argsList = @()
if ($Install) {
    $argsList += "--install"
}
if ($RuntimeDir) {
    $argsList += "--runtime-dir"
    $argsList += $RuntimeDir
}
if ($FfmpegUrl) {
    $argsList += "--ffmpeg-url"
    $argsList += $FfmpegUrl
}

Write-Host "==> media dependencies $($(if ($Install) { 'install' } else { 'check' }))"
& $py (Join-Path $root "media_dependencies.py") @argsList
exit $LASTEXITCODE
