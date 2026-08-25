import math
from typing import Any, Optional


VALID_LOCATION_SOURCES = {"manual_map", "current_gps"}
FIXED_SOURCE = "fixed"
EVENT_GPS_SOURCE = "event_gps"
NO_LOCATION_SOURCE = "none"


class DeviceLocationValidationError(ValueError):
    pass


def parse_finite_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def valid_latitude(value: Any) -> Optional[float]:
    number = parse_finite_float(value)
    if number is None or not -90.0 <= number <= 90.0:
        return None
    return number


def valid_longitude(value: Any) -> Optional[float]:
    number = parse_finite_float(value)
    if number is None or not -180.0 <= number <= 180.0:
        return None
    return number


def valid_lat_lng(latitude: Any, longitude: Any) -> Optional[tuple[float, float]]:
    lat = valid_latitude(latitude)
    lng = valid_longitude(longitude)
    if lat is None or lng is None:
        return None
    return lat, lng


def validate_device_location(
    *,
    device_id: Any,
    latitude: Any,
    longitude: Any,
    location_source: Any,
    accuracy_m: Any = None,
) -> dict:
    normalized_device_id = str(device_id or "").strip()
    if not normalized_device_id:
        raise DeviceLocationValidationError("device_id is required")

    lat = valid_latitude(latitude)
    if lat is None:
        raise DeviceLocationValidationError("latitude must be between -90 and 90")

    lng = valid_longitude(longitude)
    if lng is None:
        raise DeviceLocationValidationError("longitude must be between -180 and 180")

    source = str(location_source or "").strip().lower()
    if source not in VALID_LOCATION_SOURCES:
        raise DeviceLocationValidationError(
            "location_source must be manual_map or current_gps"
        )

    accuracy = parse_finite_float(accuracy_m)
    if accuracy_m is not None and accuracy is None:
        raise DeviceLocationValidationError("accuracy_m must be a finite number")
    if accuracy is not None and accuracy < 0:
        raise DeviceLocationValidationError("accuracy_m must be >= 0")

    return {
        "device_id": normalized_device_id,
        "latitude": lat,
        "longitude": lng,
        "location_source": source,
        "accuracy_m": accuracy,
    }


def normalize_location_row(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    return {
        "device_id": str(row.get("device_id") or "").strip(),
        "latitude": valid_latitude(row.get("latitude")),
        "longitude": valid_longitude(row.get("longitude")),
        "location_source": str(row.get("location_source") or "").strip().lower(),
        "accuracy_m": parse_finite_float(row.get("accuracy_m")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def location_map(rows: list[dict]) -> dict[str, dict]:
    output: dict[str, dict] = {}
    for row in rows:
        normalized = normalize_location_row(row)
        if (
            normalized
            and normalized["device_id"]
            and normalized["latitude"] is not None
            and normalized["longitude"] is not None
        ):
            output[normalized["device_id"]] = normalized
    return output


def resolve_effective_location(
    *,
    device_id: Any,
    event_latitude: Any,
    event_longitude: Any,
    fixed_locations: Optional[dict[str, dict]] = None,
) -> Optional[dict]:
    normalized_device_id = str(device_id or "").strip()
    fixed = (fixed_locations or {}).get(normalized_device_id)
    fixed_lat_lng = (
        valid_lat_lng(fixed.get("latitude"), fixed.get("longitude"))
        if fixed
        else None
    )
    if fixed_lat_lng is not None:
        lat, lng = fixed_lat_lng
        return {
            "device_id": normalized_device_id,
            "latitude": lat,
            "longitude": lng,
            "effective_location_source": FIXED_SOURCE,
            "fixed_location": fixed,
        }

    event_lat_lng = valid_lat_lng(event_latitude, event_longitude)
    if event_lat_lng is not None:
        lat, lng = event_lat_lng
        return {
            "device_id": normalized_device_id,
            "latitude": lat,
            "longitude": lng,
            "effective_location_source": EVENT_GPS_SOURCE,
            "fixed_location": None,
        }

    return None
