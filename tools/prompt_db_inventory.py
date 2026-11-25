"""Prompt for two staging DSNs without echoing or persisting them.

The values are held only in this Python process and passed to the existing
read-only verifier. The JSON output contains aggregates and metadata only.
"""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

from verify_db_migration import inspect


def main() -> int:
    print("Enter staging DSNs locally. Input is hidden and never written to disk.")
    tokyo = getpass.getpass("Tokyo staging DSN: ")
    singapore = getpass.getpass("Singapore staging DSN: ")
    os.environ["_TOKYO_STAGING_DSN_PROMPT"] = tokyo
    os.environ["_SINGAPORE_STAGING_DSN_PROMPT"] = singapore
    try:
        source = inspect("_TOKYO_STAGING_DSN_PROMPT")
        target = inspect("_SINGAPORE_STAGING_DSN_PROMPT")
        source_tables = set(source["tables"])
        target_tables = set(target["tables"])
        result = {
            "source": source,
            "target": target,
            "schema": {
                "missing_on_target": sorted(source_tables - target_tables),
                "extra_on_target": sorted(target_tables - source_tables),
                "row_count_differences": {
                    table: {
                        "source": source["table_summary"][table]["row_count"],
                        "target": target["table_summary"].get(table, {}).get("row_count"),
                    }
                    for table in sorted(source_tables & target_tables)
                    if source["table_summary"][table]["row_count"]
                    != target["table_summary"].get(table, {}).get("row_count")
                },
                "orphan_fk_count": {
                    "source": sum(item["orphan_count"] for item in source["orphan_foreign_keys"]),
                    "target": sum(item["orphan_count"] for item in target["orphan_foreign_keys"]),
                },
            },
            "secrets_emitted": False,
        }
        output = Path("outputs/staging_db_migration_verification.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"Wrote aggregate verification to {output}")
        return 0
    finally:
        os.environ.pop("_TOKYO_STAGING_DSN_PROMPT", None)
        os.environ.pop("_SINGAPORE_STAGING_DSN_PROMPT", None)


if __name__ == "__main__":
    raise SystemExit(main())
