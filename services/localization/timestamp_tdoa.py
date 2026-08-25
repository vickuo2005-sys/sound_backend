import hashlib
import json
import math
from typing import Any, Optional

from .geo import (
    convex_hull_area_m2,
    haversine_m,
    latlng_to_xy,
    max_pair_distance_m,
    origin_from_points,
    parse_float,
    xy_to_latlng,
)


SOUND_SPEED_MPS = 343.0
QUALITY_RANK = {
    "good": 0,
    "medium": 1,
    "fair": 1,
    "poor": 2,
    "bad": 3,
    "stale": 4,
    "missing": 5,
    "unknown": 5,
}


def normalize_quality(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in QUALITY_RANK else "unknown"


def observation_weight(observation: dict) -> float:
    rtt = parse_float(observation.get("time_sync_rtt_ms"))
    quality = normalize_quality(observation.get("time_sync_quality"))
    quality_penalty = 1.0 + QUALITY_RANK.get(quality, 5) * 0.45
    rtt_penalty = 1.0 + min(max(rtt or 0.0, 0.0), 500.0) / 180.0
    probability = parse_float(
        observation.get("aircraft_probability")
        or observation.get("ai_probability")
        or observation.get("probability_aircraft")
    )
    probability_factor = max(min(probability if probability is not None else 0.75, 1.0), 0.1)
    return probability_factor / (quality_penalty * rtt_penalty)


def choose_best_observations(observations: list[dict]) -> list[dict]:
    by_device: dict[str, dict] = {}
    for observation in observations:
        device_id = str(observation.get("device_id") or "").strip()
        corrected_time = parse_float(observation.get("corrected_arrival_time_ms"))
        lat = parse_float(observation.get("latitude"))
        lng = parse_float(observation.get("longitude"))
        if not device_id or corrected_time is None or lat is None or lng is None:
            continue

        candidate = {
            **observation,
            "device_id": device_id,
            "latitude": lat,
            "longitude": lng,
            "corrected_arrival_time_ms": corrected_time,
            "time_sync_rtt_ms": parse_float(observation.get("time_sync_rtt_ms")),
            "time_sync_age_ms": parse_float(observation.get("time_sync_age_ms")),
            "time_sync_quality": normalize_quality(observation.get("time_sync_quality")),
        }
        existing = by_device.get(device_id)
        if existing is None:
            by_device[device_id] = candidate
            continue

        current_key = (
            QUALITY_RANK.get(candidate["time_sync_quality"], 5),
            candidate["time_sync_rtt_ms"] if candidate["time_sync_rtt_ms"] is not None else 999999.0,
            candidate["time_sync_age_ms"] if candidate["time_sync_age_ms"] is not None else 999999.0,
            -candidate["corrected_arrival_time_ms"],
        )
        existing_key = (
            QUALITY_RANK.get(existing["time_sync_quality"], 5),
            existing["time_sync_rtt_ms"] if existing["time_sync_rtt_ms"] is not None else 999999.0,
            existing["time_sync_age_ms"] if existing["time_sync_age_ms"] is not None else 999999.0,
            -existing["corrected_arrival_time_ms"],
        )
        if current_key < existing_key:
            by_device[device_id] = candidate

    return sorted(by_device.values(), key=lambda item: item["device_id"])


def weighted_centroid(observations: list[dict]) -> tuple[float, float]:
    weights = [max(observation_weight(item), 1e-6) for item in observations]
    total = sum(weights)
    return (
        sum(float(item["latitude"]) * weight for item, weight in zip(observations, weights)) / total,
        sum(float(item["longitude"]) * weight for item, weight in zip(observations, weights)) / total,
    )


def geometry_quality(observations: list[dict]) -> tuple[str, dict]:
    if len(observations) < 3:
        return "insufficient", {"node_spread_m": 0.0, "hull_area_m2": 0.0}

    origin_lat, origin_lng = origin_from_points(observations)
    points_xy = [
        latlng_to_xy(float(item["latitude"]), float(item["longitude"]), origin_lat, origin_lng)
        for item in observations
    ]
    spread = max_pair_distance_m(observations)
    area = convex_hull_area_m2(points_xy)
    if spread < 5.0 or area < 10.0:
        quality = "poor"
    elif spread < 25.0 or area < 150.0:
        quality = "fair"
    else:
        quality = "good"
    return quality, {"node_spread_m": spread, "hull_area_m2": area}


def physical_consistency(observations: list[dict], tolerance_ms: float = 10.0) -> tuple[bool, list[dict]]:
    failures = []
    for index, first in enumerate(observations):
        for second in observations[index + 1 :]:
            distance_m = haversine_m(
                float(first["latitude"]),
                float(first["longitude"]),
                float(second["latitude"]),
                float(second["longitude"]),
            )
            delta_ms = abs(
                float(first["corrected_arrival_time_ms"])
                - float(second["corrected_arrival_time_ms"])
            )
            allowed_ms = distance_m / SOUND_SPEED_MPS * 1000.0 + tolerance_ms
            if delta_ms > allowed_ms:
                failures.append(
                    {
                        "first_device_id": first["device_id"],
                        "second_device_id": second["device_id"],
                        "distance_m": distance_m,
                        "delta_ms": delta_ms,
                        "allowed_ms": allowed_ms,
                    }
                )
    return not failures, failures


def input_signature(observations: list[dict], method: str) -> str:
    payload = [
        {
            "event_id": item.get("event_id"),
            "device_id": item.get("device_id"),
            "lat": round(float(item["latitude"]), 8),
            "lng": round(float(item["longitude"]), 8),
            "t": round(float(item["corrected_arrival_time_ms"]), 3),
        }
        for item in observations
    ]
    text = json.dumps({"method": method, "observations": payload}, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fallback_result(
    observations: list[dict],
    reason: str,
    version: str,
    method: str = "weighted_centroid_fallback",
    diagnostics: Optional[dict] = None,
) -> dict:
    if len(observations) < 1:
        return {
            "status": "FAILED",
            "method": method,
            "version": version,
            "failure_reason": reason,
            "diagnostics": diagnostics or {},
        }

    estimated_lat, estimated_lng = weighted_centroid(observations)
    geom_quality, geom = geometry_quality(observations)
    confidence = max(0.15, min(0.55, 0.18 + len(observations) * 0.08))
    uncertainty = max(80.0, geom.get("node_spread_m", 0.0) + 80.0)
    return {
        "status": "FALLBACK",
        "method": method,
        "version": version,
        "estimated_lat": estimated_lat,
        "estimated_lng": estimated_lng,
        "confidence": confidence,
        "residual_m": None,
        "uncertainty_radius_m": uncertainty,
        "geometry_quality": geom_quality,
        "reference_device_id": None,
        "node_count": len({item["device_id"] for item in observations}),
        "event_time_ms": min(float(item["corrected_arrival_time_ms"]) for item in observations),
        "input_signature": input_signature(observations, method),
        "failure_reason": reason,
        "diagnostics": {**(diagnostics or {}), **geom},
    }


def estimate_timestamp_tdoa(
    observations: list[dict],
    *,
    sound_speed_mps: float = SOUND_SPEED_MPS,
    max_rtt_ms: float = 200.0,
    max_sync_age_ms: float = 120_000.0,
    physical_tolerance_ms: float = 10.0,
    search_margin_m: float = 500.0,
    max_residual_m: float = 100.0,
    version: str = "v3.3-timestamp-tdoa",
) -> dict:
    selected = choose_best_observations(observations)
    diagnostics: dict[str, Any] = {
        "input_count": len(observations),
        "selected_device_ids": [item["device_id"] for item in selected],
        "rejected": [],
    }

    eligible = []
    for item in selected:
        rtt = item.get("time_sync_rtt_ms")
        age = item.get("time_sync_age_ms")
        quality = normalize_quality(item.get("time_sync_quality"))
        rejection = None
        if rtt is not None and rtt > max_rtt_ms:
            rejection = "rtt_too_high"
        elif age is not None and age > max_sync_age_ms:
            rejection = "sync_stale"
        elif quality in {"bad", "stale", "missing", "unknown"}:
            rejection = f"sync_{quality}"

        if rejection:
            diagnostics["rejected"].append({"device_id": item["device_id"], "reason": rejection})
            continue
        eligible.append(item)

    if len(eligible) < 3:
        return fallback_result(
            eligible or selected,
            "insufficient_eligible_nodes",
            version,
            diagnostics=diagnostics,
        )

    geom_quality, geom = geometry_quality(eligible)
    diagnostics.update(geom)
    if geom_quality == "poor":
        return fallback_result(
            eligible,
            "poor_geometry",
            version,
            diagnostics=diagnostics,
        )

    is_physical, physical_failures = physical_consistency(
        eligible,
        tolerance_ms=physical_tolerance_ms,
    )
    diagnostics["physical_failures"] = physical_failures
    if not is_physical:
        return fallback_result(
            eligible,
            "physically_inconsistent",
            version,
            diagnostics=diagnostics,
        )

    try:
        from scipy.optimize import least_squares
    except Exception:
        return fallback_result(
            eligible,
            "scipy_unavailable",
            version,
            diagnostics=diagnostics,
        )

    origin_lat, origin_lng = origin_from_points(eligible)
    nodes = []
    for item in eligible:
        x, y = latlng_to_xy(
            float(item["latitude"]),
            float(item["longitude"]),
            origin_lat,
            origin_lng,
        )
        nodes.append({**item, "x": x, "y": y})

    reference = min(nodes, key=lambda item: float(item["corrected_arrival_time_ms"]))
    centroid_lat, centroid_lng = weighted_centroid(eligible)
    initial_x, initial_y = latlng_to_xy(centroid_lat, centroid_lng, origin_lat, origin_lng)
    min_arrival_ms = min(float(item["corrected_arrival_time_ms"]) for item in nodes)
    for node in nodes:
        node["arrival_s"] = (
            float(node["corrected_arrival_time_ms"]) - min_arrival_ms
        ) / 1000.0

    def residuals(params: Any) -> list[float]:
        source_x = float(params[0])
        source_y = float(params[1])
        emission_s = float(params[2])
        values = []
        for node in nodes:
            distance = math.hypot(source_x - node["x"], source_y - node["y"])
            values.append(distance - sound_speed_mps * (float(node["arrival_s"]) - emission_s))
        return values

    min_x = min(node["x"] for node in nodes) - search_margin_m
    max_x = max(node["x"] for node in nodes) + search_margin_m
    min_y = min(node["y"] for node in nodes) - search_margin_m
    max_y = max(node["y"] for node in nodes) + search_margin_m
    max_spread_m = max_pair_distance_m(eligible) + search_margin_m
    min_emission_s = -(max_spread_m / sound_speed_mps) - 1.0

    try:
        starts = [
            [initial_x, initial_y, -0.05],
            [0.0, 0.0, -0.05],
            [min_x, min_y, min_emission_s / 2.0],
            [max_x, min_y, min_emission_s / 2.0],
            [max_x, max_y, min_emission_s / 2.0],
            [min_x, max_y, min_emission_s / 2.0],
        ]
        candidates = [
            least_squares(
                residuals,
                start,
                bounds=([min_x, min_y, min_emission_s], [max_x, max_y, 0.0]),
                loss="soft_l1",
            )
            for start in starts
        ]
        result = min(candidates, key=lambda item: float(getattr(item, "cost", float("inf"))))
    except Exception as exc:
        return fallback_result(
            eligible,
            "solver_failed",
            version,
            diagnostics={**diagnostics, "solver_error": str(exc)},
        )

    residual_values = residuals(result.x)
    residual_rmse = math.sqrt(
        sum(value * value for value in residual_values) / max(len(residual_values), 1)
    )
    if residual_rmse > max_residual_m:
        return fallback_result(
            eligible,
            "residual_too_high",
            version,
            diagnostics={**diagnostics, "residual_rmse_m": residual_rmse},
        )

    estimated_lat, estimated_lng = xy_to_latlng(
        float(result.x[0]),
        float(result.x[1]),
        origin_lat,
        origin_lng,
    )
    rtts = [float(item["time_sync_rtt_ms"] or 0.0) for item in eligible]
    avg_rtt = sum(rtts) / len(rtts)
    node_count = len({item["device_id"] for item in eligible})
    geometry_bonus = {"good": 0.12, "fair": 0.04}.get(geom_quality, -0.12)
    confidence = 0.55 + min(node_count - 3, 3) * 0.06 + geometry_bonus
    confidence -= min(avg_rtt, 250.0) / 1200.0
    confidence -= min(residual_rmse, max_residual_m) / 360.0
    confidence = max(0.25, min(0.95, confidence))
    uncertainty = max(20.0, residual_rmse + avg_rtt * 0.343 + (20.0 if geom_quality == "fair" else 8.0))

    residual_by_device = {}
    for node, residual in zip(nodes, residual_values):
        residual_by_device[str(node["device_id"])] = float(residual)

    diagnostics.update(
        {
            "origin_lat": origin_lat,
            "origin_lng": origin_lng,
            "reference_device_id": reference["device_id"],
            "average_rtt_ms": avg_rtt,
            "residual_by_device": residual_by_device,
            "solver_cost": float(getattr(result, "cost", 0.0)),
        }
    )

    return {
        "status": "SUCCESS",
        "method": "timestamp_tdoa",
        "version": version,
        "estimated_lat": estimated_lat,
        "estimated_lng": estimated_lng,
        "confidence": confidence,
        "residual_m": residual_rmse,
        "uncertainty_radius_m": uncertainty,
        "geometry_quality": geom_quality,
        "reference_device_id": reference["device_id"],
        "node_count": node_count,
        "event_time_ms": min(float(item["corrected_arrival_time_ms"]) for item in eligible),
        "input_signature": input_signature(eligible, "timestamp_tdoa"),
        "diagnostics": diagnostics,
    }
