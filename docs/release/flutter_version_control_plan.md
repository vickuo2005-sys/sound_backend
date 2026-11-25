# Flutter Version Control Plan

The Flutter project at `C:\Users\vicku\sound_detector_clean` is not currently a Git repository.

## Recommendation

1. Review `.gitignore.release-proposal`.
2. Create a clean repository only after verifying no secrets are present.
3. Initial commit should include source, `pubspec.yaml`, `pubspec.lock`, Android source, assets, tests, and tools.
4. Do not commit:
   - `build/`
   - `.dart_tool/`
   - `.idea/`
   - `android/local.properties`
   - `key.properties`
   - keystores
   - APK files
   - local audio recordings
   - pending upload queue files
5. Branch strategy:
   - `main`: stable production candidates
   - `staging`: staging validation
   - `feature/*`: isolated work
6. Suggested first commit message:
   - `Add Flutter Android sound detector node app`

Release APKs should be attached to a Release, not committed as source.

