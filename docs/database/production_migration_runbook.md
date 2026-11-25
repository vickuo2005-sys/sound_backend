# Production Migration Runbook

Production migration requires human approval.

1. Freeze source and record Git status.
2. Back up Supabase production database.
3. Confirm staging has already passed the same migration sequence.
4. Confirm app feature flags are conservative:
   - `LIVE_AUDIO_ENABLED=false`
   - `COMMAND_REST_FALLBACK_ENABLED=true`
5. Apply migrations during a maintenance window.
6. After each migration, run post-check SQL for expected objects and columns.
7. Deploy backend only after schema checks pass.
8. Run production smoke tests:
   - `/health`
   - `/dashboard`
   - `/nodes/live`
   - `/audio-streams`
   - `/time-sync`
   - `/event-groups`
   - `/localization-results`
   - `/tracks`
9. Canary one node before enabling all nodes.
10. If migration fails, do not run destructive rollback. Prefer forward-fix migration or feature flag disable.

