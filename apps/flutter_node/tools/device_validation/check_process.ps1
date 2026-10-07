param([string]$Serial = "")
$adbArgs = @()
if ($Serial) { $adbArgs += @("-s", $Serial) }
adb @adbArgs shell pidof com.example.sound_detector_clean
adb @adbArgs shell dumpsys meminfo com.example.sound_detector_clean

