param(
    [string]$Serial = "",
    [string]$ApkPath = "C:\Users\vicku\sound_detector_clean\build\app\outputs\flutter-apk\app-release.apk"
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ApkPath)) { throw "APK not found: $ApkPath" }
$adbArgs = @()
if ($Serial) { $adbArgs += @("-s", $Serial) }
adb @adbArgs install -r $ApkPath

