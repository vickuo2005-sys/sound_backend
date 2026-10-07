param(
    [string]$Serial = "",
    [string]$OutputDir = "C:\sound_backend\artifacts\device_logs"
)
$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$outFile = Join-Path $OutputDir "logcat_$timestamp.txt"
$adbArgs = @()
if ($Serial) { $adbArgs += @("-s", $Serial) }
adb @adbArgs logcat -c
adb @adbArgs logcat | Tee-Object -FilePath $outFile

