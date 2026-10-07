param(
    [string]$Serial = "",
    [string]$OutputDir = "C:\sound_backend\artifacts\device_logs"
)
$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$outFile = Join-Path $OutputDir "bugreport_$timestamp.zip"
$adbArgs = @()
if ($Serial) { $adbArgs += @("-s", $Serial) }
adb @adbArgs bugreport $outFile

