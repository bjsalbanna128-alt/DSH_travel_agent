import json
from types import SimpleNamespace

import chromadb
import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.db.models import Trip, TripVersion
from app.db.trip_version_migration import ensure_trip_version_index
from app.graph.nodes import clarify, compiler
from app.graph.nodes.agents import _estimate_travel
from app.services.chroma_store import ChromaStore
from app.services.trip_store import (
    TripRevisionConflict, get_trip, get_trip_versions, rollback_trip, save_trip, update_trip,
)


def test_chroma_combines_metadata_filters(tmp_path):
    store = object.__new__(ChromaStore)
    vector = [1.0, 0.0, 0.0]
    store._embed = SimpleNamespace(embed_query=lambda _: vector)
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    store._client = client

    def seed(name, metadata):
        collection = client.create_collection(name)
        collection.add(
            ids=["matching", "different-city", "different-filter"],
            embeddings=[vector] * 3,
            metadatas=[
                {"city": "成都", **metadata[0]},
                {"city": "重庆", **metadata[0]},
                {"city": "成都", **metadata[1]},
            ],
            documents=["甲", "乙", "丙"],
        )
    seed("hotels", [{"price_per_night": 400}, {"price_per_night": 900}])
    seed("attractions", [{"category": "cultural"}, {"category": "natural"}])
    seed("restaurants", [{"cuisine": "川菜"}, {"cuisine": "粤菜"}])

    assert [h["id"] for h in store.search_hotels("市区住宿", "成都", 500)] == ["matching"]
    assert {h["id"] for h in store.search_hotels("住宿", city="成都")} == {"matching", "different-filter"}
    assert len(store.search_hotels("住宿")) == 3
    assert [a["id"] for a in store.search_attractions("景点", "成都", "cultural")] == ["matching"]
    assert [r["id"] for r in store.search_restaurants("美食", "成都", "川菜")] == ["matching"]


@pytest.mark.parametrize(("km", "mode", "minutes"), [
    (0, "walking", 0), (1.5, "walking", 19), (2, "metro", 19), (15, "taxi", 22),
])
def test_travel_time_units(km, mode, minutes):
    assert _estimate_travel(km, "moderate") == (mode, minutes)


@pytest.mark.asyncio
async def test_transport_day_mapping_budget_and_first_version(monkeypatch):
    async def reply(self, **kwargs):
        prompt = json.loads(kwargs["user_prompt"])
        assert prompt["transport_by_day"]["2"][0]["from_location"] == "成都东站"
        return json.dumps({
            "title": "成都三天",
            "total_budget_estimate_cny": 5,
            "day_plans": [
                {"day": "1", "attractions": [{"name": "景点", "ticket_price_cny": 20}],
                 "hotel": {"name": "旅馆", "price_per_night_cny": 100},
                 "transport": [{"type": "fake", "price_cny": 999}]},
                {"day": 3},
            ],
        })

    monkeypatch.setattr(compiler.DeepSeekProvider, "chat", reply)
    result = await compiler.itinerary_compiler_node({
        "travel_request": {
            "destination": "成都", "days": 3, "travelers": {"adults": 2},
            "budget": {"total_cny": 250},
        },
        "transport": {
            "intercity": [
                {"type": "train", "from_location": "北京", "to_location": "成都", "price_cny": 100},
                {"type": "train", "from_location": "成都", "to_location": "北京", "price_cny": 110},
            ],
            "intraday": [
                [{"type": "metro", "price_cny": 2}],
                [{"type": "bus", "from_location": "成都东站", "price_cny": 3}],
            ],
        },
    })
    itinerary = result["itinerary"]
    assert itinerary["version"] == 1
    assert [day["day"] for day in itinerary["day_plans"]] == [1, 2, 3]
    assert [[leg["type"] for leg in day["transport"]] for day in itinerary["day_plans"]] == [
        ["train", "metro"], ["bus"], ["train"],
    ]
    assert itinerary["total_budget_estimate_cny"] == 570
    check = await compiler.constraint_validator_node({
        "itinerary": itinerary, "travel_request": {"budget": {"total_cny": 250}},
    })
    assert any("超出预算" in warning for warning in check["constraint_violations"])


