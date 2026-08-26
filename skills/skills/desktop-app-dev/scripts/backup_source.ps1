# backup_source.ps1 -- create a timestamped zip of the project source before packaging.
#
# Usage:
#   powershell -File scripts/backup_source.ps1 -SourcePath . -OutputDir dist\source_backup -Name MyApp

[CmdletBinding()]
param(
    [string] $SourcePath = (Get-Location).Path,
    [string] $OutputDir = "dist\source_backup",
    [string] $Name = "app",
    [string[]] $Exclude = @()
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $SourcePath)) {
    throw "Source path not found: $SourcePath"
}

$rootPath = (Resolve-Path -LiteralPath $SourcePath).Path
$excludeSegments = @(
    ".git", "node_modules", "target", "bin", "obj", "dist", "build", "source_backup",
    "__pycache__", ".venv", ".mypy_cache", ".ruff_cache", ".pytest_cache"
) + $Exclude

$outputPath = [System.IO.Path]::GetFullPath($OutputDir)
$outputRel = ""
if ($outputPath.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    $outputRel = $outputPath.Substring($rootPath.Length).TrimStart("\", "/")
}

$files = Get-ChildItem -LiteralPath $rootPath -Recurse -File | Where-Object {
    $rel = $_.FullName.Substring($rootPath.Length).TrimStart("\", "/")
    $segments = @($rel -split '[\\/]' | Where-Object { $_ })
    $skip = $false
    if ($outputRel -and ($rel -eq $outputRel -or $rel.StartsWith($outputRel + "/") -or $rel.StartsWith($outputRel + "\"))) {
        $skip = $true
    }
    if (-not $skip) {
        foreach ($seg in $excludeSegments) {
            if ($segments -contains $seg) {
                $skip = $true
                break
            }
        }
    }
    -not $skip
}

if (-not $files) {
    throw "No source files found under $rootPath"
}

$stage = Join-Path $env:TEMP ("source-backup-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $stage | Out-Null
try {
    foreach ($file in $files) {
        $rel = $file.FullName.Substring($rootPath.Length).TrimStart("\", "/")
        $dest = Join-Path $stage $rel
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $dest
    }

    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $zip = Join-Path $OutputDir ("{0}_source_{1}.zip" -f $Name, $stamp)
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip
    Write-Host "==> Source backup: $zip" -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
