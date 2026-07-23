import math
from typing import Iterable, Optional


EARTH_RADIUS_M = 6_371_000.0
METERS_PER_DEGREE_LAT = 111_320.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def origin_from_points(points: Iterable[dict]) -> tuple[float, float]:
    values = [
        (float(item["latitude"]), float(item["longitude"]))
        for item in points
        if item.get("latitude") is not None and item.get("longitude") is not None
    ]
    if not values:
        return 0.0, 0.0
    return (
        sum(lat for lat, _ in values) / len(values),
        sum(lng for _, lng in values) / len(values),
    )


def latlng_to_xy(
    lat: float,
    lng: float,
    origin_lat: float,
    origin_lng: float,
) -> tuple[float, float]:
    meters_per_degree_lng = METERS_PER_DEGREE_LAT * math.cos(math.radians(origin_lat))
    return (
        (lng - origin_lng) * meters_per_degree_lng,
        (lat - origin_lat) * METERS_PER_DEGREE_LAT,
    )


def xy_to_latlng(
    x: float,
    y: float,
    origin_lat: float,
    origin_lng: float,
) -> tuple[float, float]:
    meters_per_degree_lng = METERS_PER_DEGREE_LAT * math.cos(math.radians(origin_lat))
    return (
        origin_lat + (y / METERS_PER_DEGREE_LAT),
        origin_lng + (x / meters_per_degree_lng),
    )


def convex_hull_area_m2(points_xy: list[tuple[float, float]]) -> float:
    if len(points_xy) < 3:
        return 0.0

    points = sorted(set(points_xy))
    if len(points) < 3:
        return 0.0

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]
    area = 0.0
    for index, first in enumerate(hull):
        second = hull[(index + 1) % len(hull)]
        area += first[0] * second[1] - second[0] * first[1]
    return abs(area) / 2.0


def max_pair_distance_m(points: list[dict]) -> float:
    maximum = 0.0
    for index, first in enumerate(points):
        for second in points[index + 1 :]:
            maximum = max(
                maximum,
                haversine_m(
                    float(first["latitude"]),
                    float(first["longitude"]),
                    float(second["latitude"]),
                    float(second["longitude"]),
                ),
            )
    return maximum


def parse_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None
