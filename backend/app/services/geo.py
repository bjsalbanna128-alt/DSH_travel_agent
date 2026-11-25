"""Shared geographic helpers for route and transport planning."""

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(a: dict, b: dict) -> float:
    """Great-circle distance in km between two items exposing ``location.lat/lng``."""
    la1 = a.get("location", {}).get("lat", 0)
    lo1 = a.get("location", {}).get("lng", 0)
    la2 = b.get("location", {}).get("lat", 0)
    lo2 = b.get("location", {}).get("lng", 0)
    dlat = math.radians(la2 - la1)
    dlon = math.radians(lo2 - lo1)
    h = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(la1)) * math.cos(math.radians(la2))
         * math.sin(dlon / 2) ** 2)
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))
