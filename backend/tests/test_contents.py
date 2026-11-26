"""Content layer: import, inventory, vector sync, sellability and sorting."""

import asyncio
import os
from datetime import date, timedelta
from secrets import token_hex
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api import deps, routes
from app.config import settings
from app.db import database
from app.db.content_models import PlaceContent, PlaceContentProduct
from app.db.resource_models import PriceOffer, Product, Supplier
from app.main import app
from app.services import chroma_store, contents
from app.services.sellability import annotate_offers, resolve_content_candidates, sort_candidates
from app.schemas.contents import BindProducts

DAY = date.today() + timedelta(days=3)

import scripts.import_seed_contents as importer  # noqa: E402
import scripts.seed_beijing_inventory as beijing  # noqa: E402
import scripts.sync_content_vectors as syncer  # noqa: E402


async def seed_everything(sessions):
    await importer.main(["北京"])
    await beijing.main()
    await syncer.main(rebuild=True)


async def check_beijing_import(sessions, client):
    await seed_everything(sessions)
    async with sessions() as db:
        attractions = await db.scalar(select(func.count()).select_from(PlaceContent).where(
            PlaceContent.kind == "attraction"))
        hotels = await db.scalar(select(func.count()).select_from(PlaceContent).where(
            PlaceContent.kind == "hotel"))
        products = await db.scalar(select(func.count()).select_from(Product))
        offers = await db.scalar(select(func.count()).select_from(PriceOffer))
        bindings = await db.scalar(select(func.count()).select_from(PlaceContentProduct))
    assert (attractions, hotels) == (10, 18)
    assert products == 24 and offers == 24 * 90 and bindings == 24


async def check_import_is_idempotent(sessions, client):
    await seed_everything(sessions)
    await importer.main(["北京"])
    await beijing.main()
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(PlaceContent)) == 28
        assert await db.scalar(select(func.count()).select_from(Product)) == 24
        assert await db.scalar(select(func.count()).select_from(PriceOffer)) == 24 * 90


async def check_only_published_content_is_indexed(sessions, client):
    await seed_everything(sessions)
    store = chroma_store.get_chroma_store()
    assert store.collection_count("contents_attractions") == 10
    assert store.collection_count("contents_hotels") == 18
    async with sessions.begin() as db:
        row = await db.scalar(select(PlaceContent).where(PlaceContent.name == "故宫博物院"))
        row.status = "draft"
    await syncer.main(rebuild=False)
    assert store.collection_count("contents_attractions") == 9


async def check_sellable_annotation(sessions, client):
    await seed_everything(sessions)
    async with sessions() as db:
        rows = await contents.sellable_products(db, [], DAY)
        assert rows == {}
        paid = await db.scalar(select(PlaceContent).where(PlaceContent.name == "故宫博物院"))
        free = await db.scalar(select(PlaceContent).where(PlaceContent.name == "南锣鼓巷"))
        paid_ids = [paid.id]
        annotated = await annotate_offers(db, [
            {"content_id": paid.id, "name": paid.name},
            {"content_id": free.id, "name": free.name},
            {"name": "高德来的地点"},
        ], kind="attraction", travel_date=DAY)
        found = await contents.sellable_products(db, paid_ids, DAY)
    assert annotated[0]["offer"]["sellable"] is True
    assert annotated[0]["offer"]["remaining"] == 200
    assert annotated[1]["offer"] is None
    assert annotated[2]["offer"] is None
    assert found[paid.id]["price_fen"] == 6000  # 故宫门票 60 元


async def check_stopped_offer_is_not_sellable(sessions, client):
    await seed_everything(sessions)
    async with sessions.begin() as db:
        content = await db.scalar(select(PlaceContent).where(PlaceContent.name == "故宫博物院"))
        binding = await db.scalar(select(PlaceContentProduct).where(
            PlaceContentProduct.content_id == content.id))
        offer = await db.get(PriceOffer, (binding.product_id, DAY))
        offer.status = "stopped"
    async with sessions() as db:
        found = await contents.sellable_products(db, [content.id], DAY)
    assert found == {}


async def check_sellable_sorts_first(sessions, client):
    items = [
        {"name": "远但可售", "offer": {"sellable": True}, "location": {"lat": 40.0, "lng": 116.5}},
        {"name": "近但不可售", "offer": None, "location": {"lat": 39.9, "lng": 116.4}},
        {"name": "近且可售", "offer": {"sellable": True}, "location": {"lat": 39.91, "lng": 116.41}},
    ]
    ordered = sort_candidates(items, anchor={"location": {"lat": 39.9, "lng": 116.4}})
    assert [item["name"] for item in ordered] == ["近且可售", "远但可售", "近但不可售"]


