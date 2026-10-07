Get-Process adb -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "*adb*" } |
    Stop-Process -Force

