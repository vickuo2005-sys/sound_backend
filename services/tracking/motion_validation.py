from __future__ import annotations

import math
import statistics
from typing import Any, Iterable, Optional

from services.localization.geo import haversine_m
from services.tracking.motion import estimate_constant_velocity


def finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def percentile(values: Iterable[float], percentile_value: float) -> Optional[float]:
    numbers = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not numbers:
        return None
    percentile_value = min(100.0, max(0.0, float(percentile_value)))
    if len(numbers) == 1:
        return numbers[0]
    rank = (len(numbers) - 1) * percentile_value / 100.0
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return numbers[lower]
    weight = rank - lower
    return numbers[lower] * (1.0 - weight) + numbers[upper] * weight


def numeric_summary(values: Iterable[float]) -> dict[str, Optional[float] | int]:
    numbers = [float(value) for value in values if math.isfinite(float(value))]
    if not numbers:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p50": None,
            "p95": None,
            "max": None,
            "min": None,
        }
    return {
        "count": len(numbers),
        "mean": sum(numbers) / len(numbers),
        "median": statistics.median(numbers),
        "p50": percentile(numbers, 50.0),
        "p95": percentile(numbers, 95.0),
        "max": max(numbers),
        "min": min(numbers),
    }


def error_summary(
    estimates: Iterable[float], truths: Iterable[float]
) -> dict[str, Any]:
    pairs = [
        (float(estimate), float(truth))
        for estimate, truth in zip(estimates, truths)
        if math.isfinite(float(estimate)) and math.isfinite(float(truth))
    ]
    if not pairs:
        return {
            "count": 0,
            "mae": None,
            "rmse": None,
            "bias": None,
            "mean": None,
            "median": None,
            "p50": None,
            "p95": None,
            "max": None,
            "min": None,
            "estimate_standard_deviation": None,
            "relative_absolute_error_percent": numeric_summary([]),
        }
    signed = [estimate - truth for estimate, truth in pairs]
    absolute = [abs(value) for value in signed]
    estimate_values = [estimate for estimate, _ in pairs]
    relative_absolute_percent = [
        abs(estimate - truth) * 100.0 / abs(truth)
        for estimate, truth in pairs
        if abs(truth) > 1e-9
    ]
    summary = numeric_summary(absolute)
    return {
        **summary,
        "mae": sum(absolute) / len(absolute),
        "rmse": math.sqrt(sum(value * value for value in signed) / len(signed)),
        "bias": sum(signed) / len(signed),
        "estimate_standard_deviation": statistics.pstdev(estimate_values),
        "relative_absolute_error_percent": numeric_summary(
            relative_absolute_percent
        ),
    }


def circular_heading_error_deg(estimate: float, truth: float) -> float:
    if not math.isfinite(float(estimate)) or not math.isfinite(float(truth)):
        raise ValueError("heading values must be finite")
    difference = abs((float(estimate) - float(truth)) % 360.0)
    return min(difference, 360.0 - difference)


def uncertainty_coverage(
    actual_errors_m: Iterable[float], uncertainty_radii_m: Iterable[float]
) -> dict[str, Optional[float] | int]:
    pairs = [
        (max(0.0, float(error)), max(0.0, float(radius)))
        for error, radius in zip(actual_errors_m, uncertainty_radii_m)
        if math.isfinite(float(error)) and math.isfinite(float(radius))
    ]
    if not pairs:
        return {
            "count": 0,
            "covered_count": 0,
            "coverage_rate": None,
            "underestimated_count": 0,
            "mean_error_to_radius_ratio": None,
        }
    covered = sum(error <= radius for error, radius in pairs)
    ratios = [
        error / radius
        for error, radius in pairs
        if radius > 0.0
    ]
    return {
        "count": len(pairs),
        "covered_count": covered,
        "coverage_rate": covered / len(pairs),
        "underestimated_count": len(pairs) - covered,
        "mean_error_to_radius_ratio": (
            sum(ratios) / len(ratios) if ratios else None
        ),
    }


