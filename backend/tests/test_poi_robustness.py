"""Regression coverage for Amap responses and hybrid POI diagnostics."""

import logging
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.services import amap, embeddings, poi_service
from app.services.amap import PoiSearchResult


@pytest.fixture
def amap_backend(monkeypatch):
    monkeypatch.setattr(amap.settings, "amap_api_key", "test-key")
    cache = SimpleNamespace(cache_get_json=AsyncMock(return_value=None), cache_set_json=AsyncMock())
    monkeypatch.setitem(sys.modules, "app.services.redis_cache", cache)
    handler = Mock()
    make_client = httpx.AsyncClient
    monkeypatch.setattr(
        amap.httpx, "AsyncClient",
        lambda **kwargs: make_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return handler, cache


def _poi(name, **fields):
    return {"id": name, "name": name, "location": "104.061,30.671", **fields}


@pytest.mark.asyncio
@pytest.mark.parametrize(("poi_type", "price_field"), [
    ("attraction", "ticket_price_cny"),
    ("hotel", "price_per_night_cny"),
    ("restaurant", "avg_price_per_person_cny"),
])
async def test_biz_ext_list_and_null_keep_poi(amap_backend, poi_type, price_field):
    handler, cache = amap_backend
    handler.return_value = httpx.Response(200, json={"status": "1", "pois": [
        _poi("列表扩展", biz_ext=[], address=[], tel=[]),
        _poi("空扩展", biz_ext=None),
        _poi("扩展完整", biz_ext={"rating": "4.8", "cost": "26.5", "opentime": "09:00-18:00"}),
    ]})

    result = await amap.search_poi("候选地点", "成都", poi_type=poi_type)

    assert result.reason is None
    assert result.skipped == 0
    assert [poi["name"] for poi in result.items] == ["列表扩展", "空扩展", "扩展完整"]
    assert [poi["rating"] for poi in result.items] == [4.0, 4.0, 4.8]
    assert [poi[price_field] for poi in result.items] == [0.0, 0.0, 26.5]
    assert result.items[0]["biz_ext"] == result.items[1]["biz_ext"] == {}
    if poi_type == "attraction":
        assert result.items[2]["opening_hours"] == "09:00-18:00"
    cache.cache_set_json.assert_awaited_once_with(
        f"amap:成都:{poi_type}:候选地点:15:1", result.items, ttl=86400
    )


@pytest.mark.asyncio
async def test_bad_poi_fields_do_not_drop_batch(amap_backend):
    handler, cache = amap_backend
    handler.return_value = httpx.Response(200, json={"status": "1", "pois": [
        _poi("前一条"),
        _poi("非法坐标格式", location=[]),
        _poi("非法坐标范围", location="104.061,999"),
        _poi("非法评分", biz_ext={"rating": "nan"}),
        _poi("非法照片格式", photos=[42]),
        None,
        _poi("后一条", biz_ext=None),
    ]})

    result = await amap.search_poi("景点", "成都")

    assert result.reason is None
    assert result.skipped == 5
    assert [poi["name"] for poi in result.items] == ["前一条", "后一条"]
    assert result.items[0]["location"] == {"lng": 104.061, "lat": 30.671}
    assert cache.cache_set_json.await_args.args[1] == result.items


@pytest.mark.asyncio
async def test_offset_capped_for_long_trips(monkeypatch, caplog):
    search = AsyncMock(return_value=PoiSearchResult(items=[{"name": "宽窄巷子"}]))
    monkeypatch.setattr(poi_service, "search_poi", search)
    monkeypatch.setattr(poi_service, "get_chroma_store", lambda: SimpleNamespace(collection_count=lambda _: 0))

    with caplog.at_level(logging.INFO, logger=poi_service.__name__):
        result = await poi_service.search_attractions_hybrid("成都", days=7)

    search.assert_awaited_once_with(keywords="成都景点", city="成都", poi_type="attraction", offset=25)
    assert result == [{"name": "宽窄巷子"}]
    assert "requested=35 actual=25" in caplog.text
    assert all(entry.levelno < logging.WARNING for entry in caplog.records)


@pytest.mark.parametrize("failure_point", ["load", "predict"])
def test_reranker_disabled_after_first_failure(monkeypatch, failure_point):
    reranker = Mock()
    load = Mock(return_value=reranker)
    if failure_point == "load":
        load.side_effect = OSError("model unavailable")
    else:
        reranker.rerank.side_effect = RuntimeError("prediction failed")
    monkeypatch.setattr(embeddings, "get_reranker", load)
    monkeypatch.setattr(poi_service, "_reranker", None)
    monkeypatch.setattr(poi_service, "_reranker_available", True)
    items = [{"name": "Chroma 第一项"}, {"name": "高德第二项"}, {"name": "高德第三项"}]

    assert poi_service._rerank("成都", items, top_k=2) == items[:2]
    assert poi_service._reranker is None
    assert poi_service._reranker_available is False
    assert poi_service._rerank("成都", items) == items
    load.assert_called_once_with()
    assert reranker.rerank.call_count == (1 if failure_point == "predict" else 0)


@pytest.mark.asyncio
async def test_failure_reason_returned_to_caller(amap_backend, monkeypatch):
    handler, cache = amap_backend
    monkeypatch.setattr(amap.settings, "amap_api_key", "")
    missing_key = await amap.search_poi("景点", "成都")
    handler.assert_not_called()

    monkeypatch.setattr(amap.settings, "amap_api_key", "test-key")
    handler.return_value = httpx.Response(200, json={"status": "0", "infocode": "10001"})
    rejected = await amap.search_poi("景点", "成都")

    handler.side_effect = httpx.ReadTimeout("test timeout")
    timeout = await amap.search_poi("景点", "成都")
    assert [result.reason for result in (missing_key, rejected, timeout)] == [
        "missing_api_key", "api_error", "request_or_parse_error",
    ]
    assert all(result.items == [] and result.skipped == 0 for result in (missing_key, rejected, timeout))
    cache.cache_set_json.assert_not_awaited()

    handler.side_effect = None
    handler.return_value = httpx.Response(200, json={"status": "1", "pois": []})
    empty = await amap.search_poi("景点", "成都")
    assert empty == PoiSearchResult()
    cache.cache_set_json.assert_awaited_once_with("amap:成都:attraction:景点:15:1", [], ttl=86400)


@pytest.mark.asyncio
@pytest.mark.parametrize(("payload", "skipped"), [
    ({"status": "1", "pois": {}}, 0),
    ({"status": "1", "pois": [None, {"location": "unknown"}]}, 2),
])
async def test_invalid_batch_is_distinct_from_no_data(amap_backend, payload, skipped):
    handler, cache = amap_backend
    handler.return_value = httpx.Response(200, json=payload)
    result = await amap.search_poi("景点", "成都")
    assert result == PoiSearchResult(reason="request_or_parse_error", skipped=skipped)
    cache.cache_set_json.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("items", [[], [{"name": "缓存景点"}]])
async def test_cache_restores_success_result(amap_backend, items):
    handler, cache = amap_backend
    cache.cache_get_json.return_value = items
    result = await amap.search_poi("景点", "成都")
    assert result == PoiSearchResult(items=items)
    handler.assert_not_called()
    cache.cache_set_json.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("search", "poi_type", "keyword"), [
    (poi_service.search_attractions_hybrid, "attraction", "景点"),
    (poi_service.search_hotels_hybrid, "hotel", "酒店"),
    (poi_service.search_restaurants_hybrid, "restaurant", "美食"),
])
async def test_hybrid_consumers_log_reason_and_skipped(monkeypatch, caplog, search, poi_type, keyword):
    item = {"name": "知识库候选"}
    store = SimpleNamespace(
        collection_count=lambda _: 1,
        search_attractions=lambda *_, **__: [item],
        search_hotels=lambda *_, **__: [item],
        search_restaurants=lambda *_, **__: [item],
    )
    monkeypatch.setattr(poi_service, "get_chroma_store", lambda: store)
    monkeypatch.setattr(
        poi_service, "search_poi",
        AsyncMock(return_value=PoiSearchResult(reason="request_or_parse_error", skipped=2)),
    )

    with caplog.at_level(logging.INFO, logger=poi_service.__name__):
        assert await search("成都") == [item]

    context = f"city=成都 keywords=成都{keyword} poi_type={poi_type}"
    assert any(
        entry.levelno == logging.WARNING and f"{context} reason=request_or_parse_error" in entry.message
        for entry in caplog.records
    )
    assert any(
        entry.levelno == logging.INFO and f"{context} skipped=2" in entry.message
        for entry in caplog.records
    )
