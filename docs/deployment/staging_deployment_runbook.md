# Staging Deployment Runbook

1. Freeze source and record `git status`.
2. Generate backend release manifest.
3. Generate Flutter release snapshot.
4. Back up staging database.
5. Apply staging migrations.
6. Configure staging environment variables.
7. Deploy staging Render service with one worker.
8. Run post-deploy smoke tool.
9. Install Release APK on one test node.
10. Confirm node WebSocket hello, heartbeat, command ACK, and command result.
11. Confirm REST fallback polling still works by disabling WebSocket temporarily.
12. Trigger one event and verify retry queue does not duplicate.
13. Enable `LIVE_AUDIO_ENABLED=true` for one-node live audio canary.
14. Confirm dashboard subscriber receives frames.
15. Observe logs and memory for at least 30 minutes.
16. Record evidence in `artifacts/test_results`.

