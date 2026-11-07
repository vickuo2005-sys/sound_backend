from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.localization.geo import haversine_m  # noqa: E402
from services.tracking.motion import (  # noqa: E402
    estimate_constant_velocity,
    latlng_to_local_xy,
)
from services.tracking.motion_validation import (  # noqa: E402
    circular_heading_error_deg,
    classify_site_motion,
    error_summary,
    finite_number,
    numeric_summary,
    uncertainty_coverage,
)
from tools.capture_motion_field_run import parse_time_ms  # noqa: E402


def load_run(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"run file must contain an object: {path}")
    if payload.get("schema_version") != "bi2.motion_field_run.v1":
        raise ValueError(f"unsupported run schema: {path}")
    if not isinstance(payload.get("track_raw_data"), list):
        raise ValueError(f"track_raw_data must be an array: {path}")
    return payload


def heading_between(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
) -> Optional[float]:
    x, y = latlng_to_local_xy(end_lat, end_lng, start_lat, start_lng)
    if math.hypot(x, y) < 1e-9:
        return None
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def ground_truth_waypoints(run: dict[str, Any]) -> list[dict[str, float]]:
    ground_truth = run.get("ground_truth") or {}
    waypoints = ground_truth.get("waypoints")
    if isinstance(waypoints, list) and waypoints:
        parsed = []
        for item in waypoints:
            if not isinstance(item, dict):
                continue
            latitude = finite_number(item.get("lat", item.get("latitude")))
            longitude = finite_number(item.get("lng", item.get("longitude")))
            time_value = item.get("event_time", item.get("time"))
            if latitude is None or longitude is None or time_value is None:
                continue
            parsed.append(
                {
                    "time_ms": parse_time_ms(str(time_value)),
                    "lat": latitude,
                    "lng": longitude,
                }
            )
        return sorted(parsed, key=lambda item: item["time_ms"])

    start = ground_truth.get("route_start") or {}
    end = ground_truth.get("route_end") or start
    start_lat = finite_number(start.get("lat", start.get("latitude")))
    start_lng = finite_number(start.get("lng", start.get("longitude")))
    end_lat = finite_number(end.get("lat", end.get("latitude")))
    end_lng = finite_number(end.get("lng", end.get("longitude")))
    if None in {start_lat, start_lng, end_lat, end_lng}:
        return []
    start_time = ground_truth.get("motion_start_time", ground_truth.get("start_time", run.get("start_time")))
    end_time = ground_truth.get("motion_end_time", ground_truth.get("end_time", run.get("end_time")))
    if start_time is None or end_time is None:
        return []
    return [
        {
            "time_ms": parse_time_ms(str(start_time)),
            "lat": float(start_lat),
            "lng": float(start_lng),
        },
        {
            "time_ms": parse_time_ms(str(end_time)),
            "lat": float(end_lat),
            "lng": float(end_lng),
        },
    ]


def truth_state_at(
    event_time_ms: float, waypoints: list[dict[str, float]]
) -> Optional[dict[str, float | None]]:
    if not waypoints:
        return None
    if len(waypoints) == 1 or event_time_ms < waypoints[0]["time_ms"]:
        return {
            "lat": waypoints[0]["lat"],
            "lng": waypoints[0]["lng"],
            "speed_mps": 0.0,
            "heading_deg": None,
        }
    if event_time_ms > waypoints[-1]["time_ms"]:
        return {
            "lat": waypoints[-1]["lat"],
            "lng": waypoints[-1]["lng"],
            "speed_mps": 0.0,
            "heading_deg": None,
        }
    for first, second in zip(waypoints, waypoints[1:]):
        if first["time_ms"] <= event_time_ms <= second["time_ms"]:
            duration_s = (second["time_ms"] - first["time_ms"]) / 1000.0
            if duration_s <= 0.0:
                return None
            ratio = (event_time_ms - first["time_ms"]) / (
                second["time_ms"] - first["time_ms"]
            )
            distance_m = haversine_m(
                first["lat"], first["lng"], second["lat"], second["lng"]
            )
            return {
                "lat": first["lat"] + (second["lat"] - first["lat"]) * ratio,
                "lng": first["lng"] + (second["lng"] - first["lng"]) * ratio,
                "speed_mps": distance_m / duration_s,
                "heading_deg": heading_between(
                    first["lat"], first["lng"], second["lat"], second["lng"]
                ),
            }
    return None


