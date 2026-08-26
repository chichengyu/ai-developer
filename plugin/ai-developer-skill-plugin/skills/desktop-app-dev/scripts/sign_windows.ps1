# sign_windows.ps1 -- SHA256 + RFC3161 code signing for a Windows binary.
#
# Usage:
#   powershell -File scripts/sign_windows.ps1 -File .\dist\MyApp.exe -CertThumbprint <sha1>
#   powershell -File scripts/sign_windows.ps1 -File .\dist\MyApp.exe -CertPath .\cert.pfx -CertPassword <pw>

[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $File,
    [string] $CertThumbprint = "",
    [string] $CertPath = "",
    [string] $CertPassword = "",
    [string] $TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $File)) {
    throw "File not found: $File"
}

$signtool = Get-Command signtool -ErrorAction SilentlyContinue
if (-not $signtool) {
    $candidates = @(
        "$env:ProgramFiles (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe",
        "$env:ProgramFiles (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe"
    )
    $signtool = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $signtool) {
        throw "signtool not found. Install the Windows SDK or add it to PATH."
    }
}
$signtoolPath = if ($signtool -is [System.Management.Automation.CommandInfo]) {
    $signtool.Source
} else {
    [string] $signtool
}

$argsList = @("sign", "/fd", "SHA256", "/tr", $TimestampUrl, "/td", "SHA256")
if ($CertThumbprint) { $argsList += "/sha1"; $argsList += $CertThumbprint }
if ($CertPath) {
    if (-not (Test-Path -LiteralPath $CertPath)) { throw "Cert file not found: $CertPath" }
    $argsList += "/f"; $argsList += $CertPath
    if ($CertPassword) { $argsList += "/p"; $argsList += $CertPassword }
}
if (-not $CertThumbprint -and -not $CertPath) { $argsList += "/a" }
$argsList += $File

& $signtoolPath @argsList
if ($LASTEXITCODE -ne 0) { throw "signtool failed with exit code $LASTEXITCODE" }

Write-Host "==> Signed: $File" -ForegroundColor Green
