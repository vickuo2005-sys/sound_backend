# Flutter Android node: realtime inference state

This directory imports the Flutter project at source commit
`cc9b4091479859e6065f79910170cd9f9869943b`. The backend files at the repository
root retain their original contents. Run Flutter commands from this directory.

Each successful inference in the current listening session publishes the
existing operational target decision through the existing Node WebSocket:
`/ws/node/{device_id}`, using `message_type: status_update` and
`payload.detection_state`. No event admission, database write, or audio upload
must complete before this state is published.

```json
{
  "detection_state": {
    "active": true,
    "sequence": 1,
    "observed_at_ms": 1791339000000,
    "label": "Drone",
    "confidence": 0.87
  }
}
```

The next non-target inference publishes `active: false`. Repeated positive or
negative inferences each allocate a new sequence. The counter survives service
recreation within the app process. Offline operation retains only the latest
state; an authenticated reconnection republishes it with a new sequence and the
original observation timestamp. A blocked sender has one in-flight send and one
replaceable pending state, rather than an unbounded replay queue.

Manual/remote stop and microphone error paths publish false and invalidate old
inference sessions. Target policy, event cooldown, observation retry, durable
event upload, audio upload, and model thresholds remain unchanged. Audio windows
below the existing candidate threshold do not run inference; these skipped
windows are not reported as completed inference results.

## Validation and build

The source project passed `flutter analyze` and all 107 `flutter test` tests.
The staging release APK built successfully. Tests include a real local
WebSocket server, true/false frames, repeated states, reconnect, stop, offline
buffering, sequence continuity, transport failure, and existing upload queues.

```powershell
flutter pub get
flutter analyze
flutter test
```

For a staging APK, create your own ignored `config/staging.local.json` using
`config/staging.example.json`, supply the staging endpoint and credentials
locally, and run the existing script:

```powershell
./tools/build_staging_apk.ps1 -ConfigPath config/staging.local.json -ApprovedStagingHost sound-backend-staging.onrender.com
```

Local configuration, signing material, APKs, device logs, recordings, and
uncommitted source-project changes are not part of this import.

## Android recording recovery

One staging device had an old `Music/sound_events` folder owned by a previous
installation's UID. Opening a new WAV failed with `EACCES`; the existing
`audio_error` callback made listening appear stopped although the process was
still alive. The native read/process and sliding-window-save catches now log
the original exception under `SoundNodeAudio` instead of hiding its cause.

That device's recordings were backed up and its old directory retained under a
backup name. The app created a new directory under its current UID. More than
100 consecutive audio windows then saved with zero audio errors. This is a
device recovery result, not an automatic directory migration implemented in
the app. Full inference-to-staging-Dashboard behavior still requires physical
verification with suitable sound input.
