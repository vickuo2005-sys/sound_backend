param([string]$Serial = "")
$ErrorActionPreference = "Stop"
$adbArgs = @()
if ($Serial) { $adbArgs += @("-s", $Serial) }
adb @adbArgs devices
adb @adbArgs shell getprop ro.product.model
adb @adbArgs shell getprop ro.build.version.release

