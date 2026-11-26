"""Content layer: import, inventory, vector sync, sellability and sorting."""

import asyncio
import os
from datetime import date, timedelta
from secrets import token_hex

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
from app.services.sellability import annotate_offers, sort_candidates

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
