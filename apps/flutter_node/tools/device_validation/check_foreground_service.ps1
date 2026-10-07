param([string]$Serial = "")
$adbArgs = @()
if ($Serial) { $adbArgs += @("-s", $Serial) }
adb @adbArgs shell dumpsys activity services com.example.sound_detector_clean | Select-String "SoundNodeForegroundService|foreground"

