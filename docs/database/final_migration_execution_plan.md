# Final Migration Execution Plan

Run migrations in Supabase SQL Editor after backing up the database.

## Order

1. `migrations/v3_3_localization.sql`
2. `migrations/v3_4_hybrid_localization.sql`
3. `migrations/v4_0_tracking.sql`
4. `migrations/v4_final_realtime.sql`
5. `migrations/v4_final_localization.sql`
6. `migrations/v4_final_tracking.sql`

## Repeatability Check

Run each migration once. If Supabase reports success, run the final three migrations a second time to confirm idempotency.

## Post-Migration Smoke Checks

- `GET /health`
- `GET /dashboard`
- `GET /nodes/live`
- `GET /audio-streams`
- `GET /event-groups`
- `GET /localization-results`
- `GET /tracks`

## Failure Handling

These migrations are additive. If a statement fails, stop and inspect the exact table or column named in the error before continuing.

Do not drop existing production tables during this migration.

