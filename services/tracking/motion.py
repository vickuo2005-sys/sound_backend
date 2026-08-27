from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Literal, Optional


EARTH_RADIUS_M = 6_371_008.8
MotionQuality = Literal["insufficient", "low", "medium", "high"]


@dataclass(frozen=True)
class MotionQualityConfig:
    expected_interval_s: float = 1.5
    medium_min_points: int = 3
    high_min_points: int = 5
    medium_min_span_s: float = 3.0
    high_min_span_s: float = 6.0
    medium_max_gap_factor: float = 3.0
    high_max_gap_factor: float = 1.75
    medium_max_mean_uncertainty_m: float = 100.0
    high_max_mean_uncertainty_m: float = 40.0
    medium_max_residual_rmse_m: float = 75.0
    high_max_residual_rmse_m: float = 30.0
    stationary_speed_epsilon_mps: float = 0.05
    max_diagnostic_speed_mps: float = 200.0
    outlier_speed_guard_enabled: bool = False


@dataclass(frozen=True)
class MotionEstimate:
    speed_mps: Optional[float]
    heading_deg: Optional[float]
    vx_mps: Optional[float]
    vy_mps: Optional[float]
    input_count: int
    sample_count: int
    duplicate_count: int
    time_span_s: float
    maximum_gap_s: Optional[float]
    mean_uncertainty_m: Optional[float]
    residual_rmse_m: Optional[float]
    maximum_segment_speed_mps: Optional[float]
    outlier_detected: bool
    valid: bool
    quality: MotionQuality
    ordered_event_time_ms: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _Point:
    event_time_ms: float
    latitude: float
    longitude: float
    uncertainty_m: Optional[float]


def latlng_to_local_xy(
    latitude: float,
    longitude: float,
    reference_latitude: float,
    reference_longitude: float,
) -> tuple[float, float]:
    """Equirectangular local tangent approximation for short track segments."""

    reference_latitude_rad = math.radians(reference_latitude)
    x = (
        EARTH_RADIUS_M
        * math.cos(reference_latitude_rad)
        * math.radians(longitude - reference_longitude)
    )
    y = EARTH_RADIUS_M * math.radians(latitude - reference_latitude)
    return x, y


def local_xy_to_latlng(
    x_m: float,
    y_m: float,
    reference_latitude: float,
    reference_longitude: float,
) -> tuple[float, float]:
    latitude = reference_latitude + math.degrees(y_m / EARTH_RADIUS_M)
    longitude_scale = EARTH_RADIUS_M * math.cos(math.radians(reference_latitude))
    if abs(longitude_scale) < 1e-9:
        raise ValueError("local tangent conversion is undefined at the poles")
    longitude = reference_longitude + math.degrees(x_m / longitude_scale)
    return latitude, longitude


def estimate_constant_velocity(
    points: Iterable[dict[str, Any]],
    *,
    config: MotionQualityConfig = MotionQualityConfig(),
) -> MotionEstimate:
    """Fit raw x(t), y(t) with least squares after event-time ordering.

    Arrival/DB time is never used. Duplicate event times are deterministically
    reduced to their first valid measurement and reported as diagnostics.
    """

    input_points = list(points)
    parsed = sorted(
        (point for item in input_points if (point := _parse_point(item)) is not None),
        key=lambda point: point.event_time_ms,
    )
    unique: list[_Point] = []
    seen_times: set[float] = set()
    duplicate_count = 0
    for point in parsed:
        if point.event_time_ms in seen_times:
            duplicate_count += 1
            continue
        seen_times.add(point.event_time_ms)
        unique.append(point)

    if len(unique) < 2:
        return _insufficient(
            input_count=len(input_points),
            sample_count=len(unique),
            duplicate_count=duplicate_count,
            ordered_times=tuple(point.event_time_ms for point in unique),
        )

    origin = unique[0]
    times_s = [
        (point.event_time_ms - origin.event_time_ms) / 1000.0 for point in unique
    ]
    time_span_s = times_s[-1] - times_s[0]
    if time_span_s <= 0.0:
        return _insufficient(
            input_count=len(input_points),
            sample_count=len(unique),
            duplicate_count=duplicate_count,
            ordered_times=tuple(point.event_time_ms for point in unique),
        )

    xy = [
        latlng_to_local_xy(
            point.latitude,
            point.longitude,
            origin.latitude,
            origin.longitude,
        )
        for point in unique
    ]
    xs = [position[0] for position in xy]
    ys = [position[1] for position in xy]
    vx, intercept_x = _linear_slope_and_intercept(times_s, xs)
    vy, intercept_y = _linear_slope_and_intercept(times_s, ys)
    speed = math.hypot(vx, vy)
    heading = None
    if speed >= max(0.0, config.stationary_speed_epsilon_mps):
        heading = (math.degrees(math.atan2(vx, vy)) + 360.0) % 360.0

    residuals = [
        math.hypot(
            x - (intercept_x + vx * time_s),
            y - (intercept_y + vy * time_s),
        )
        for time_s, x, y in zip(times_s, xs, ys)
    ]
    residual_rmse = math.sqrt(
        sum(residual * residual for residual in residuals) / len(residuals)
    )
    gaps = [later - earlier for earlier, later in zip(times_s, times_s[1:])]
    maximum_gap = max(gaps)
    segment_speeds = [
        math.hypot(x2 - x1, y2 - y1) / gap
        for (x1, y1), (x2, y2), gap in zip(xy, xy[1:], gaps)
        if gap > 0.0
    ]
    maximum_segment_speed = max(segment_speeds) if segment_speeds else None
    outlier_detected = bool(
        maximum_segment_speed is not None
        and maximum_segment_speed > max(0.1, config.max_diagnostic_speed_mps)
    )
    uncertainties = [
        point.uncertainty_m
        for point in unique
        if point.uncertainty_m is not None
    ]
    mean_uncertainty = (
        sum(uncertainties) / len(uncertainties) if uncertainties else None
    )
    quality = _quality(
        sample_count=len(unique),
        time_span_s=time_span_s,
        maximum_gap_s=maximum_gap,
        mean_uncertainty_m=mean_uncertainty,
        residual_rmse_m=residual_rmse,
        duplicate_count=duplicate_count,
        outlier_detected=outlier_detected,
        config=config,
    )
    valid = not (config.outlier_speed_guard_enabled and outlier_detected)

    return MotionEstimate(
        speed_mps=speed,
        heading_deg=heading,
        vx_mps=vx,
        vy_mps=vy,
        input_count=len(input_points),
        sample_count=len(unique),
        duplicate_count=duplicate_count,
        time_span_s=time_span_s,
        maximum_gap_s=maximum_gap,
        mean_uncertainty_m=mean_uncertainty,
        residual_rmse_m=residual_rmse,
        maximum_segment_speed_mps=maximum_segment_speed,
        outlier_detected=outlier_detected,
        valid=valid,
        quality=quality,
        ordered_event_time_ms=tuple(point.event_time_ms for point in unique),
    )


