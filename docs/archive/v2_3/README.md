# Sound Detector V2.3 archive

This directory is the canonical archive record for the product release named
**V2.3**.

## Version identity

The product release name is V2.3. Some source branches and implementation
documents retain internal phase labels such as V2.4, V2.4.1, and V2.4.2. Those
labels describe development workstreams; they do not change the archived
product release name.

| Identity | Value |
| --- | --- |
| Product release | V2.3 |
| Backend functional baseline | `256f44548c8375c544d3d6bc972e126041746232` |
| Flutter baseline | `e593007cfd9df9c969ff6cfdd89ff8c9c9288121` |
| Production runtime baseline | `5babe2bafaffbb77b48d16a5e1675f202ae7286b` |
| Archive date | 2026-09-04 (Asia/Taipei) |

## Archive contents

- [ARCHIVE_REPORT.md](ARCHIVE_REPORT.md): scope, evidence, verdict, source
  identity, restore points, and archive rules.
- [KNOWN_RUNTIME_ISSUES.md](KNOWN_RUNTIME_ISSUES.md): observed limitations,
  field-validation gaps, and their operational impact.
- [runtime_snapshot.json](runtime_snapshot.json): sanitized machine-readable
  snapshot of staging and production runtime state.

## Interpretation rule

This archive preserves a development/demo baseline. It is not evidence that
fixed-site arrival prediction, multi-node motion estimation, or five-class
field accuracy is approved for operational safety decisions. Speaker playback
is end-to-end smoke evidence only and is not physical-drone field evidence.

The external release bundle is generated from exact Git commits. It excludes
working-tree-only changes, ignored local configuration, credentials, build
outputs, APKs, signing material, audio, and precise device coordinates. Its
SHA-256 manifests are the integrity authority for the copied files.
