param(
    [string]$ConfigPath = "config\production.local.json"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

& "$PSScriptRoot\validate_flutter_config.ps1" -ConfigPath $ConfigPath -Environment production

$keyPropertiesPath = Join-Path $projectRoot "android\key.properties"
if (-not (Test-Path -LiteralPath $keyPropertiesPath)) {
    throw "BLOCKED: android\key.properties is required for production release signing."
}

$keyProps = @{}
Get-Content -LiteralPath $keyPropertiesPath | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+?)\s*=\s*(.*)$") {
        $keyProps[$matches[1].Trim()] = $matches[2].Trim()
    }
}
foreach ($required in @("storeFile", "storePassword", "keyAlias", "keyPassword")) {
    if (-not $keyProps.ContainsKey($required) -or [string]::IsNullOrWhiteSpace($keyProps[$required])) {
        throw "BLOCKED: android\key.properties is missing '$required'."
    }
}

$storeFile = $keyProps["storeFile"]
if (-not [System.IO.Path]::IsPathRooted($storeFile)) {
    $storeFile = Join-Path (Join-Path $projectRoot "android") $storeFile
}
if (-not (Test-Path -LiteralPath $storeFile)) {
    throw "BLOCKED: release keystore file not found."
}

$previousRequireSigning = $env:ORG_GRADLE_PROJECT_REQUIRE_RELEASE_SIGNING
$env:ORG_GRADLE_PROJECT_REQUIRE_RELEASE_SIGNING = "true"
try {
    flutter pub get
    dart format --output=none --set-exit-if-changed .
    flutter analyze
    flutter test
    flutter build apk --flavor production --release --dart-define-from-file=$ConfigPath
} finally {
    if ($null -eq $previousRequireSigning) {
        Remove-Item Env:\ORG_GRADLE_PROJECT_REQUIRE_RELEASE_SIGNING -ErrorAction SilentlyContinue
    } else {
        $env:ORG_GRADLE_PROJECT_REQUIRE_RELEASE_SIGNING = $previousRequireSigning
    }
}

$apkPath = Join-Path $projectRoot "build\app\outputs\flutter-apk\app-production-release.apk"
if (-not (Test-Path -LiteralPath $apkPath)) {
    throw "Production APK not found: $apkPath"
}

$hash = (Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash.ToLowerInvariant()
$size = (Get-Item -LiteralPath $apkPath).Length
Write-Output "PRODUCTION_APK=$apkPath"
Write-Output "PRODUCTION_APK_SIZE_BYTES=$size"
Write-Output "PRODUCTION_APK_SHA256=$hash"
