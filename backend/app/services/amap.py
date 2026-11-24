"""Amap (高德) POI Search API wrapper."""

import logging
from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Literal

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

AMAP_SEARCH_URL = "https://restapi.amap.com/v3/place/text"
AMAP_MAX_OFFSET = 25

PoiFailure = Literal["missing_api_key", "api_error", "request_or_parse_error"]


@dataclass
class PoiSearchResult:
    items: list[dict[str, Any]] = field(default_factory=list)
    reason: PoiFailure | None = None
    skipped: int = 0

# Amap POI type codes
POI_TYPES = {
    "attraction": "风景名胜|国家级景点|公园|博物馆|展览馆|纪念馆|游乐园|动物园|植物园|水族馆",
    "hotel": "星级酒店|快捷酒店|公寓式酒店|度假村|民宿",
    "restaurant": "中餐厅|火锅|特色/地方风味|海鲜|自助餐|西餐厅|日韩菜|小吃快餐",
}

PRICE_FIELDS = {
    "attraction": "ticket_price_cny",
    "hotel": "price_per_night_cny",
    "restaurant": "avg_price_per_person_cny",
}


async def search_poi(
    keywords: str,
    city: str,
    poi_type: str = "attraction",
    offset: int = 15,
    page: int = 1,
) -> PoiSearchResult:
    """Search Amap POI and return normalized results (cached 24h)."""
    api_key = settings.amap_api_key
    if not api_key:
        return PoiSearchResult(reason="missing_api_key")

    # Try Redis cache first (24h TTL since POI data changes slowly)
    cache_key = f"amap:{city}:{poi_type}:{keywords}:{offset}:{page}"
    try:
        from app.services.redis_cache import cache_get_json

        cached = await cache_get_json(cache_key)
        if isinstance(cached, list) and all(
            isinstance(item, dict) and isinstance(item.get("name", ""), str) for item in cached
        ):
            logger.info(f"Amap cache hit: '{keywords}' in '{city}' ({poi_type}) → {len(cached)} results")
            return PoiSearchResult(items=cached)
    except Exception:
        pass  # Redis optional, continue without cache

    types = POI_TYPES.get(poi_type, "")
    params: dict[str, Any] = {
        "key": api_key,
        "keywords": keywords or city,
        "city": city,
        "offset": offset,
        "page": page,
        "extensions": "all",
    }
    if types:
        params["types"] = types

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(AMAP_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, dict) or "status" not in data:
            raise ValueError("Missing Amap status")
        if data["status"] != "1":
            code = str(data.get("infocode", ""))
            logger.info(
                "Amap rejected POI request: infocode=%s", code if code.isdecimal() else "unknown"
            )
            return PoiSearchResult(reason="api_error")

        pois = data.get("pois")
        if not isinstance(pois, list):
            raise ValueError("Expected an Amap POI list")
    except Exception as e:
        # HTTP exceptions can contain the request URL, including its API key.
        logger.info("Amap POI request or response failed: %s", type(e).__name__)
        return PoiSearchResult(reason="request_or_parse_error")

    results = []
    for poi in pois:
        try:
            results.append(_parse_poi(poi, poi_type))
        except (ValueError, TypeError, OverflowError):
            continue

    skipped = len(pois) - len(results)
    if skipped and not results:
        return PoiSearchResult(reason="request_or_parse_error", skipped=skipped)

    logger.info("Amap search: '%s' in '%s' (%s) → %s results", keywords, city, poi_type, len(results))
    try:
        from app.services.redis_cache import cache_set_json

        await cache_set_json(cache_key, results, ttl=86400)
    except Exception:
        pass  # Redis optional
    return PoiSearchResult(items=results, skipped=skipped)


def _parse_poi(poi: Any, poi_type: str) -> dict[str, Any]:
    if not isinstance(poi, dict):
        raise ValueError("Expected a POI object")
    lng, lat = (float(part) for part in _optional_text(poi.get("location")).split(","))
    if not -180 <= lng <= 180 or not -90 <= lat <= 90:
        raise ValueError("Invalid POI coordinates")

    raw_extension = poi.get("biz_ext")
    extension = raw_extension if isinstance(raw_extension, dict) else {}
    rating = float(extension.get("rating") or 0) or 4.0
    if not isfinite(rating):
        raise ValueError("Invalid POI rating")

    photos = poi.get("photos") or []
    if not isinstance(photos, list):
        raise ValueError("Expected a photo list")
    urls = []
    for photo in photos:
        if not isinstance(photo, dict):
            raise ValueError("Expected a photo object")
        url = _optional_text(photo.get("url"))
        if url:
            urls.append(url)

    item = {
        "id": _optional_text(poi.get("id")),
        "name": _optional_text(poi.get("name")),
        "address": _optional_text(poi.get("address")),
        "location": {"lat": lat, "lng": lng},
        "rating": rating,
        "category": _optional_text(poi.get("type")).split(";")[0],
        "telephone": _optional_text(poi.get("tel")),
        "photos": urls[:3],
        "distance": int(poi.get("distance") or 0),
        "biz_ext": extension,
    }
    price_field = PRICE_FIELDS.get(poi_type)
    if price_field:
        item[price_field] = _parse_price(extension.get("cost"))
    if poi_type == "attraction":
        item["opening_hours"] = _optional_text(extension.get("opentime"))
    return item


def _optional_text(value: Any) -> str:
    if value is None or value == []:
        return ""
    if not isinstance(value, str):
        raise ValueError("Expected a text field")
    return value


def _parse_price(raw: Any) -> float:
    """Return zero for missing or unusable prices."""
    try:
        price = float(raw or 0)
    except (ValueError, TypeError, OverflowError):
        return 0.0
    return price if isfinite(price) and price >= 0 else 0.0
