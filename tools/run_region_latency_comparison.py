"""Summarize redacted Tokyo/Singapore staging probe JSON files.

The inputs are local JSON artifacts produced by the staging-only probe. This
tool performs no network access and never accepts or prints a DSN/token.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


METRICS = {
    "tcp_connect_ms": ("network", "tcp_connect_ms"),
    "warm_select_1_ms": ("same_connection_select_1_ms",),
    "transaction_select_ms": ("transaction_select_1_ms",),
    "commit_ms": ("transaction_commit_ms",),
    "physical_connect_ms": ("physical_connect_ms",),
}


def _series(payload: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    value: Any = payload
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value if isinstance(value, dict) else {"count": 0}


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"probe JSON must be an object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokyo", type=Path, required=True)
    parser.add_argument("--singapore", type=Path, required=True)
    args = parser.parse_args()
    tokyo = _read(args.tokyo)
    singapore = _read(args.singapore)
    rows: list[dict[str, Any]] = []
    for name, paths in METRICS.items():
        tokyo_value = _series(tokyo, paths)
        singapore_value = _series(singapore, paths)
        row: dict[str, Any] = {"metric": name}
        for label, value in (("tokyo", tokyo_value), ("singapore", singapore_value)):
            for percentile in ("p50_ms", "p95_ms", "p99_ms", "count"):
                row[f"{label}_{percentile}"] = value.get(percentile)
        if isinstance(tokyo_value.get("p50_ms"), (int, float)) and isinstance(singapore_value.get("p50_ms"), (int, float)):
            row["p50_change_ms"] = round(float(singapore_value["p50_ms"]) - float(tokyo_value["p50_ms"]), 3)
            row["p50_change_percent"] = round((float(singapore_value["p50_ms"]) / float(tokyo_value["p50_ms"]) - 1) * 100, 2) if tokyo_value["p50_ms"] else None
        else:
            row["p50_change_ms"] = None
            row["p50_change_percent"] = None
        rows.append(row)
    print(json.dumps({"metrics": rows, "network_lower_bound_only": True, "secrets_emitted": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
