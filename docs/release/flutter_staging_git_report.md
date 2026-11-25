# Flutter Staging Git Report

Date: 2026-07-24  
Project: `C:\Users\vicku\sound_detector_clean`  
Branch: `staging`  
Remote: None configured. No push was performed.

## Local Git Initialization

| Item | Result |
| --- | --- |
| Git repo initialized | Yes |
| Branch | `staging` |
| Local author | `vickuo2005-sys <vickuo2005-sys@users.noreply.github.com>` |
| Remote configured | No |
| Push performed | No |

## Local Commits

| Commit | Group | Message |
| --- | --- | --- |
| `6dfa77e` | Flutter runtime | `feat: add Flutter staging node runtime` |
| `0b8ec4c` | Android native and flavors | `feat(android): add staging flavor and foreground service` |
| `3c43f5a` | Tests | `test: add Flutter validation tests` |
| `1fb3b7d` | Config and build tools | `chore(staging): add Flutter config and build tools` |
| `8fe6be2` | Ignore generated outputs | `chore: ignore generated Flutter outputs` |

## Guardrail Checks

| Check | Result |
| --- | --- |
| `config/*.local.json` committed | No |
| `android/local.properties` committed | No |
| `android/key.properties` committed | No |
| keystore/JKS committed | No |
| APK committed | No |
| `build/` committed | No |
| `.dart_tool/` committed | No |
| generated `outputs/` committed | No |

## Validation

| Command | Result |
| --- | --- |
| `dart format --output=none --set-exit-if-changed .` | Pass |
| `flutter analyze` | Pass |
| `flutter test` | Pass, 22 tests |
| `tools\validate_flutter_config.ps1 -ConfigPath config\staging.local.json -Environment staging` | Pass |

## Staging APK Artifact

| Field | Value |
| --- | --- |
| Path | `C:\Users\vicku\sound_detector_clean\build\app\outputs\flutter-apk\app-staging-release.apk` |
| Size | `174838569` bytes |
| SHA-256 | `42535146e859677e63680696c9748fe173b3dbb8199a5ed36657e171cea9e2b1` |
| applicationId | `com.example.sound_detector_clean.staging` |
| versionName | `1.0.0-staging` |
| versionCode | `1` |
| Certificate SHA-256 | `36545ed91eaaaebdc564417abb39252c639385d9939716c441e6b29d5fc7ec04` |
| Signing classification | Internal test signing, Android Debug certificate |
| Backend host | `sound-backend-staging.onrender.com` |
| Live audio default | `false` |

## Notes

- The APK is a local staging build artifact and is not committed to Git.
- Canary install is blocked until the explicit approval phrase `APPROVE CANARY INSTALL`.
- Staging cloud execution is blocked until the explicit approval phrase `APPROVE STAGING EXECUTION`.
