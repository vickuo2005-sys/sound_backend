# Pre-Staging Git Classification

Generated on 2026-07-24 during Production Blocker Remediation. No files were
staged, committed, pushed, tagged, deployed, or migrated.

## Summary

| Category | Include in future commit? | Notes |
| --- | --- | --- |
| Runtime required | Yes, explicit review | `main.py`, `app/`, `services/` runtime additions |
| Tests required | Yes | `tests/`, `tools/test_*.py`, `pytest.ini`, `requirements-dev.txt` |
| Migrations required | Yes, after Supabase review | `migrations/v3_*.sql`, `migrations/v4_*.sql` |
| Documentation | Yes | `docs/architecture`, `docs/database`, `docs/deployment`, `docs/testing`, release notes |
| Release / staging tools | Yes | `tools/post_deploy_smoke.py`, staging scripts, manifest tools |
| Generated artifacts | Usually no | `artifacts/` should be reviewed before committing |
| Existing README dirty change | Manual review | Pre-existing dirty change; do not stage automatically |
| Potential secret | No | `.env*`, `.secrets/`, local config, signing files |
| Temporary / should ignore | No | venvs, caches, APKs, local DBs |
| Unknown / manual review | Manual | Anything outside listed release scope |

## Current Known Dirty Tracked Files

| Path | Category | Include? | Risk |
| --- | --- | --- | --- |
| `README.md` | Existing README dirty change | Manual review | Pre-existing wording change and demo token examples |
| `main.py` | Runtime required | Yes, explicit commit group | Large runtime surface |
| `requirements.txt` | Runtime required | Yes | Dependency drift |
| `services/event_fusion.py` | Runtime required | Yes | Event grouping behavior |
| `tools/test_event_fusion.py` | Tests required | Yes | Fixture updates |
| `tools/test_time_sync.py` | Tests required | Yes | Fixture updates |
| `docs/architecture/time-sync.md` | Documentation | Yes | Existing V3.2 docs |
| `docs/database/time-sync-schema.md` | Documentation | Yes | Existing V3.2 docs |
| `docs/release_notes/v3.2-time-sync.md` | Documentation | Yes | Existing V3.2 docs |
| `docs/testing/time-sync-testing.md` | Documentation | Yes | Existing V3.2 docs |
| `migrations/v3_2_time_sync.sql` | Migrations required | Yes after review | Requires staging migration first |

## New Remediation Files

| Path | Category | Include? | Risk |
| --- | --- | --- | --- |
| `tools/migration_precheck.sql` | Release / staging tools | Yes | Read-only SQL |
| `tools/migration_postcheck.sql` | Release / staging tools | Yes | Read-only SQL |
| `tools/validate_migration_output.py` | Release / staging tools | Yes | Offline parser only |
| `tools/generate_staging_secrets.ps1` | Release / staging tools | Yes | Does not print secrets, output ignored |
| `tools/staging/*.ps1` | Release / staging tools | Yes | Local wrappers |
| `docs/deployment/staging_resource_creation_checklist.md` | Documentation | Yes | No secrets |
| `docs/release/android_release_signing_guide.md` | Documentation | Yes | No secrets |
| `docs/release/flutter_git_initialization_runbook.md` | Documentation | Yes | No Git action performed |
| `docs/release/pre_staging_git_classification.md` | Documentation | Yes | This classification |

## Suggested Future Commit Groups

1. Realtime/runtime backend.
2. Localization/tracking backend.
3. Migrations.
4. Tests and validation tools.
5. Staging/release tooling.
6. Documentation.
7. Flutter project in its own repository, if initialized manually later.

README.md should remain outside automated staging until manually approved.
