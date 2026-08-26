# Build MSIX sample with full self-contained publish + manual packaging.
#
# This is the CLI path (no Visual Studio required).
# 1. dotnet publish produces the WPF EXE + DLLs.
# 2. MakeAppx.exe packages the publish output into an .msix.
# 3. signtool signs the .msix with the supplied cert.
#
# Usage:
#   powershell -File build_msix.ps1 -CertPath cert.pfx -CertPassword (Read-Host -AsSecureString)

[CmdletBinding()]
param(
    [string] $AppDir = "package\AppX",
    [string] $CertPath = "",
    [string] $CertPassword = "",
    [string] $OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

# 1. Publish the WPF project self-contained.
Write-Host "==> dotnet publish (self-contained)" -ForegroundColor Cyan
dotnet publish .\app\MsixSample.csproj -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=false -p:WindowsAppSDKSelfContained=true `
    -o "$AppDir"
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }

# 2. Copy AppxManifest + assets into AppX.
Copy-Item package\Package.appxmanifest "$AppDir\"
Copy-Item -Recurse package\Assets "$AppDir\" -ErrorAction SilentlyContinue

# 3. Locate MakeAppx + signtool from the Windows SDK.
$sdk = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\MakeAppx.exe" -ErrorAction SilentlyContinue |
       Select-Object -First 1 -ExpandProperty FullName
$signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
if (-not $sdk)   { throw "MakeAppx.exe not found; install Windows SDK 10.0.22621 or later." }
if (-not $signtool) { throw "signtool.exe not found; install Windows SDK signing tools." }

if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory $OutputDir | Out-Null }
$msix = Join-Path $OutputDir "MsixSample.msix"
if (Test-Path $msix) { Remove-Item $msix -Force }

# 4. MakeAppx pack
Write-Host "==> MakeAppx.exe pack" -ForegroundColor Cyan
& $sdk pack /d $AppDir /p $msix
if ($LASTEXITCODE -ne 0) { throw "MakeAppx pack failed" }

# 5. Sign
if ($CertPath -and (Test-Path $CertPath)) {
    Write-Host "==> signtool.exe sign + verify" -ForegroundColor Cyan
    & $signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
        /f $CertPath /p $CertPassword $msix
    if ($LASTEXITCODE -ne 0) { throw "signtool sign failed" }
    & $signtool verify /pa $msix
} else {
    Write-Host "==> Skipping signing (no -CertPath provided)" -ForegroundColor Yellow
}

Write-Host "==> Built: $msix" -ForegroundColor Green
Write-Host "Next: sideload via Add-AppxPackage, or upload to the Microsoft Store." -ForegroundColor Yellow
