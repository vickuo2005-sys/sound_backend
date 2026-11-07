"""Validate pasted CSV/JSON/text output from migration postcheck.

This tool is intentionally conservative: it never connects to Supabase and never
executes SQL. Save Supabase SQL Editor output to a local file, then run:

    python tools/validate_migration_output.py path/to/postcheck-output.txt
"""

from __future__ import annotations

import sys
from pathlib import Path


REQUIRED_MARKERS = [
    "events",
    "device_status",
    "device_commands",
    "event_groups",
    "event_group_observations",
    "time_sync_offset_ms",
    "time_sync_rtt_ms",
    "time_sync_quality",
    "time_sync_at",
    "corrected_arrival_time_ms",
    "tdoa_clip_path",
    "tdoa_clip_start_sample",
]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/validate_migration_output.py <output-file>")
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"not_ready: file not found: {path}")
        return 2

    text = path.read_text(encoding="utf-8", errors="replace")
    lowered = text.lower()
    missing = [marker for marker in REQUIRED_MARKERS if marker.lower() not in lowered]
    unexpected = [
        phrase
        for phrase in (" missing", ",missing", "\tmissing", "| missing")
        if phrase in lowered
    ]

    if missing:
        print("not_ready: missing expected markers")
        for marker in missing:
            print(f"- {marker}")
        return 1

    if unexpected:
        print("not_ready: postcheck output appears to contain missing columns")
        return 1

    print("ready: migration output contains expected schema markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
