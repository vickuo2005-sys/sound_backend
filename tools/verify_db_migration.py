"""Read-only source/target PostgreSQL migration verification.

DSNs are read from environment variables named by the CLI. Values and row
contents are never printed. The tool is intentionally limited to metadata,
aggregates, and orphan counts so it can be used during a staging cutover.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import psycopg2


def _connect(env_name: str):
    dsn = os.environ.get(env_name)
    if not dsn:
        raise SystemExit(f"missing DSN environment variable: {env_name}")
    return psycopg2.connect(dsn)


def _fetchall(connection: Any, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return list(cursor.fetchall())


def _tables(connection: Any) -> list[str]:
    rows = _fetchall(
        connection,
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
    )
    return [str(row[0]) for row in rows]


def _table_summary(connection: Any, table: str) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM public."' + table.replace('"', '""') + '"')
        count = int(cursor.fetchone()[0])
        cursor.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
              AND (column_name ILIKE '%time%' OR column_name IN ('created_at','updated_at','last_seen'))
            ORDER BY ordinal_position LIMIT 1
            """,
            (table,),
        )
        timestamp_column = cursor.fetchone()
        timestamp_summary: dict[str, Any] | None = None
        if timestamp_column:
            column = str(timestamp_column[0]).replace('"', '""')
            cursor.execute(
                f'SELECT MIN("{column}"), MAX("{column}") FROM public."{table.replace(chr(34), chr(34) * 2)}"'
            )
            min_value, max_value = cursor.fetchone()
            timestamp_summary = {"column": column, "min": str(min_value) if min_value is not None else None, "max": str(max_value) if max_value is not None else None}
        cursor.execute(
            """
            SELECT ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.table_schema='public' AND tc.table_name=%s
              AND tc.constraint_type='PRIMARY KEY'
            ORDER BY ccu.ordinal_position
            """,
            (table,),
        )
        primary_key = [str(row[0]) for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT column_name, data_type, udt_name, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        columns = [
            {
                "name": row[0],
                "data_type": row[1],
                "udt_name": row[2],
                "nullable": row[3],
                "default": row[4],
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname='public' AND tablename=%s ORDER BY indexname
            """,
            (table,),
        )
        indexes = [{"name": row[0], "definition": row[1]} for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_schema='public' AND table_name=%s
            ORDER BY constraint_name
            """,
            (table,),
        )
        constraints = [{"name": row[0], "type": row[1]} for row in cursor.fetchall()]
    result: dict[str, Any] = {
        "row_count": count,
        "primary_key": primary_key,
        "columns": columns,
        "indexes": indexes,
        "constraints": constraints,
    }
    if timestamp_summary is not None:
        result["timestamp"] = timestamp_summary
    return result


def _sequences(connection: Any) -> dict[str, Any]:
    rows = _fetchall(
        connection,
        """
        SELECT schemaname, sequencename, last_value, start_value, increment_by
        FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename
        """,
    )
    return {str(row[1]): {"last_value": row[2], "start_value": row[3], "increment_by": row[4]} for row in rows}


def _foreign_keys(connection: Any) -> list[dict[str, Any]]:
    rows = _fetchall(
        connection,
        """
        SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu USING (constraint_name, table_schema)
        JOIN information_schema.constraint_column_usage ccu USING (constraint_name, table_schema)
        WHERE tc.table_schema='public' AND tc.constraint_type='FOREIGN KEY'
        ORDER BY 1,2,3,4
        """,
    )
    return [{"table": r[0], "column": r[1], "ref_table": r[2], "ref_column": r[3]} for r in rows]


def _orphan_count(connection: Any, foreign_key: dict[str, Any]) -> int:
    table = str(foreign_key["table"]).replace('"', '""')
    column = str(foreign_key["column"]).replace('"', '""')
    ref_table = str(foreign_key["ref_table"]).replace('"', '""')
    ref_column = str(foreign_key["ref_column"]).replace('"', '""')
    query = f'''SELECT COUNT(*) FROM public."{table}" child
                LEFT JOIN public."{ref_table}" parent ON child."{column}" = parent."{ref_column}"
                WHERE child."{column}" IS NOT NULL AND parent."{ref_column}" IS NULL'''
    return int(_fetchall(connection, query)[0][0])


def inspect(env_name: str) -> dict[str, Any]:
    connection = _connect(env_name)
    try:
        tables = _tables(connection)
        foreign_keys = _foreign_keys(connection)
        return {
            "tables": tables,
            "table_summary": {table: _table_summary(connection, table) for table in tables},
            "sequences": _sequences(connection),
            "foreign_keys": foreign_keys,
            "orphan_foreign_keys": [
                {**fk, "orphan_count": _orphan_count(connection, fk)} for fk in foreign_keys
            ],
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dsn-env", required=True)
    parser.add_argument("--target-dsn-env", required=True)
    args = parser.parse_args()
    source = inspect(args.source_dsn_env)
    target = inspect(args.target_dsn_env)
    source_tables = set(source["tables"])
    target_tables = set(target["tables"])
    comparison = {
        "source": source,
        "target": target,
        "schema": {
            "missing_on_target": sorted(source_tables - target_tables),
            "extra_on_target": sorted(target_tables - source_tables),
            "row_count_differences": {
                table: {"source": source["table_summary"][table]["row_count"], "target": target["table_summary"].get(table, {}).get("row_count")}
                for table in sorted(source_tables & target_tables)
                if source["table_summary"][table]["row_count"] != target["table_summary"].get(table, {}).get("row_count")
            },
            "orphan_fk_count": {
                side: sum(item["orphan_count"] for item in payload["orphan_foreign_keys"])
                for side, payload in (("source", source), ("target", target))
            },
        },
        "secrets_emitted": False,
    }
    json.dump(comparison, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