def position_error_summary(
    points: list[dict[str, Any]],
    truths: list[Optional[dict[str, float | None]]],
    *,
    latitude_key: str,
    longitude_key: str,
    include_rejected: bool,
) -> tuple[dict[str, Any], list[Optional[float]]]:
    errors: list[Optional[float]] = []
    valid_errors = []
    for point, truth in zip(points, truths):
        latitude = finite_number(point.get(latitude_key))
        longitude = finite_number(point.get(longitude_key))
        if (
            truth is None
            or latitude is None
            or longitude is None
            or (not include_rejected and point.get("rejected_as_outlier"))
        ):
            errors.append(None)
            continue
        error = haversine_m(
            latitude,
            longitude,
            float(truth["lat"]),
            float(truth["lng"]),
        )
        errors.append(error)
        valid_errors.append(error)
    summary = numeric_summary(valid_errors)
    summary["rmse"] = (
        math.sqrt(sum(value * value for value in valid_errors) / len(valid_errors))
        if valid_errors
        else None
    )
    return summary, errors


def position_jitter_rms(
    points: list[dict[str, Any]], latitude_key: str, longitude_key: str
) -> Optional[float]:
    coordinates = [
        (finite_number(point.get(latitude_key)), finite_number(point.get(longitude_key)))
        for point in points
        if not point.get("rejected_as_outlier")
    ]
    coordinates = [
        (float(latitude), float(longitude))
        for latitude, longitude in coordinates
        if latitude is not None and longitude is not None
    ]
    if not coordinates:
        return None
    reference_lat, reference_lng = coordinates[0]
    xy = [
        latlng_to_local_xy(lat, lng, reference_lat, reference_lng)
        for lat, lng in coordinates
    ]
    mean_x = sum(point[0] for point in xy) / len(xy)
    mean_y = sum(point[1] for point in xy) / len(xy)
    return math.sqrt(
        sum((x - mean_x) ** 2 + (y - mean_y) ** 2 for x, y in xy) / len(xy)
    )


def raw_motion_series(
    points: list[dict[str, Any]], *, window_size: int = 5
) -> list[dict[str, Any]]:
    accepted = [
        point
        for point in points
        if finite_number(point.get("measured_lat")) is not None
        and finite_number(point.get("measured_lng")) is not None
    ]
    result = []
    for index in range(1, len(accepted)):
        window = accepted[max(0, index + 1 - max(2, window_size)) : index + 1]
        estimate = estimate_constant_velocity(
            [
                {
                    "measurement_time_ms": point["event_time_ms"],
                    "measured_lat": point["measured_lat"],
                    "measured_lng": point["measured_lng"],
                    "uncertainty_radius_m": point.get("uncertainty_radius_m"),
                }
                for point in window
            ]
        )
        result.append(
            {
                "event_time_ms": accepted[index]["event_time_ms"],
                "speed_mps": estimate.speed_mps,
                "heading_deg": estimate.heading_deg,
                "quality": estimate.quality,
                "valid": estimate.valid,
                "residual_rmse_m": estimate.residual_rmse_m,
                "outlier_detected": estimate.outlier_detected,
            }
        )
    return result


def gap_metrics(points: list[dict[str, Any]], expected_interval_s: float) -> dict[str, Any]:
    ordered_times = sorted(
        {
            float(point["event_time_ms"])
            for point in points
            if finite_number(point.get("event_time_ms")) is not None
        }
    )
    gaps = [
        (later - earlier) / 1000.0
        for earlier, later in zip(ordered_times, ordered_times[1:])
        if later > earlier
    ]
    return {
        **numeric_summary(gaps),
        "missing_hop_count": sum(
            gap > max(0.001, expected_interval_s) * 1.5 for gap in gaps
        ),
    }


