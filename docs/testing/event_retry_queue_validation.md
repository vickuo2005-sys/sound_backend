# Event Retry Queue Validation

## Automated Coverage

Flutter unit test coverage:

- Pending event is persisted.
- Metadata uploaded state is persisted.
- Failure records retry state and attempts.
- Completed upload removes the queue item.

Artifact:

- `artifacts/test_results/flutter_test.txt`

## Implementation Notes

- Queue storage: SharedPreferences.
- Queue payload: event metadata snapshot.
- Retry scope: metadata upload, primary audio upload, TDOA clip upload, final metadata refresh.
- Worker guard: prevents concurrent queue processing.
- Missing WAV file: marked permanent failure.
- Non-target events intentionally ignored by Detection Mode are not enqueued.

## Limits

- Current queue does not store MP3/WAV bytes.
- Current queue does not store a separate cryptographic checksum for local audio files.
- Local file paths must remain valid until retry completes.
- Corrupted SharedPreferences JSON recovery is best-effort and returns an empty queue.

Staging status: `ACCEPTABLE WITH LIMITS`

Production recommendation: add file size/hash validation before external production deployment if unattended long-running nodes will depend on retry for many hours.

