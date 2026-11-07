from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PERCENTILES = ("p50_ms", "p95_ms", "p99_ms", "max_ms")


def compare_reports(
    shadow_off: dict[str, Any],
    shadow_on: dict[str, Any],
    *,
    minimum_samples: int = 50,
    p95_absolute_guard_ms: float = 25.0,
    p95_relative_guard_percent: float = 10.0,
) -> dict[str, Any]:
    if shadow_off.get("nodes") != shadow_on.get("nodes"):
        raise ValueError("Shadow OFF and ON reports must use the same node count")
    nodes = int(shadow_off.get("nodes") or 0)
    if nodes not in (1, 2, 4):
        raise ValueError("nodes must be 1, 2, or 4")

    warnings: list[str] = []
    for mode, report in (("off", shadow_off), ("on", shadow_on)):
        joined = int((report.get("counts") or {}).get("joined") or 0)
        if joined < minimum_samples:
            warnings.append(f"shadow_{mode} joined sample count below {minimum_samples}")

    stage_names = sorted(
        set((shadow_off.get("stages") or {})) | set((shadow_on.get("stages") or {}))
    )
    deltas: dict[str, dict[str, Any]] = {}
    regressions: list[str] = []
    for stage_name in stage_names:
        off_stage = (shadow_off.get("stages") or {}).get(stage_name) or {}
        on_stage = (shadow_on.get("stages") or {}).get(stage_name) or {}
        stage_delta: dict[str, Any] = {}
        for percentile in PERCENTILES:
            off_value = _number(off_stage.get(percentile))
            on_value = _number(on_stage.get(percentile))
            stage_delta[percentile] = (
                round(on_value - off_value, 3)
                if off_value is not None and on_value is not None
                else None
            )
        off_p95 = _number(off_stage.get("p95_ms"))
        on_p95 = _number(on_stage.get("p95_ms"))
        p95_relative = (
            (on_p95 - off_p95) * 100.0 / off_p95
            if off_p95 and on_p95 is not None
            else None
        )
        stage_delta["p95_relative_percent"] = (
            round(p95_relative, 3) if p95_relative is not None else None
        )
        stage_regression = bool(
            off_p95 is not None
            and on_p95 is not None
            and on_p95 - off_p95 > p95_absolute_guard_ms
            and p95_relative is not None
            and p95_relative > p95_relative_guard_percent
        )
        stage_delta["guard_exceeded"] = stage_regression
        if stage_regression:
            regressions.append(stage_name)
        deltas[stage_name] = stage_delta

    evidence_complete = not warnings
    return {
        "nodes": nodes,
        "evidence_complete": evidence_complete,
        "minimum_samples": minimum_samples,
        "shadow_off_joined": int(
            (shadow_off.get("counts") or {}).get("joined") or 0
        ),
        "shadow_on_joined": int((shadow_on.get("counts") or {}).get("joined") or 0),
        "on_minus_off": deltas,
        "guard": {
            "p95_absolute_ms": p95_absolute_guard_ms,
            "p95_relative_percent": p95_relative_guard_percent,
        },
        "regression_detected": bool(regressions) if evidence_complete else None,
        "regression_stages": regressions,
        "warnings": warnings,
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare real staging Alert latency with Observation Shadow OFF/ON."
    )
    parser.add_argument("--off-report", type=Path, required=True)
    parser.add_argument("--on-report", type=Path, required=True)
    parser.add_argument("--minimum-samples", type=int, default=50)
    args = parser.parse_args()
    off_report = json.loads(args.off_report.read_text(encoding="utf-8"))
    on_report = json.loads(args.on_report.read_text(encoding="utf-8"))
    print(
        json.dumps(
            compare_reports(
                off_report,
                on_report,
                minimum_samples=max(1, args.minimum_samples),
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