def analyze_run(run: dict[str, Any]) -> dict[str, Any]:
    points = sorted(
        [dict(point) for point in run.get("track_raw_data") or []],
        key=lambda point: float(point.get("event_time_ms") or 0.0),
    )
    ground_truth = run.get("ground_truth") or {}
    analysis_config = ground_truth.get("analysis") or {}
    expected_interval_s = float(analysis_config.get("expected_interval_s", 1.5))
    waypoints = ground_truth_waypoints(run)
    truths = [truth_state_at(float(point["event_time_ms"]), waypoints) for point in points]
    raw_position, raw_errors = position_error_summary(
        points,
        truths,
        latitude_key="measured_lat",
        longitude_key="measured_lng",
        include_rejected=True,
    )
    filtered_position, _ = position_error_summary(
        points,
        truths,
        latitude_key="filtered_lat",
        longitude_key="filtered_lng",
        include_rejected=False,
    )

    raw_series = raw_motion_series(points)
    truth_by_time = {
        float(point["event_time_ms"]): truth
        for point, truth in zip(points, truths)
        if truth is not None
    }
    raw_speed_estimates = []
    raw_speed_truths = []
    raw_heading_errors = []
    quality_counts = Counter()
    minimum_reliable_speed = finite_number(
        analysis_config.get("minimum_reliable_motion_speed_mps")
    )
    for sample in raw_series:
        quality_counts[str(sample["quality"])] += 1
        truth = truth_by_time.get(float(sample["event_time_ms"]))
        if truth is None:
            continue
        speed = finite_number(sample.get("speed_mps"))
        truth_speed = finite_number(truth.get("speed_mps"))
        if speed is not None and truth_speed is not None:
            raw_speed_estimates.append(speed)
            raw_speed_truths.append(truth_speed)
        heading = finite_number(sample.get("heading_deg"))
        truth_heading = finite_number(truth.get("heading_deg"))
        if (
            heading is not None
            and truth_heading is not None
            and sample.get("quality") in {"medium", "high"}
            and minimum_reliable_speed is not None
            and speed is not None
            and speed >= minimum_reliable_speed
        ):
            raw_heading_errors.append(circular_heading_error_deg(heading, truth_heading))

    tracker_speed_estimates = []
    tracker_speed_truths = []
    tracker_heading_errors = []
    for point, truth in zip(points, truths):
        if truth is None or point.get("rejected_as_outlier"):
            continue
        speed = finite_number(point.get("speed_mps"))
        truth_speed = finite_number(truth.get("speed_mps"))
        if speed is not None and truth_speed is not None:
            tracker_speed_estimates.append(speed)
            tracker_speed_truths.append(truth_speed)
        heading = finite_number(point.get("heading_deg"))
        truth_heading = finite_number(truth.get("heading_deg"))
        if (
            heading is not None
            and truth_heading is not None
            and minimum_reliable_speed is not None
            and speed is not None
            and speed >= minimum_reliable_speed
        ):
            tracker_heading_errors.append(
                circular_heading_error_deg(heading, truth_heading)
            )

    coverage_errors = []
    coverage_radii = []
    for error, point in zip(raw_errors, points):
        radius = finite_number(point.get("uncertainty_radius_m"))
        if error is not None and radius is not None:
            coverage_errors.append(error)
            coverage_radii.append(radius)

    full_raw = estimate_constant_velocity(
        [
            {
                "measurement_time_ms": point.get("event_time_ms"),
                "measured_lat": point.get("measured_lat"),
                "measured_lng": point.get("measured_lng"),
                "uncertainty_radius_m": point.get("uncertainty_radius_m"),
            }
            for point in points
        ]
    ).to_dict()
    excluded_raw = estimate_constant_velocity(
        [
            {
                "measurement_time_ms": point.get("event_time_ms"),
                "measured_lat": point.get("measured_lat"),
                "measured_lng": point.get("measured_lng"),
                "uncertainty_radius_m": point.get("uncertainty_radius_m"),
            }
            for point in points
            if not point.get("rejected_as_outlier")
        ]
    ).to_dict()

    site = ground_truth.get("validation_site") or {}
    site_lat = finite_number(site.get("lat", site.get("latitude")))
    site_lng = finite_number(site.get("lng", site.get("longitude")))
    if site_lat is None or site_lng is None:
        site_motion = {
            "classification": "UNCERTAIN",
            "reason": "validation_site_not_configured",
            "sample_count": 0,
            "closing_speed_mps": None,
        }
    else:
        site_motion = classify_site_motion(
            points,
            site_latitude=site_lat,
            site_longitude=site_lng,
            minimum_reliable_speed_mps=minimum_reliable_speed,
            minimum_closing_speed_mps=finite_number(
                analysis_config.get("minimum_closing_speed_mps")
            ),
        )

    static_metrics = None
    if str(run.get("scenario") or "").startswith("S0_static"):
        static_metrics = {
            "raw_position_jitter_rms_m": position_jitter_rms(
                points, "measured_lat", "measured_lng"
            ),
            "filtered_position_jitter_rms_m": position_jitter_rms(
                points, "filtered_lat", "filtered_lng"
            ),
            "raw_false_speed_mps": numeric_summary(
                [sample["speed_mps"] for sample in raw_series if sample["speed_mps"] is not None]
            ),
            "current_tracker_false_speed_mps": numeric_summary(
                [
                    float(point["speed_mps"])
                    for point in points
                    if finite_number(point.get("speed_mps")) is not None
                    and not point.get("rejected_as_outlier")
                ]
            ),
        }

    return {
        "schema_version": "bi2.motion_field_metrics.v1",
        "run_id": run.get("run_id"),
        "scenario": run.get("scenario"),
        "node_count": len(run.get("node_ids") or []),
        "point_count": len(points),
        "accepted_point_count": sum(not point.get("rejected_as_outlier") for point in points),
        "rejected_point_count": sum(bool(point.get("rejected_as_outlier")) for point in points),
        "ground_truth_waypoint_count": len(waypoints),
        "position": {
            "raw_measured": raw_position,
            "current_filtered": filtered_position,
        },
        "speed": {
            "raw_ls": error_summary(raw_speed_estimates, raw_speed_truths),
            "current_tracker": error_summary(
                tracker_speed_estimates, tracker_speed_truths
            ),
            "ground_truth_overall_mps": ground_truth.get("ground_truth_speed_mps"),
        },
        "heading_error_deg": {
            "raw_ls": numeric_summary(raw_heading_errors),
            "current_tracker": numeric_summary(tracker_heading_errors),
            "trusted_population_requires_calibrated_speed": minimum_reliable_speed
            is not None,
        },
        "uncertainty_coverage_diagnostic": uncertainty_coverage(
            coverage_errors, coverage_radii
        ),
        "outlier": {
            "count": sum(bool(point.get("rejected_as_outlier")) for point in points),
            "innovation_m": numeric_summary(
                [
                    float(point["innovation_m"])
                    for point in points
                    if finite_number(point.get("innovation_m")) is not None
                ]
            ),
            "raw_ls_with_outliers": full_raw,
            "raw_ls_diagnostic_excluded": excluded_raw,
        },
        "tracking": {
            "gap_s": gap_metrics(points, expected_interval_s),
            "arrival_out_of_order_count": sum(
                bool(point.get("arrival_out_of_order")) for point in points
            ),
            "late_count": sum(
                point.get("tracking_discard_reason") == "late_measurement_discarded"
                for point in points
            ),
            "duplicate_count": sum(
                point.get("tracking_discard_reason")
                == "duplicate_measurement_discarded"
                for point in points
            ),
        },
        "motion_quality_distribution": dict(sorted(quality_counts.items())),
        "raw_ls_series": raw_series,
        "static": static_metrics,
        "site_motion_shadow": site_motion,
        "thresholds": {
            "minimum_reliable_motion_speed_mps": minimum_reliable_speed,
            "source": "field_ground_truth_metadata"
            if minimum_reliable_speed is not None
            else "not_calibrated",
        },
    }


