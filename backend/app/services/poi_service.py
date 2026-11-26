"""Hybrid POI search — ChromaDB semantic + Amap API realtime merge + Cross-Encoder re-rank."""

import logging
from difflib import SequenceMatcher
from typing import Any

from app.services.amap import AMAP_MAX_OFFSET, search_poi
from app.services.chroma_store import get_chroma_store

logger = logging.getLogger(__name__)

# Lazy-loaded reranker
_reranker = None
_reranker_available = True


def _get_reranker():
    """Lazy-load the cross-encoder reranker singleton."""
    global _reranker, _reranker_available
    if not _reranker_available:
        return None
    if _reranker is not None:
        return _reranker
    try:
        from app.services.embeddings import get_reranker
        _reranker = get_reranker()
        return _reranker
    except Exception as e:
        logger.warning(f"Reranker unavailable (will skip): {e}")
        _reranker_available = False
        _reranker = None
        return None


def _name_similarity(a: str, b: str) -> float:
    """String similarity ratio for dedup."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _poi_to_text(item: dict) -> str:
    """Convert a POI dict to a searchable text string for the reranker."""
    parts = [item.get("name", "")]
    if item.get("description"):
        parts.append(item["description"])
    if item.get("category"):
        parts.append(f"分类:{item['category']}")
    if item.get("tags"):
        tags = item["tags"]
        if isinstance(tags, list):
            parts.append(" ".join(tags))
    if item.get("suitable_for"):
        sf = item["suitable_for"]
        if isinstance(sf, list):
            parts.append(f"适合:{' '.join(sf)}")
    return " ".join(parts)


def _rerank(query: str, items: list[dict], top_k: int | None = None) -> list[dict]:
    """Re-rank items using cross-encoder. Falls back to original order."""
    global _reranker, _reranker_available
    if len(items) <= 1:
        return items

    reranker = _get_reranker()
    if reranker is None:
        return items[:top_k] if top_k else items

    try:
        documents = [_poi_to_text(item) for item in items]
        ranked = reranker.rerank(query, documents, top_k=top_k)
        return [items[i] for i, _ in ranked]
    except Exception as e:
        logger.warning(f"Rerank failed (falling back to original order): {e}")
        _reranker_available = False
        _reranker = None
        return items[:top_k] if top_k else items


def _merge_and_dedup(
    chroma_results: list[dict],
    amap_results: list[dict],
    prefer_chroma: bool = True,
) -> list[dict]:
    """Merge ChromaDB and Amap results, removing duplicates.

    Dedup rule: same-name similarity > 0.8 → keep ChromaDB version.
    ChromaDB items come first (semantically more relevant).
    """
    merged: list[dict] = []
    seen_names: list[str] = []

    primary = chroma_results if prefer_chroma else amap_results
    secondary = amap_results if prefer_chroma else chroma_results

    for item in primary:
        merged.append(item)
        seen_names.append(item.get("name", ""))

    for item in secondary:
        name = item.get("name", "")
        is_dup = any(_name_similarity(name, seen) > 0.8 for seen in seen_names)
        if not is_dup:
            merged.append(item)
            seen_names.append(name)

    return merged


async def _search_amap_items(
    keywords: str, city: str, poi_type: str, offset: int,
) -> list[dict[str, Any]]:
    result = await search_poi(keywords=keywords, city=city, poi_type=poi_type, offset=offset)
    if result.reason is not None:
        logger.warning(
            "Amap POI search degraded: city=%s keywords=%s poi_type=%s reason=%s",
            city, keywords, poi_type, result.reason,
        )
    if result.skipped:
        logger.info(
            "Amap POI records skipped: city=%s keywords=%s poi_type=%s skipped=%d",
            city, keywords, poi_type, result.skipped,
        )
    return result.items


async def search_attractions_hybrid(
    city: str,
    preferences: list[str] | None = None,
    days: int = 3,
    chroma_only: bool = False,
    *,
    travel_date=None,
    anchor: dict | None = None,
    session=None,
) -> list[dict[str, Any]]:
    """Content layer (our sellable places) + Amap realtime.

    Legacy seed collections are no longer read: a city without content simply
    falls back to Amap.
    """
    prefs = preferences or []
    query = f"{city} {' '.join(prefs)}"
    limit = days * 5  # more candidates for LLM curation

    content_results: list[dict] = []
    try:
        store = get_chroma_store()
        if store.collection_count("contents_attractions") > 0:
            content_results = [
                {**item, "source": "content", "city": item.get("city") or city}
                for item in store.search_contents("attraction", query, city=city, k=min(limit, 20))
                if (item.get("city") or city) == city
            ]
            logger.info(f"Content attractions: {len(content_results)} results")
    except Exception as e:
        logger.warning(f"Content attraction search failed (will use Amap only): {e}")

    if chroma_only:
        return content_results

    amap_offset = min(limit, AMAP_MAX_OFFSET)
    if amap_offset < limit:
        logger.info(
            "Amap attraction offset capped: city=%s requested=%d actual=%d",
            city, limit, amap_offset,
        )
    amap_results = await _search_amap_items(
        keywords=city + "景点",
        city=city,
        poi_type="attraction",
        offset=amap_offset,
    )
    amap_results = [
        {**item, "source": "amap", "city": item.get("city") or city} if item.get("id") else item
        for item in amap_results
    ]

    merged = _merge_and_dedup(content_results, amap_results, prefer_chroma=True)
    merged = _rerank(query, merged, top_k=limit)
    if session is not None:
        from app.services.sellability import annotate_offers, sort_candidates

        merged = await annotate_offers(session, merged, kind="attraction", travel_date=travel_date)
        merged = sort_candidates(merged)
    logger.info(
        f"Hybrid attraction search: {len(content_results)} content + {len(amap_results)} amap "
        f"→ {len(merged)} re-ranked"
    )
    return merged


async def search_hotels_hybrid(
    city: str,
    max_price_per_night: float = 0,
    count: int = 10,
    *,
    travel_date=None,
    anchor: dict | None = None,
    session=None,
) -> list[dict[str, Any]]:
    """Content layer hotels + Amap realtime, sellable first and nearest to anchor."""
    content_results: list[dict] = []
    try:
        store = get_chroma_store()
        if store.collection_count("contents_hotels") > 0:
            content_results = [
                {**item, "source": "content", "city": item.get("city") or city}
                for item in store.search_contents("hotel", city + " 酒店", city=city, k=count)
                if (item.get("city") or city) == city
            ]
    except Exception as e:
        logger.warning(f"Content hotel search failed: {e}")

    amap_results = await _search_amap_items(
        keywords=city + "酒店",
        city=city,
        poi_type="hotel",
        offset=count,
    )

    # Budget filter for Amap results
    if max_price_per_night > 0:
        amap_results = [
            h for h in amap_results
            if h.get("price_per_night_cny", 0) <= max_price_per_night
        ]

    merged = _merge_and_dedup(content_results, amap_results, prefer_chroma=True)
    merged = _rerank(city + " 酒店", merged, top_k=count)
    if session is not None:
        from app.services.sellability import annotate_offers, sort_candidates

        merged = await annotate_offers(session, merged, kind="hotel", travel_date=travel_date)
        if max_price_per_night > 0:
            merged = [
                hotel for hotel in merged
                if not (hotel.get("offer") or {}).get("sellable")
                or hotel["offer"]["price_cny"] <= max_price_per_night
            ]
        merged = sort_candidates(merged, anchor=anchor)
    logger.info(
        f"Hybrid hotel search: {len(content_results)} content + {len(amap_results)} amap "
        f"→ {len(merged)} re-ranked"
    )
    return merged


async def search_restaurants_hybrid(
    city: str,
    preferences: list[str] | None = None,
    count: int = 15,
) -> list[dict[str, Any]]:
    """Hybrid restaurant search."""
    prefs = preferences or []
    query = f"{city} {' '.join(prefs)} 美食"

    chroma_results: list[dict] = []
    try:
        store = get_chroma_store()
        if store.collection_count("restaurants") > 0:
            chroma_results = store.search_restaurants(query, city=city, k=count)
    except Exception as e:
        logger.warning(f"ChromaDB restaurant search failed: {e}")

    amap_results = await _search_amap_items(
        keywords=city + "美食",
        city=city,
        poi_type="restaurant",
        offset=count,
    )

    merged = _merge_and_dedup(chroma_results, amap_results, prefer_chroma=True)
    merged = _rerank(query, merged, top_k=count)
    logger.info(f"Hybrid restaurant search: {len(chroma_results)} chroma + {len(amap_results)} amap → {len(merged)} re-ranked")
    return merged
