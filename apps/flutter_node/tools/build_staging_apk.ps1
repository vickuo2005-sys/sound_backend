param(
    [string]$ConfigPath = "config\staging.local.json",
    [Parameter(Mandatory = $true)]
    [string]$ApprovedStagingHost
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

& "$PSScriptRoot\validate_flutter_config.ps1" `
    -ConfigPath $ConfigPath `
    -Environment staging `
    -ApprovedStagingHost $ApprovedStagingHost

dart run tools/validate_field_staging_config.dart `
    $ConfigPath `
    --approved-host `
    $ApprovedStagingHost
if ($LASTEXITCODE -ne 0) {
    throw "Field staging validation failed."
}

flutter pub get
dart format --output=none --set-exit-if-changed .
flutter analyze
flutter test
flutter build apk --flavor staging --release --dart-define-from-file=$ConfigPath

$apkPath = Join-Path $projectRoot "build\app\outputs\flutter-apk\app-staging-release.apk"
if (-not (Test-Path -LiteralPath $apkPath)) {
    throw "Staging APK not found: $apkPath"
}

$hash = (Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash.ToLowerInvariant()
$size = (Get-Item -LiteralPath $apkPath).Length
Write-Output "STAGING_APK=$apkPath"
Write-Output "STAGING_APK_SIZE_BYTES=$size"
Write-Output "STAGING_APK_SHA256=$hash"