@pytest.mark.asyncio
async def test_clarification_keeps_partial_destination_until_days_are_known(monkeypatch):
    responses = iter([
        {"action": "ask", "travel_request": {"destination": "成都"}},
        {"action": "ready", "travel_request": {}},
        {"action": "ask", "travel_request": {"days": "3"}},
    ])

    async def reply(self, **kwargs):
        if "3天" in kwargs["user_prompt"]:
            assert "成都" in kwargs["system_prompt"]
            assert "你计划玩几天？" in kwargs["system_prompt"]
        return json.dumps(next(responses))

    monkeypatch.setattr(clarify.DeepSeekProvider, "chat", reply)
    first = await clarify.clarify_node("去成都")
    history = [{"role": "user", "content": "去成都"}, {"role": "assistant", "content": first["message"]}]
    incomplete = await clarify.clarify_node("还没想好", history, first["travel_request"])
    assert incomplete["action"] == "ask"
    assert incomplete["missing_fields"] == ["days"]
    ready = await clarify.clarify_node("3天", history, incomplete["travel_request"])
    assert ready["action"] == "ready"
    assert ready["travel_request"] == {"destination": "成都", "days": 3}


def test_version_index_migration_preserves_legacy_snapshots():
    engine = create_engine("sqlite://")
    table = TripVersion.__table__
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
        next(iter(table.indexes)).drop(conn)
        conn.execute(Trip.__table__.insert(), {
            "id": "trip", "thread_id": "thread", "version": 2,
            "itinerary": {"title": "当前行程", "version": 2},
        })
        conn.execute(table.insert(), [
            {"id": "a", "trip_id": "trip", "version": 2, "itinerary": {"title": "当前行程", "version": 2}},
            {"id": "b", "trip_id": "trip", "version": 2, "itinerary": {"title": "旧草稿", "version": 2}},
            {"id": "c", "trip_id": "trip", "version": 5, "itinerary": {"title": "其他版本", "version": 5}},
        ])
        ensure_trip_version_index(conn)
        ensure_trip_version_index(conn)
        assert any(index["unique"] for index in inspect(conn).get_indexes(table.name))
        rows = conn.execute(select(table).order_by(table.c.id)).mappings().all()
        assert [(row["version"], row["itinerary"]["title"]) for row in rows] == [
            (2, "当前行程"), (6, "旧草稿"), (5, "其他版本"),
        ]
        assert rows[1]["itinerary"]["version"] == 6
        with pytest.raises(IntegrityError):
            conn.execute(table.insert(), {"id": "d", "trip_id": "trip", "version": 2})
    engine.dispose()


@pytest.mark.asyncio
async def test_saved_versions_increase_after_rollback_and_stale_write(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'versions.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions.begin() as db:
            first = await save_trip(db, "thread", {"title": "初始", "version": 7}, "alice")
            assert first.version == first.itinerary["version"] == 1
        async with sessions.begin() as db:
            second = await save_trip(db, "thread", {"title": "第二版", "version": 1}, "alice")
            assert second.version == second.itinerary["version"] == 2

        async with sessions() as stale:
            old = await stale.get(Trip, first.id)
            async with sessions.begin() as db:
                restored = await rollback_trip(db, first.id, 1, user_id="alice")
                assert restored["version"] == restored["itinerary"]["version"] == 3
                assert restored["title"] == "初始"
            with pytest.raises(TripRevisionConflict):
                await update_trip(stale, old.id, {"title": "过期写入"}, user_id="alice")

        async with sessions.begin() as db:
            updated = await update_trip(db, first.id, {"title": "手动编辑"}, user_id="alice")
            assert updated["version"] == updated["itinerary"]["version"] == 4
            history = await get_trip_versions(db, first.id, user_id="alice")
            assert [item["version"] for item in history] == [4, 3, 2, 1]
            assert (await get_trip(db, first.id, user_id="alice"))["title"] == "手动编辑"
    finally:
        await engine.dispose()
