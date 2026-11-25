# Flutter Git Initialization Runbook

The Flutter project is currently not a Git repository. Do not initialize or
commit automatically during blocker remediation.

Project path:

`C:\Users\vicku\sound_detector_clean`

## Recommended Ignore Rules

Start from:

`C:\Users\vicku\sound_detector_clean\.gitignore.release-proposal`

Also ensure these are ignored:

- `build/`
- `.dart_tool/`
- `.idea/`
- `.vscode/`
- `android/.gradle/`
- `android/local.properties`
- `android/key.properties`
- `android/signing/`
- `*.jks`
- `*.keystore`
- `config/*.local.json`
- generated APK files
- device logs, bugreports, and test evidence
- pending local audio files

## Files Usually Included

- `lib/`
- `test/`
- `android/app/src/`
- `android/app/build.gradle.kts`
- `pubspec.yaml`
- `pubspec.lock`
- `config/*.example.json`
- source scripts in `tools/`

## Manual Commands

Use explicit adds only:

```powershell
cd C:\Users\vicku\sound_detector_clean
git init
git status --short
git add lib
git add test
git add android/app/src
git add android/app/build.gradle.kts
git add android/key.properties.example
git add pubspec.yaml pubspec.lock
git add config/*.example.json
git add tools/*.ps1
git status --short
```

Do not use:

```powershell
git add .
```

Review ignored files:

```powershell
git check-ignore -v android/key.properties
git check-ignore -v config/staging.local.json
git check-ignore -v build/app/outputs/flutter-apk/app-staging-release.apk
```
