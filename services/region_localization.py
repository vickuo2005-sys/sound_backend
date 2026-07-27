import math
from typing import Any, Optional


UNKNOWN_REGION = "unknown"
SINGLE_NODE_REGION = "single_node"
SEGMENT_REGION = "segment"
POLYGON_REGION = "polygon"
REGION_METHOD = "multi_node_region"


def _parse_float(value: Any) -> Optional[float]:
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


def _valid_lat_lng(latitude: Any, longitude: Any) -> Optional[tuple[float, float]]:
    lat = _parse_float(latitude)
    lng = _parse_float(longitude)
    if lat is None or lng is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    return lat, lng


def _dedupe_reporting_devices(observations: list[dict]) -> list[dict]:
    by_device: dict[str, dict] = {}
    for item in observations:
        device_id = str(item.get("device_id") or "").strip()
        if not device_id:
            continue
        lat_lng = _valid_lat_lng(item.get("latitude"), item.get("longitude"))
        if lat_lng is None:
            continue
        lat, lng = lat_lng
        by_device[device_id] = {
            **item,
            "device_id": device_id,
            "latitude": lat,
            "longitude": lng,
        }
    return [by_device[device_id] for device_id in sorted(by_device)]


def _unique_points(reports: list[dict]) -> list[tuple[float, float]]:
    seen: set[tuple[float, float]] = set()
    points: list[tuple[float, float]] = []
    for item in reports:
        point = (float(item["longitude"]), float(item["latitude"]))
        if point in seen:
            continue
        seen.add(point)
        points.append(point)
    return points


def _cross(
    origin: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    sorted_points = sorted(set(points))
    if len(sorted_points) <= 1:
        return sorted_points

    lower: list[tuple[float, float]] = []
    for point in sorted_points:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(sorted_points):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def _polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        total += point[0] * next_point[1] - next_point[0] * point[1]
    return total / 2.0


def _polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    area = _polygon_area(points)
    if abs(area) < 1e-18:
        return _mean_center(points)

    factor = 0.0
    centroid_x = 0.0
    centroid_y = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        factor = point[0] * next_point[1] - next_point[0] * point[1]
        centroid_x += (point[0] + next_point[0]) * factor
        centroid_y += (point[1] + next_point[1]) * factor

    scale = 1.0 / (6.0 * area)
    return centroid_x * scale, centroid_y * scale


def _mean_center(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _segment_region(
    reports: list[dict],
    points: list[tuple[float, float]],
) -> dict:
    ordered = sorted(points)
    start = ordered[0]
    end = ordered[-1]
    center_lng = (start[0] + end[0]) / 2.0
    center_lat = (start[1] + end[1]) / 2.0
    return _base_region(
        reports=reports,
        region_type=SEGMENT_REGION,
        center_lat=center_lat,
        center_lng=center_lng,
        geometry={
            "type": "LineString",
            "coordinates": [[start[0], start[1]], [end[0], end[1]]],
        },
    )


def _base_region(
    reports: list[dict],
    region_type: str,
    center_lat: Optional[float],
    center_lng: Optional[float],
    geometry: Optional[dict],
) -> dict:
    device_ids = [item["device_id"] for item in reports]
    return {
        "region_type": region_type,
        "region_center_lat": center_lat,
        "region_center_lng": center_lng,
        "region_geojson": geometry,
        "reporting_node_count": len(device_ids),
        "reporting_device_ids": device_ids,
        "localization_method": REGION_METHOD,
        "estimated_lat": center_lat,
        "estimated_lng": center_lng,
    }


def estimate_region(observations: list[dict]) -> dict:
    """Estimate an approximate source region from unique reporting node GPS.

    This intentionally avoids TDOA, GCC-PHAT, sample timing, or acoustic
    distance calculations. The output is a coarse region inferred from which
    nodes reported the same fused event.
    """
    reports = _dedupe_reporting_devices(observations)
    points = _unique_points(reports)

    if not reports or not points:
        return _base_region(
            reports=[],
            region_type=UNKNOWN_REGION,
            center_lat=None,
            center_lng=None,
            geometry=None,
        )

    if len(points) == 1:
        lng, lat = points[0]
        return _base_region(
            reports=reports,
            region_type=SINGLE_NODE_REGION,
            center_lat=lat,
            center_lng=lng,
            geometry={
                "type": "Point",
                "coordinates": [lng, lat],
            },
        )

    if len(points) == 2:
        return _segment_region(reports, points)

    hull = _convex_hull(points)
    if len(hull) < 3 or abs(_polygon_area(hull)) < 1e-18:
        return _segment_region(reports, points)

    center_lng, center_lat = _polygon_centroid(hull)
    closed_hull = hull + [hull[0]]
    return _base_region(
        reports=reports,
        region_type=POLYGON_REGION,
        center_lat=center_lat,
        center_lng=center_lng,
        geometry={
            "type": "Polygon",
            "coordinates": [[[lng, lat] for lng, lat in closed_hull]],
        },
    )
