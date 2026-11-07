from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

APPROVED_STAGING_HOST = "sound-backend-staging.onrender.com"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "backend_intelligence" / "validation" / "bi2"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
FORBIDDEN_METADATA_KEYS = {
    "authorization",
    "database_url",
    "device_token",
    "google_application_credentials_json",
    "service_account",
    "signed_url",
    "upload_token",
}
CSV_FIELDS = (
    "run_id",
    "track_id",
    "point_id",
    "event_time",
    "event_time_ms",
    "measured_lat",
    "measured_lng",
    "filtered_lat",
    "filtered_lng",
    "predicted_lat",
    "predicted_lng",
    "localization_method",
    "uncertainty_radius_m",
    "confidence",
    "group_id",
    "source_node_count",
    "velocity_east_mps",
    "velocity_north_mps",
    "vx_mps",
    "vy_mps",
    "speed_mps",
    "heading_deg",
    "innovation_m",
    "rejected_as_outlier",
    "sequence",
    "created_at",
    "arrival_order",
    "event_time_order",
    "arrival_out_of_order",
    "diagnostics_json",
)


def parse_time_ms(value: str) -> float:
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp() * 1000.0


def time_iso(event_time_ms: float) -> str:
    return datetime.fromtimestamp(event_time_ms / 1000.0, tz=timezone.utc).isoformat()


def validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    if parsed.scheme != "https" or parsed.hostname != APPROVED_STAGING_HOST:
        raise ValueError(
            "motion field capture is fail-closed to the isolated staging hostname"
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base URL must not contain credentials, query, or fragment")
    return f"https://{APPROVED_STAGING_HOST}"


def validate_safe_identifier(value: str, field: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise ValueError(f"{field} must match {SAFE_ID.pattern}")
    return value


def load_metadata(path: Optional[Path]) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"metadata file must contain an object: {path}")
    reject_secret_keys(payload)
    return payload


def reject_secret_keys(value: Any, path: str = "metadata") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_METADATA_KEYS:
                raise ValueError(f"secret-like key is forbidden in capture output: {path}.{key}")
            reject_secret_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_secret_keys(item, f"{path}[{index}]")


def fetch_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is allowlisted
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected response shape from {url}")
    return payload


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(decoded) if isinstance(decoded, dict) else {}
    return {}


def select_track(
    base_url: str,
    *,
    track_id: Optional[str],
    start_time_ms: float,
    end_time_ms: float,
    timeout: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if track_id:
        validate_safe_identifier(track_id, "track-id")
        payload = fetch_json(f"{base_url}/tracks/{track_id}", timeout)
        points_payload = fetch_json(
            f"{base_url}/tracks/{track_id}/points?limit=500",
            timeout,
        )
        return dict(payload.get("track") or {}), list(points_payload.get("points") or [])

    query = urlencode({"limit": 100, "points_limit": 0})
    payload = fetch_json(f"{base_url}/tracks?{query}", timeout)
    candidates = []
    for track in payload.get("tracks") or []:
        first = track.get("first_event_time_ms")
        last = track.get("last_event_time_ms")
        if not isinstance(first, (int, float)) or not isinstance(last, (int, float)):
            continue
        if float(last) >= start_time_ms and float(first) <= end_time_ms:
            candidates.append(dict(track))
    if len(candidates) != 1:
        candidate_ids = [str(item.get("id")) for item in candidates]
        raise ValueError(
            "track-id is required unless exactly one track overlaps the run; "
            f"overlapping candidates={candidate_ids}"
        )
    selected = candidates[0]
    points_payload = fetch_json(
        f"{base_url}/tracks/{selected['id']}/points?limit=500",
        timeout,
    )
    return selected, list(points_payload.get("points") or [])


def normalized_points(
    points: list[dict[str, Any]],
    *,
    run_id: str,
    track_id: str,
    start_time_ms: float,
    end_time_ms: float,
) -> list[dict[str, Any]]:
    selected = [
        dict(point)
        for point in points
        if isinstance(point.get("measurement_time_ms"), (int, float))
        and start_time_ms <= float(point["measurement_time_ms"]) <= end_time_ms
    ]
    arrival_order = {
        str(point.get("id")): index
        for index, point in enumerate(
            sorted(
                selected,
                key=lambda point: (
                    str(point.get("created_at") or ""),
                    str(point.get("id") or ""),
                ),
            ),
            start=1,
        )
    }
    ordered = sorted(
        selected,
        key=lambda point: (
            float(point["measurement_time_ms"]),
            str(point.get("id") or ""),
        ),
    )
    result = []
    for event_index, point in enumerate(ordered, start=1):
        diagnostics = parse_json_object(point.get("diagnostics_json"))
        point_id = str(point.get("id") or f"missing-{event_index}")
        arrival_index = arrival_order.get(point_id)
        event_time_ms = float(point["measurement_time_ms"])
        result.append(
            {
                "run_id": run_id,
                "track_id": track_id,
                "point_id": point_id,
                "event_time": time_iso(event_time_ms),
                "event_time_ms": event_time_ms,
                "measured_lat": point.get("measured_lat"),
                "measured_lng": point.get("measured_lng"),
                "filtered_lat": point.get("filtered_lat"),
                "filtered_lng": point.get("filtered_lng"),
                "predicted_lat": point.get("predicted_lat"),
                "predicted_lng": point.get("predicted_lng"),
                "localization_method": diagnostics.get("localization_method")
                or diagnostics.get("source"),
                "uncertainty_radius_m": point.get("uncertainty_radius_m"),
                "confidence": point.get("confidence"),
                "group_id": point.get("group_id"),
                "source_node_count": diagnostics.get("reporting_node_count"),
                "source_node_ids": diagnostics.get("reporting_device_ids"),
                "velocity_east_mps": point.get("velocity_east_mps"),
                "velocity_north_mps": point.get("velocity_north_mps"),
                "vx_mps": point.get("velocity_east_mps"),
                "vy_mps": point.get("velocity_north_mps"),
                "speed_mps": point.get("speed_mps"),
                "heading_deg": point.get("heading_deg"),
                "innovation_m": point.get("innovation_m"),
                "rejected_as_outlier": bool(point.get("rejected_as_outlier")),
                "sequence": diagnostics.get("sequence"),
                "observation_id": diagnostics.get("observation_id"),
                "tracking_discard_reason": diagnostics.get("tracking_discard_reason"),
                "created_at": point.get("created_at"),
                "arrival_order": arrival_index,
                "event_time_order": event_index,
                "arrival_out_of_order": (
                    arrival_index is not None and arrival_index != event_index
                ),
                "state_json": parse_json_object(point.get("state_json")),
                "covariance_json": parse_json_object(point.get("covariance_json")),
                "diagnostics_json": diagnostics,
            }
        )
    return result


def write_capture(
    output_dir: Path,
    *,
    scenario: str,
    run_id: str,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"run_{scenario}_{run_id}_raw"
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for point in payload["track_raw_data"]:
            row = dict(point)
            row["diagnostics_json"] = json.dumps(
                point.get("diagnostics_json") or {},
                separators=(",", ":"),
                sort_keys=True,
            )
            writer.writerow(row)
    return json_path, csv_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one isolated-staging BI-2 motion field run"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--scenario",
        required=True,
        choices=("S0_static", "S1_east_west", "S2_north_south", "S3_diagonal", "S4_stop_move_stop", "S5_turn_90"),
    )
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--end-time", required=True)
    parser.add_argument("--track-id")
    parser.add_argument("--node-id", action="append", default=[])
    parser.add_argument("--audio-asset", required=True)
    parser.add_argument("--ground-truth-file", type=Path, required=True)
    parser.add_argument("--node-layout-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    base_url = validate_base_url(args.base_url)
    run_id = validate_safe_identifier(args.run_id, "run-id")
    scenario = validate_safe_identifier(args.scenario, "scenario")
    start_time_ms = parse_time_ms(args.start_time)
    end_time_ms = parse_time_ms(args.end_time)
    if end_time_ms <= start_time_ms:
        raise SystemExit("end-time must be later than start-time")
    ground_truth = load_metadata(args.ground_truth_file)
    node_layout = load_metadata(args.node_layout_file)
    node_ids = sorted({validate_safe_identifier(item, "node-id") for item in args.node_id})
    if not node_ids:
        raise SystemExit("at least one --node-id is required")
    track, points = select_track(
        base_url,
        track_id=args.track_id,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
        timeout=max(1.0, args.timeout),
    )
    track_id = str(track.get("id") or args.track_id or "")
    if not track_id:
        raise SystemExit("selected track has no id")
    raw_points = normalized_points(
        points,
        run_id=run_id,
        track_id=track_id,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
    )
    payload = {
        "schema_version": "bi2.motion_field_run.v1",
        "run_id": run_id,
        "scenario": scenario,
        "start_time": time_iso(start_time_ms),
        "end_time": time_iso(end_time_ms),
        "node_ids": node_ids,
        "node_layout": node_layout,
        "audio_asset": args.audio_asset,
        "ground_truth": ground_truth,
        "source": {
            "backend_host": APPROVED_STAGING_HOST,
            "track_id": track_id,
        },
        "track": track,
        "track_raw_data": raw_points,
        "capture_diagnostics": {
            "point_count": len(raw_points),
            "rejected_point_count": sum(
                bool(point.get("rejected_as_outlier")) for point in raw_points
            ),
            "arrival_out_of_order_count": sum(
                bool(point.get("arrival_out_of_order")) for point in raw_points
            ),
        },
    }
    reject_secret_keys(payload)
    json_path, csv_path = write_capture(
        args.output_dir.resolve(),
        scenario=scenario,
        run_id=run_id,
        payload=payload,
    )
    print(
        json.dumps(
            {
                "status": "captured",
                "run_id": run_id,
                "point_count": len(raw_points),
                "json": str(json_path),
                "csv": str(csv_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
