param(
    [string]$OutputDirectory = "android\signing",
    [string]$Alias = "sound-detector-release",
    [int]$ValidityDays = 10000
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$keytool = Get-Command keytool.exe -ErrorAction SilentlyContinue
if (-not $keytool) {
    $keytool = Get-Command keytool -ErrorAction SilentlyContinue
}
if (-not $keytool) {
    throw "keytool not found. Install a JDK before generating a release keystore."
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$keystorePath = Join-Path $OutputDirectory "sound-detector-release.jks"
if (Test-Path -LiteralPath $keystorePath) {
    throw "Keystore already exists. Refusing to overwrite: $keystorePath"
}

Write-Output "This script creates a local keystore file. Do not commit it to Git."
$storePassword = Read-Host "Keystore password" -AsSecureString
$keyPassword = Read-Host "Key password" -AsSecureString
$storePasswordText = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($storePassword))
$keyPasswordText = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($keyPassword))

& $keytool.Source -genkeypair `
    -v `
    -keystore $keystorePath `
    -storetype JKS `
    -keyalg RSA `
    -keysize 2048 `
    -validity $ValidityDays `
    -alias $Alias `
    -storepass $storePasswordText `
    -keypass $keyPasswordText `
    -dname "CN=Sound Detector, OU=Node, O=Sound Detector, L=Taipei, ST=Taiwan, C=TW"

$keyPropertiesPath = "android\key.properties"
@"
storePassword=$storePasswordText
keyPassword=$keyPasswordText
keyAlias=$Alias
storeFile=signing/sound-detector-release.jks
"@ | Set-Content -LiteralPath $keyPropertiesPath -Encoding UTF8

Write-Output "Keystore created: $keystorePath"
Write-Output "key.properties created: $keyPropertiesPath"
Write-Output "Keep both files local and secret."
