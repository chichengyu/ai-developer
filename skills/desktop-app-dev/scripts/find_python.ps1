# find_python.ps1 -- shared Python interpreter discovery for skill scripts.
#
# Order:
#   1. -Explicit path (passed by the caller, e.g. build_python.ps1 -PythonExe)
#   2. $env:CODEX_PYTHON
#   3. $env:PYTHON
#   4. Codex primary runtime under $HOME\.cache (only if present)
#   5. python / python3 / py on PATH
#
# Dot-source this file, then call Get-ProjectPython.

function Get-ProjectPython {
    param([string] $Explicit = "")

    $candidates = @()
    if ($Explicit) { $candidates += $Explicit }
    if ($env:CODEX_PYTHON) { $candidates += $env:CODEX_PYTHON }
    if ($env:PYTHON) { $candidates += $env:PYTHON }

    $codexRt = Join-Path $HOME ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
    if (Test-Path -LiteralPath $codexRt) { $candidates += $codexRt }

    foreach ($name in @("python", "python3", "py")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { $candidates += $cmd.Source }
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    return ""
}
