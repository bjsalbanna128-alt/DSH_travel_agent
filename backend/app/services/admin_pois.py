"""Read-only binding candidates from the travel project's POI sources."""

import logging

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.schemas.admin_resources import PoiKind, PoiReference, PoiSearchResponse
from app.services import amap
from app.services.chroma_store import get_chroma_store

logger = logging.getLogger(__name__)


def _lookup_seed(city: str, keyword: str, kind: PoiKind) -> list[dict]:
    return get_chroma_store().find_poi_names(city, keyword, kind)


async def find_binding_candidates(city: str, keyword: str, kind: PoiKind) -> PoiSearchResponse:
    seeds = []
    source_failed = False
    if kind != "service_point":
        try:
            seeds = await run_in_threadpool(_lookup_seed, city, keyword, kind)
        except Exception as error:
            source_failed = True
            logger.warning("Local POI lookup failed: %s", type(error).__name__)

    result = await amap.search_poi(keyword, city, poi_type=kind, city_only=True)
    source_failed = source_failed or result.reason is not None
    candidates = {}
    for source, rows in (("chroma", seeds), ("amap", result.items)):
        for row in rows:
            try:
                candidate = PoiReference(
                    source=source, id=row.get("id"), name=row.get("name"),
                    city=row.get("city") or city, type=kind,
                )
            except ValidationError:
                continue
            candidates[(candidate.source, candidate.id)] = candidate

    if source_failed and not candidates:
        raise HTTPException(503, "POI 查询暂时失败，请重试。已有绑定仍可使用。")
    return PoiSearchResponse(
        items=list(candidates.values()),
        warning="部分 POI 来源暂时无法查询，可重试。" if source_failed else None,
    )
