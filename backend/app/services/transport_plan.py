"""Transport plan helpers: intraday legs from route results, intercity estimates."""

import logging

from app.config import settings
from app.schemas.travel_state import IntercityEstimate, TransportOption
from app.services.geo import haversine_km

logger = logging.getLogger(__name__)

# Speeds mirror route_node's _estimate_travel so both use one convention.
WALK_SPEED_KMH = 4.8
BUS_SPEED_KMH = 20.0
METRO_SPEED_KMH = 30.0
TAXI_SPEED_KMH = 40.0
BUS_WAIT_MINUTES = 10
METRO_WAIT_MINUTES = 15

# Taxi fares are rounded to the nearest half yuan.
FARE_ROUNDING_CNY = 0.5

# A price band wider than this ratio is treated as an unusable guess.
MAX_PRICE_SPREAD_RATIO = 2.0

INTERCITY_MODES = ("train", "flight")


def travel_minutes(distance_km: float, mode: str) -> int:
    """Rough travel time for one leg, including waiting time where relevant."""
    if distance_km <= 0:
        return 0
    if mode == "walking":
        return round(distance_km / WALK_SPEED_KMH * 60)
    if mode == "bus":
        return int(distance_km / BUS_SPEED_KMH * 60 + BUS_WAIT_MINUTES)
    if mode == "metro":
        return int(distance_km / METRO_SPEED_KMH * 60 + METRO_WAIT_MINUTES)
    if mode == "taxi":
        return int(distance_km / TAXI_SPEED_KMH * 60)
    return 0


def _round_half(value: float) -> float:
    return round(value / FARE_ROUNDING_CNY) * FARE_ROUNDING_CNY


def segment_fare(distance_km: float, mode: str) -> float:
    """Single-person fare for one leg, taken from configuration."""
    if mode == "walking":
        return settings.transport_walk_fare_cny
    if mode == "bus":
        return settings.transport_bus_fare_cny
    if mode == "metro":
        return settings.transport_metro_fare_cny
    if mode == "taxi":
        raw = settings.transport_taxi_base_cny + settings.transport_taxi_per_km_cny * max(distance_km, 0)
        return _round_half(raw)
    return 0.0


def _as_stop(item) -> dict | None:
    """Normalise an attraction/hotel object or dict into {name, location}."""
    if isinstance(item, dict):
        name = str(item.get("name") or "").strip()
        location = item.get("location") or {}
    else:
        name = str(getattr(item, "name", "") or "").strip()
        location = getattr(item, "location", None)
        if hasattr(location, "model_dump"):
            location = location.model_dump()
        location = location or {}
    if not name:
        return None
    return {"name": name, "location": location}


def _build_leg(origin: dict, destination: dict, mode: str) -> TransportOption | None:
    if origin["name"] == destination["name"]:
        return None
    distance_km = haversine_km(origin, destination)
    return TransportOption(
        type=mode,
        from_location=origin["name"],
        to_location=destination["name"],
        duration_minutes=travel_minutes(distance_km, mode),
        price_cny=segment_fare(distance_km, mode),
    )


def build_intraday_transports(attractions, hotel, travel_mode: str = "walking") -> list[TransportOption]:
    """Build one day's legs from the planned attraction order and hotel.

    Order: hotel → first attraction → … → last attraction → hotel. A day without
    hotel only links attractions; a day without attractions has no legs.
    """
    stops = [stop for stop in (_as_stop(item) for item in attractions or []) if stop]
    if not stops:
        return []

    mode = (travel_mode or "walking").strip() or "walking"
    hotel_stop = _as_stop(hotel) if hotel else None

    pairs: list[tuple[dict, dict]] = []
    if hotel_stop:
        pairs.append((hotel_stop, stops[0]))
    pairs.extend(zip(stops, stops[1:]))
    if hotel_stop:
        pairs.append((stops[-1], hotel_stop))

    legs = [leg for leg in (_build_leg(a, b, mode) for a, b in pairs) if leg]
    return legs


def _valid_range(low: float, high: float) -> bool:
    return 0 <= low <= high


def parse_intercity_estimates(raw) -> list[IntercityEstimate]:
    """Validate model-provided intercity estimates, dropping unusable entries."""
    if not isinstance(raw, list):
        return []

    estimates: list[IntercityEstimate] = []
    seen: set[tuple[str, str, str]] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue
        mode = str(item.get("type") or "").strip().lower()
        origin = str(item.get("from_location") or "").strip()
        destination = str(item.get("to_location") or "").strip()
        if mode not in INTERCITY_MODES or not origin or not destination:
            logger.warning("Dropped intercity estimate with unknown mode or city: %s", item)
            continue
        try:
            hours_low = float(item.get("duration_hours_min") or 0)
            hours_high = float(item.get("duration_hours_max") or 0)
            price_low = float(item.get("price_cny_min") or 0)
            price_high = float(item.get("price_cny_max") or 0)
        except (TypeError, ValueError):
            logger.warning("Dropped intercity estimate with non-numeric range: %s", item)
            continue

        if not _valid_range(hours_low, hours_high) or not _valid_range(price_low, price_high):
            logger.warning("Dropped intercity estimate with inverted range: %s", item)
            continue
        if hours_high <= 0 or price_high <= 0:
            logger.warning("Dropped intercity estimate without duration or price: %s", item)
            continue
        if price_low > 0 and price_high > price_low * MAX_PRICE_SPREAD_RATIO:
            logger.warning("Dropped intercity estimate with too wide a price band: %s", item)
            continue

        key = (mode, origin, destination)
        if key in seen:
            continue
        seen.add(key)
        estimates.append(IntercityEstimate(
            type=mode,
            from_location=origin,
            to_location=destination,
            duration_hours_min=hours_low,
            duration_hours_max=hours_high,
            price_cny_min=price_low,
            price_cny_max=price_high,
        ))

    return estimates


def intercity_median_total(estimates: list[IntercityEstimate]) -> float:
    """Return the summed midpoint of every price band."""
    total = sum((item.price_cny_min + item.price_cny_max) / 2 for item in estimates)
    return round(total, 2)