async def check_admin_api_requires_operator(sessions, client):
    await seed_everything(sessions)
    assert client.get("/api/v1/admin/contents").status_code in (401, 403)


def test_vector_failure_keeps_sql_publication_authoritative(sessions, monkeypatch):
    from fastapi import HTTPException

    async def fail(*args, **kwargs):
        raise OSError("vector temporarily unavailable")

    async def run():
        await importer.main(["北京"])
        await beijing.main()
        async with sessions.begin() as db:
            attraction = await db.scalar(select(PlaceContent).where(PlaceContent.name == "故宫博物院"))
            hotel_product = await db.scalar(select(Product).where(Product.type == "hotel_room").limit(1))
            hint = [{"content_id": attraction.id, "kind": "attraction", "city": "北京"}]
            assert (await annotate_offers(db, hint, kind="attraction", travel_date=DAY))[0]["offer"]
            with pytest.raises(HTTPException) as invalid:
                await contents.bind_products(db, attraction.id, BindProducts(product_ids=[hotel_product.id]), "ops")
            assert invalid.value.status_code == 422
            await contents.unpublish_content(db, attraction.id, "ops")
        monkeypatch.setattr(contents, "sync_vectors", fail)
        async with sessions.begin() as db:
            assert await contents.process_vector_job(db) is None
        async with sessions.begin() as db:
            assert await contents.vector_status(db) == {"pending": True, "failed": True}
            assert (await annotate_offers(db, hint, kind="attraction", travel_date=None))[0]["offer"] is None
            await contents.bind_products(db, attraction.id, BindProducts(product_ids=[]), "ops")
            await contents.delete_content(db, attraction.id)
        async with sessions() as db:
            resolved = await resolve_content_candidates(db, hint, "北京", "attraction", DAY)
            assert attraction.id not in {poi["content_id"] for poi in resolved}

    asyncio.run(run())


def test_distance_without_coordinates_and_next_day_offer(sessions):
    async def run():
        await importer.main(["北京"])
        await beijing.main()
        async with sessions.begin() as db:
            content_id, product_id = (await db.execute(select(
                PlaceContentProduct.content_id, Product.id,
            ).join(Product).where(Product.type == "hotel_room").limit(1))).one()
            first = await db.get(PriceOffer, (product_id, DAY))
            first.total_quantity = 0
            poi = {"content_id": content_id, "kind": "hotel"}
            assert (await annotate_offers(db, [poi], kind="hotel", travel_date=DAY))[0]["offer"] is None
            assert (await annotate_offers(db, [poi], kind="hotel", travel_date=DAY, end_date=DAY + timedelta(days=1)))[0]["offer"]
        near = {"location": {"lat": 39.9, "lng": 116.41}}
        distant = {"location": {"lat": 40, "lng": 116.41}}
        unknown = {"name": "未知"}
        assert sort_candidates([unknown, distant, near], anchor={"lat": 39.9, "lng": 116.4}) == [near, distant, unknown]

    asyncio.run(run())


def test_compiler_dates_take_only_the_confirmed_departure():
    from app.graph.nodes.compiler import _apply_day_dates
    from app.schemas.travel_state import DayPlan

    plans = [DayPlan(day=1, date="2000-01-01"), DayPlan(day=2, date="2000-01-01")]
    _apply_day_dates(plans, "2026-12")
    assert [p.date for p in plans] == ["", ""]
    _apply_day_dates(plans, "2026年12月12日出发")
    assert [p.date for p in plans] == ["2026-12-12", "2026-12-13"]


SCENARIOS = [
    check_beijing_import,
    check_import_is_idempotent,
    check_only_published_content_is_indexed,
    check_sellable_annotation,
    check_stopped_offer_is_not_sellable,
    check_sellable_sorts_first,
    check_admin_api_requires_operator,
]


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = database.create_db_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'contents.db'}", poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", factory)
    for module in (deps, routes):
        monkeypatch.setattr(module, "async_session", factory)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
    monkeypatch.setattr(settings, "chroma_persist_path", str(tmp_path / "chroma"))
    monkeypatch.setattr(chroma_store, "_chroma_store_instance", None)
    monkeypatch.setattr(chroma_store, "get_embedding_provider", lambda: SimpleNamespace(
        embed_query=lambda _text: [1.0, 0.0, 0.0],
    ))
    asyncio.run(database.init_db())
    yield factory
    asyncio.run(engine.dispose())


@pytest.fixture
def api(sessions):
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.__name__.removeprefix("check_"))
def test_content_layer(api, sessions, scenario):
    asyncio.run(scenario(sessions, api))
