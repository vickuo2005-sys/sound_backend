import math
from datetime import datetime, timezone
from typing import Optional

from services.localization.geo import haversine_m, latlng_to_xy, xy_to_latlng


def parse_time_ms(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text)
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp() * 1000.0
        except ValueError:
            return None
    return None


def heading_deg(vx: float, vy: float) -> Optional[float]:
    speed = math.hypot(vx, vy)
    if speed < 0.05:
        return None
    return (math.degrees(math.atan2(vx, vy)) + 360.0) % 360.0


def predict_state(track: dict, measurement_time_ms: float) -> dict:
    origin_lat = float(track["origin_lat"])
    origin_lng = float(track["origin_lng"])
    last_time_ms = parse_time_ms(track.get("last_event_time_ms")) or measurement_time_ms
    last_x, last_y = latlng_to_xy(
        float(track["last_lat"]),
        float(track["last_lng"]),
        origin_lat,
        origin_lng,
    )
    vx = float(track.get("velocity_east_mps") or 0.0)
    vy = float(track.get("velocity_north_mps") or 0.0)
    dt = max((measurement_time_ms - last_time_ms) / 1000.0, 0.0)
    return {
        "x": last_x + vx * dt,
        "y": last_y + vy * dt,
        "vx": vx,
        "vy": vy,
        "dt": dt,
        "last_time_ms": last_time_ms,
    }


def update_track_from_measurement(
    track: Optional[dict],
    measurement: dict,
    *,
    alpha: float = 0.70,
    beta: float = 0.35,
) -> dict:
    measurement_time_ms = parse_time_ms(measurement.get("event_time_ms")) or datetime.now(
        timezone.utc
    ).timestamp() * 1000.0
    measured_lat = float(measurement["estimated_lat"])
    measured_lng = float(measurement["estimated_lng"])

    if track is None:
        return {
            "origin_lat": measured_lat,
            "origin_lng": measured_lng,
            "filtered_lat": measured_lat,
            "filtered_lng": measured_lng,
            "predicted_lat": measured_lat,
            "predicted_lng": measured_lng,
            "velocity_east_mps": 0.0,
            "velocity_north_mps": 0.0,
            "speed_mps": 0.0,
            "heading_deg": None,
            "measurement_time_ms": measurement_time_ms,
            "innovation_m": 0.0,
            "rejected_as_outlier": False,
            "state_json": {
                "x": 0.0,
                "y": 0.0,
                "vx": 0.0,
                "vy": 0.0,
                "alpha": alpha,
                "beta": beta,
            },
            "covariance_json": {
                "uncertainty_radius_m": measurement.get("uncertainty_radius_m"),
            },
        }

    origin_lat = float(track["origin_lat"])
    origin_lng = float(track["origin_lng"])
    measurement_x, measurement_y = latlng_to_xy(
        measured_lat,
        measured_lng,
        origin_lat,
        origin_lng,
    )
    predicted = predict_state(track, measurement_time_ms)
    residual_x = measurement_x - predicted["x"]
    residual_y = measurement_y - predicted["y"]
    innovation_m = math.hypot(residual_x, residual_y)
    dt = max(predicted["dt"], 0.001)

    filtered_x = predicted["x"] + alpha * residual_x
    filtered_y = predicted["y"] + alpha * residual_y
    vx = predicted["vx"] + beta * residual_x / dt
    vy = predicted["vy"] + beta * residual_y / dt
    filtered_lat, filtered_lng = xy_to_latlng(filtered_x, filtered_y, origin_lat, origin_lng)
    predicted_lat, predicted_lng = xy_to_latlng(
        filtered_x + vx,
        filtered_y + vy,
        origin_lat,
        origin_lng,
    )
    speed = math.hypot(vx, vy)

    return {
        "origin_lat": origin_lat,
        "origin_lng": origin_lng,
        "filtered_lat": filtered_lat,
        "filtered_lng": filtered_lng,
        "predicted_lat": predicted_lat,
        "predicted_lng": predicted_lng,
        "velocity_east_mps": vx,
        "velocity_north_mps": vy,
        "speed_mps": speed,
        "heading_deg": heading_deg(vx, vy),
        "measurement_time_ms": measurement_time_ms,
        "innovation_m": innovation_m,
        "rejected_as_outlier": False,
        "state_json": {
            "x": filtered_x,
            "y": filtered_y,
            "vx": vx,
            "vy": vy,
            "alpha": alpha,
            "beta": beta,
        },
        "covariance_json": {
            "uncertainty_radius_m": measurement.get("uncertainty_radius_m"),
            "innovation_m": innovation_m,
        },
    }


def can_associate_track(
    track: dict,
    measurement: dict,
    *,
    max_gap_seconds: float = 15.0,
    max_speed_mps: float = 50.0,
    base_gate_m: float = 30.0,
) -> tuple[bool, dict]:
    if str(track.get("label") or "").lower() != str(measurement.get("label") or "").lower():
        return False, {"reason": "label_mismatch"}

    measurement_time_ms = parse_time_ms(measurement.get("event_time_ms"))
    last_time_ms = parse_time_ms(track.get("last_event_time_ms"))
    if measurement_time_ms is None or last_time_ms is None:
        return False, {"reason": "missing_time"}

    gap_s = (measurement_time_ms - last_time_ms) / 1000.0
    if gap_s < -1.0:
        return False, {"reason": "measurement_before_track"}
    if gap_s > max_gap_seconds:
        return False, {"reason": "gap_too_large", "gap_s": gap_s}

    predicted = predict_state(track, measurement_time_ms)
    predicted_lat, predicted_lng = xy_to_latlng(
        predicted["x"],
        predicted["y"],
        float(track["origin_lat"]),
        float(track["origin_lng"]),
    )
    distance_m = haversine_m(
        predicted_lat,
        predicted_lng,
        float(measurement["estimated_lat"]),
        float(measurement["estimated_lng"]),
    )
    uncertainty = float(measurement.get("uncertainty_radius_m") or 0.0)
    gate_m = base_gate_m + max_speed_mps * max(gap_s, 0.0) + uncertainty
    return distance_m <= gate_m, {
        "distance_m": distance_m,
        "gate_m": gate_m,
        "gap_s": gap_s,
    }
