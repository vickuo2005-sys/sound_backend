# Real Device Execution Guide

Use the scripts in `C:\Users\vicku\sound_detector_clean\tools\device_validation`.

## Device Matrix

For each node:

- Install the same APK.
- Confirm node id.
- Confirm foreground service notification.
- Confirm GPS permission.
- Confirm microphone permission.
- Confirm backend WebSocket connection.

## Test Cases

| Case | Steps | Expected Result | Evidence |
|---|---|---|---|
| 30 minutes screen on | Start node and leave screen on | heartbeat and GPS continue | logcat |
| 30 minutes screen off | Turn screen off | foreground service remains active | logcat + device status |
| Network switch | Toggle Wi-Fi/mobile | reconnect then heartbeat resumes | logcat |
| Backend restart | Restart staging backend | node reconnects or polling fallback resumes | logs |
| Offline event retry | Disable network, trigger event, re-enable | event uploads once | app log |
| Dashboard command | Start/stop detection | ACK and result appear | dashboard + logs |
| Live audio | Enable live audio canary | frame counter increases, manual audio check | dashboard |

Codex cannot mark these as Pass without physical-device evidence.

