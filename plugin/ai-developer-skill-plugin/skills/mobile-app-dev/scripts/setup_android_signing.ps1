<#
.SYNOPSIS
    Set up Android upload keystore and write key.properties.

.DESCRIPTION
    Generates an upload keystore (~/.keystores/upload.jks) and writes
    a key.properties file in the Android project root that Gradle
    reads to find the keystore. NEVER commit the keystore or
    key.properties.

.PARAMETER ProjectDir
    Android project root. Defaults to ./android.

.PARAMETER Alias
    Keystore alias. Defaults to 'upload'.

.PARAMETER ValidityDays
    Keystore validity in days. Default 10000 (~27 years).

.PARAMETER NonInteractive
    Skip all prompts; fail if any input is missing.

.EXAMPLE
    pwsh setup_android_signing.ps1 -ProjectDir ./android

.EXAMPLE
    pwsh setup_android_signing.ps1 -ProjectDir ./android -NonInteractive
#>

[CmdletBinding()]
param(
    [string] $ProjectDir = "./android",
    [string] $Alias = "upload",
    [int] $ValidityDays = 10000,
    [switch] $NonInteractive
)

$ErrorActionPreference = "Stop"

# ---- Guard: keytool present ---------------------------------------------
if (-not (Get-Command keytool -ErrorAction SilentlyContinue)) {
    throw "keytool not on PATH. Install JDK 17+."
}

# ---- Resolve keystore path ---------------------------------------------
$keystoreDir = if ($env:KEYSTORE_DIR) { $env:KEYSTORE_DIR } else { "$env:USERPROFILE\.keystores" }
if (-not (Test-Path $keystoreDir)) {
    New-Item -ItemType Directory -Force -Path $keystoreDir | Out-Null
    Write-Host "Created $keystoreDir" -ForegroundColor Yellow
}
$keystorePath = Join-Path $keystoreDir "upload.jks"

if ((Test-Path $keystorePath) -and -not $NonInteractive) {
    Write-Warning "Keystore already exists at $keystorePath. Re-using."
} elseif ((Test-Path $keystorePath) -and $NonInteractive) {
    throw "Keystore already exists at $keystorePath. Refusing to overwrite in NonInteractive mode."
}

# ---- Prompt for passwords (or use env vars) -----------------------------
$storePass = $env:KEYSTORE_STORE_PASSWORD
$keyPass   = $env:KEYSTORE_KEY_PASSWORD

if (-not $storePass -and -not $NonInteractive) {
    $secure = Read-Host -AsSecureString "Keystore store password"
    $storePass = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}
if (-not $keyPass -and -not $NonInteractive) {
    $secure = Read-Host -AsSecureString "Key password (press Enter to use store password)"
    $keyPass = if ($secure.Length -eq 0) { $storePass } else {
        [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    }
}
if ($NonInteractive -and (-not $storePass -or -not $keyPass)) {
    throw "NonInteractive mode requires KEYSTORE_STORE_PASSWORD and KEYSTORE_KEY_PASSWORD env vars."
}
if (-not $storePass) { $storePass = "android" }
if (-not $keyPass)   { $keyPass   = $storePass }

# ---- Generate keystore --------------------------------------------------
if (-not (Test-Path $keystorePath)) {
    Write-Host "==> keytool -genkey" -ForegroundColor Cyan
    & keytool -genkey -v `
        -keystore $keystorePath `
        -keyalg RSA -keysize 2048 `
        -validity $ValidityDays `
        -alias $Alias `
        -storepass $storePass `
        -keypass $keyPass `
        -dname "CN=Upload Key, OU=Engineering, O=MyApp, L=City, S=State, C=US"
    if ($LASTEXITCODE -ne 0) { throw "keytool -genkey failed." }
}

# ---- Write key.properties -----------------------------------------------
$propsPath = Join-Path $ProjectDir "key.properties"

if ((Test-Path $propsPath) -and $NonInteractive) {
    Write-Warning "key.properties already exists at $propsPath. Refusing to overwrite in NonInteractive mode."
} elseif (Test-Path $propsPath) {
    Write-Warning "key.properties already exists at $propsPath. Skipping write."
} else {
    $storeFilePath = $keystorePath.Replace('\', '/')
    $props = @"
storeFile=$storeFilePath
storePassword=$storePass
keyAlias=$Alias
keyPassword=$keyPass
"@
    [System.IO.File]::WriteAllText($propsPath, $props, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Wrote $propsPath" -ForegroundColor Green
}

# ---- Done ---------------------------------------------------------------
Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Keystore:    $keystorePath" -ForegroundColor Cyan
Write-Host "key.properties: $propsPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "Add to .gitignore (BOTH lines):" -ForegroundColor Yellow
Write-Host "  *.jks"
Write-Host "  key.properties"
Write-Host ""
Write-Host "Backup this keystore now -- losing it means you cannot upload" -ForegroundColor Red
Write-Host "updates to the existing Play Store listing." -ForegroundColor Red
Write-Host "Recommended: store in 1Password / Bitwarden + encrypted Git repo." -ForegroundColor Red
