"""Amap (高德) POI Search API wrapper."""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

AMAP_SEARCH_URL = "https://restapi.amap.com/v3/place/text"

# Amap POI type codes
POI_TYPES = {
    "attraction": "风景名胜|国家级景点|公园|博物馆|展览馆|纪念馆|游乐园|动物园|植物园|水族馆",
    "hotel": "星级酒店|快捷酒店|公寓式酒店|度假村|民宿",
    "restaurant": "中餐厅|火锅|特色/地方风味|海鲜|自助餐|西餐厅|日韩菜|小吃快餐",
}


async def search_poi(
    keywords: str,
    city: str,
    poi_type: str = "attraction",
    offset: int = 15,
    page: int = 1,
) -> list[dict[str, Any]]:
    """Search Amap POI and return normalized results (cached 24h)."""
    api_key = settings.amap_api_key
    if not api_key:
        logger.warning("Amap API key not configured, returning empty results")
        return []

    # Try Redis cache first (24h TTL since POI data changes slowly)
    cache_key = f"amap:{city}:{poi_type}:{keywords}:{offset}:{page}"
    try:
        from app.services.redis_cache import cache_get_json, cache_set_json
        cached = await cache_get_json(cache_key)
        if cached is not None:
            logger.info(f"Amap cache hit: '{keywords}' in '{city}' ({poi_type}) → {len(cached)} results")
            return cached
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

        if data.get("status") != "1":
            logger.error(f"Amap API error: {data}")
            return []

        pois = data.get("pois", [])
        if not pois:
            logger.info(f"No Amap POI results for '{keywords}' in '{city}' ({poi_type})")

        results = []
        for p in pois:
            # Parse location
            loc = p.get("location", "0,0").split(",")
            lng = float(loc[0]) if len(loc) >= 1 else 0
            lat = float(loc[1]) if len(loc) >= 2 else 0

            # Parse photos
            photos = []
            for ph in (p.get("photos") or []):
                url = ph.get("url", "")
                if url:
                    photos.append(url)

            # Normalize
            item = {
                "id": p.get("id", ""),
                "name": p.get("name", ""),
                "address": p.get("address", ""),
                "location": {"lat": lat, "lng": lng},
                "rating": float(p.get("biz_ext", {}).get("rating", "0") or 0) or 4.0,
                "category": p.get("type", "").split(";")[0] if p.get("type") else "",
                "telephone": p.get("tel", "") or "",
                "photos": photos[:3],
                "distance": int(p.get("distance", 0) or 0),
                "biz_ext": p.get("biz_ext", {}),
            }

            # Type-specific fields
            if poi_type == "attraction":
                item["ticket_price_cny"] = _parse_price(
                    p.get("biz_ext", {}).get("cost", "0") or "0"
                )
                item["opening_hours"] = p.get("biz_ext", {}).get("opentime", "") or ""
            elif poi_type == "hotel":
                item["price_per_night_cny"] = _parse_price(
                    p.get("biz_ext", {}).get("cost", "0") or "0"
                )
                item["rating"] = float(p.get("biz_ext", {}).get("rating", "0") or 0) or 4.0
            elif poi_type == "restaurant":
                item["avg_price_per_person_cny"] = _parse_price(
                    p.get("biz_ext", {}).get("cost", "0") or "0"
                )

            results.append(item)

        logger.info(
            f"Amap search: '{keywords}' in '{city}' ({poi_type}) → {len(results)} results"
        )
        # Cache results for 24 hours
        try:
            await cache_set_json(cache_key, results, ttl=86400)
        except Exception:
            pass
        return results

    except Exception as e:
        logger.error(f"Amap API call failed: {e}")
        return []


def _parse_price(raw: str) -> float:
    """Parse price string to float."""
    try:
        return float(raw) if raw else 0
    except (ValueError, TypeError):
        return 0