def _quality(
    *,
    sample_count: int,
    time_span_s: float,
    maximum_gap_s: float,
    mean_uncertainty_m: Optional[float],
    residual_rmse_m: float,
    duplicate_count: int,
    outlier_detected: bool,
    config: MotionQualityConfig,
) -> MotionQuality:
    expected_interval = max(0.001, config.expected_interval_s)
    uncertainty_for_high = mean_uncertainty_m is not None and (
        mean_uncertainty_m <= config.high_max_mean_uncertainty_m
    )
    uncertainty_for_medium = mean_uncertainty_m is None or (
        mean_uncertainty_m <= config.medium_max_mean_uncertainty_m
    )
    if (
        not outlier_detected
        and duplicate_count == 0
        and sample_count >= config.high_min_points
        and time_span_s >= config.high_min_span_s
        and maximum_gap_s <= expected_interval * config.high_max_gap_factor
        and uncertainty_for_high
        and residual_rmse_m <= config.high_max_residual_rmse_m
    ):
        return "high"
    if (
        not outlier_detected
        and sample_count >= config.medium_min_points
        and time_span_s >= config.medium_min_span_s
        and maximum_gap_s <= expected_interval * config.medium_max_gap_factor
        and uncertainty_for_medium
        and residual_rmse_m <= config.medium_max_residual_rmse_m
    ):
        return "medium"
    return "low"


def _parse_point(item: dict[str, Any]) -> Optional[_Point]:
    event_time_ms = _finite_number(
        item.get("measurement_time_ms", item.get("event_time_ms"))
    )
    latitude = _first_finite(
        item,
        "measured_lat",
        "latitude",
        "estimated_lat",
        "filtered_lat",
    )
    longitude = _first_finite(
        item,
        "measured_lng",
        "longitude",
        "estimated_lng",
        "filtered_lng",
    )
    uncertainty = _finite_number(item.get("uncertainty_radius_m"))
    if (
        event_time_ms is None
        or latitude is None
        or longitude is None
        or not -90.0 <= latitude <= 90.0
        or not -180.0 <= longitude <= 180.0
    ):
        return None
    return _Point(
        event_time_ms=event_time_ms,
        latitude=latitude,
        longitude=longitude,
        uncertainty_m=max(0.0, uncertainty) if uncertainty is not None else None,
    )


def _linear_slope_and_intercept(
    times_s: list[float], values: list[float]
) -> tuple[float, float]:
    mean_time = sum(times_s) / len(times_s)
    mean_value = sum(values) / len(values)
    denominator = sum((time - mean_time) ** 2 for time in times_s)
    if denominator <= 0.0:
        return 0.0, mean_value
    slope = sum(
        (time - mean_time) * (value - mean_value)
        for time, value in zip(times_s, values)
    ) / denominator
    return slope, mean_value - slope * mean_time


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _first_finite(item: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = _finite_number(item.get(key))
        if value is not None:
            return value
    return None


def _insufficient(
    *,
    input_count: int,
    sample_count: int,
    duplicate_count: int,
    ordered_times: tuple[float, ...],
) -> MotionEstimate:
    return MotionEstimate(
        speed_mps=None,
        heading_deg=None,
        vx_mps=None,
        vy_mps=None,
        input_count=input_count,
        sample_count=sample_count,
        duplicate_count=duplicate_count,
        time_span_s=0.0,
        maximum_gap_s=None,
        mean_uncertainty_m=None,
        residual_rmse_m=None,
        maximum_segment_speed_mps=None,
        outlier_detected=False,
        valid=False,
        quality="insufficient",
        ordered_event_time_ms=ordered_times,
    )
