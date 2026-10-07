param([string]$Serial = "")
$adbArgs = @()
if ($Serial) { $adbArgs += @("-s", $Serial) }
adb @adbArgs shell dumpsys connectivity