def classify_site_motion(
    points: Iterable[dict[str, Any]],
    *,
    site_latitude: float,
    site_longitude: float,
    minimum_reliable_speed_mps: Optional[float],
    minimum_closing_speed_mps: Optional[float] = None,
    minimum_samples: int = 3,
) -> dict[str, Any]:
    """Classify site-relative motion from multiple event-time samples.

    Thresholds are mandatory inputs from field calibration. There is no hidden
    production threshold and the result is diagnostic-only.
    """

    if minimum_reliable_speed_mps is None:
        return {
            "classification": "UNCERTAIN",
            "reason": "minimum_reliable_speed_not_calibrated",
            "sample_count": 0,
            "closing_speed_mps": None,
        }
    reliable_speed = max(0.0, float(minimum_reliable_speed_mps))
    closing_threshold = (
        reliable_speed
        if minimum_closing_speed_mps is None
        else max(0.0, float(minimum_closing_speed_mps))
    )
    usable = []
    for point in points:
        time_ms = finite_number(
            point.get("measurement_time_ms", point.get("event_time_ms"))
        )
        latitude = finite_number(point.get("filtered_lat"))
        longitude = finite_number(point.get("filtered_lng"))
        if latitude is None or longitude is None:
            latitude = finite_number(point.get("measured_lat"))
            longitude = finite_number(point.get("measured_lng"))
        if time_ms is None or latitude is None or longitude is None:
            continue
        usable.append(
            {
                "measurement_time_ms": time_ms,
                "measured_lat": latitude,
                "measured_lng": longitude,
                "uncertainty_radius_m": point.get("uncertainty_radius_m"),
                "distance_m": haversine_m(
                    latitude,
                    longitude,
                    float(site_latitude),
                    float(site_longitude),
                ),
            }
        )
    usable.sort(key=lambda point: point["measurement_time_ms"])
    unique = []
    seen_times = set()
    for point in usable:
        if point["measurement_time_ms"] in seen_times:
            continue
        seen_times.add(point["measurement_time_ms"])
        unique.append(point)
    if len(unique) < max(3, int(minimum_samples)):
        return {
            "classification": "UNCERTAIN",
            "reason": "insufficient_samples",
            "sample_count": len(unique),
            "closing_speed_mps": None,
        }

    estimate = estimate_constant_velocity(unique)
    if estimate.quality in {"insufficient", "low"} or not estimate.valid:
        return {
            "classification": "UNCERTAIN",
            "reason": "motion_quality_unreliable",
            "sample_count": len(unique),
            "closing_speed_mps": None,
            "motion_quality": estimate.quality,
            "speed_mps": estimate.speed_mps,
        }
    if estimate.speed_mps is None or estimate.speed_mps < reliable_speed:
        return {
            "classification": "STATIONARY",
            "reason": "below_reliable_speed",
            "sample_count": len(unique),
            "closing_speed_mps": 0.0,
            "motion_quality": estimate.quality,
            "speed_mps": estimate.speed_mps,
        }

    origin_time = unique[0]["measurement_time_ms"]
    times_s = [
        (point["measurement_time_ms"] - origin_time) / 1000.0
        for point in unique
    ]
    distances = [point["distance_m"] for point in unique]
    mean_time = sum(times_s) / len(times_s)
    mean_distance = sum(distances) / len(distances)
    denominator = sum((time - mean_time) ** 2 for time in times_s)
    if denominator <= 0.0:
        return {
            "classification": "UNCERTAIN",
            "reason": "zero_time_span",
            "sample_count": len(unique),
            "closing_speed_mps": None,
        }
    distance_slope = sum(
        (time - mean_time) * (distance - mean_distance)
        for time, distance in zip(times_s, distances)
    ) / denominator
    closing_speed = -distance_slope
    if closing_speed >= closing_threshold:
        classification = "APPROACHING"
        reason = "distance_trend_decreasing"
    elif closing_speed <= -closing_threshold:
        classification = "DEPARTING"
        reason = "distance_trend_increasing"
    else:
        classification = "UNCERTAIN"
        reason = "site_projection_below_threshold"
    return {
        "classification": classification,
        "reason": reason,
        "sample_count": len(unique),
        "closing_speed_mps": closing_speed,
        "motion_quality": estimate.quality,
        "speed_mps": estimate.speed_mps,
        "distance_start_m": distances[0],
        "distance_end_m": distances[-1],
    }
