"""Read-only PostgreSQL index/query audit for the hot realtime tables.

Usage:
    DATABASE_URL=... python tools/audit_realtime_postgres.py

The script never creates or alters schema. Run it against staging first.
"""

from __future__ import annotations

import json
import os
import sys

import psycopg2
import psycopg2.extras


EXPECTED_INDEX_PREFIXES = {
    "events": {"events_event_id_key"},
    "event_groups": {
        "event_groups_label_status_last_time_idx",
        "event_groups_updated_at_idx",
    },
    "event_group_observations": {
        "event_group_observations_group_idx",
        "event_group_observations_event_id_idx",
        "event_group_observations_device_idx",
        "event_group_observations_timestamp_idx",
    },
    "target_tracks": {"target_tracks_status_label_idx"},
    "target_track_points": {
        "target_track_points_track_idx",
        "target_track_points_group_idx",
    },
}


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    connection = psycopg2.connect(database_url, connect_timeout=10)
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT tablename, indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = ANY(%s)
                ORDER BY tablename, indexname
                """,
                (list(EXPECTED_INDEX_PREFIXES),),
            )
            rows = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT relname AS table_name,
                       seq_scan,
                       idx_scan,
                       n_live_tup,
                       n_dead_tup
                FROM pg_stat_user_tables
                WHERE relname = ANY(%s)
                ORDER BY relname
                """,
                (list(EXPECTED_INDEX_PREFIXES),),
            )
            stats = [dict(row) for row in cursor.fetchall()]

        observed = {}
        for row in rows:
            observed.setdefault(row["tablename"], set()).add(row["indexname"])

        missing = {
            table: sorted(expected - observed.get(table, set()))
            for table, expected in EXPECTED_INDEX_PREFIXES.items()
            if expected - observed.get(table, set())
        }

        output = {
            "status": "pass" if not missing else "review",
            "missing_expected_indexes": missing,
            "indexes": rows,
            "table_stats": stats,
            "notes": [
                "This is a read-only audit; no index is created automatically.",
                "A high seq_scan count is not itself proof of a bad plan.",
                "Use EXPLAIN (ANALYZE, BUFFERS) on staging for confirmed hot queries before changing schema.",
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        return 0 if not missing else 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
