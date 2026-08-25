# Android Release Signing Guide

This guide prepares release signing without storing secrets in Git.

## Files

Flutter project:

- `C:\Users\vicku\sound_detector_clean\android\key.properties.example`
- `C:\Users\vicku\sound_detector_clean\android\key.properties`
- `C:\Users\vicku\sound_detector_clean\android\signing\sound-detector-release.jks`

Only the `.example` file is safe to keep in version control.

## Create Local Keystore

From the Flutter project root:

```powershell
tools\generate_release_keystore.ps1
```

The script prompts for passwords, writes a local keystore, and creates
`android\key.properties`. Do not commit either file.

## key.properties Format

```properties
storePassword=
keyPassword=
keyAlias=
storeFile=signing/sound-detector-release.jks
```

`storeFile` is resolved relative to `C:\Users\vicku\sound_detector_clean\android`.

## Build Rules

- Staging APK may be debug-signed for internal testing only.
- Production APK must be release-signed.
- Production build script blocks when `android\key.properties` or the keystore is missing.
- Production APK must be checked with `tools\verify_apk_signing.ps1 -Production`.

## Commands

```powershell
tools\build_staging_apk.ps1 -ConfigPath config\staging.local.json
tools\build_production_apk.ps1 -ConfigPath config\production.local.json
tools\verify_apk_signing.ps1 -ApkPath build\app\outputs\flutter-apk\app-production-release.apk -Production
```

## Recovery

If the keystore is lost, existing release updates using that signing identity
cannot be installed as an update over previous signed builds. Back up the
keystore outside the repository and restrict access.