def aggregate(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in metrics:
        by_scenario[str(item.get("scenario") or "unknown")].append(item)
    return {
        "schema_version": "bi2.motion_field_aggregate.v1",
        "run_count": len(metrics),
        "scenarios": {
            scenario: {
                "run_count": len(items),
                "run_ids": [item.get("run_id") for item in items],
                "node_counts": sorted({int(item.get("node_count") or 0) for item in items}),
                "point_count": sum(int(item.get("point_count") or 0) for item in items),
                "runs": items,
            }
            for scenario, items in sorted(by_scenario.items())
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze BI-2 raw motion field runs")
    parser.add_argument("raw_files", type=Path, nargs="+")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--aggregate-output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    metrics = []
    written = []
    for raw_path in args.raw_files:
        run = load_run(raw_path)
        result = analyze_run(run)
        output_dir = (args.output_dir or raw_path.parent).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / raw_path.name.replace("_raw.json", "_metrics.json")
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        metrics.append(result)
        written.append(str(output_path))
    aggregate_result = aggregate(metrics)
    if args.aggregate_output:
        args.aggregate_output.parent.mkdir(parents=True, exist_ok=True)
        args.aggregate_output.write_text(
            json.dumps(aggregate_result, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {"status": "analyzed", "metrics": written, "aggregate": aggregate_result},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
