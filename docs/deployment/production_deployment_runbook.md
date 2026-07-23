# Production Deployment Runbook

Production deployment was not performed during this freeze pass.

## Approval Gates

- Staging migrations passed.
- Staging smoke passed.
- One-node staging live audio canary passed.
- APK installation test passed.
- Secret review passed.
- Rollback plan reviewed.

## Deployment Order

1. Confirm maintenance window.
2. Back up production Supabase.
3. Confirm Render env vars and feature flags.
4. Apply approved production migrations.
5. Deploy backend.
6. Run `tools/post_deploy_smoke.py --base-url https://sound-backend.onrender.com --allow-websocket`.
7. Canary one physical node.
8. Monitor logs.
9. Enable remaining nodes.
10. Enable live audio only after command and event flow are stable.

