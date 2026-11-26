"""Stock counters: availability reasons, reservation lifecycle and migration."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from secrets import token_hex
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api import deps, routes
from app.config import settings
from app.db import database
from app.db import database as database_module
from app.db.models import User
from app.db.order_models import Order
from app.db.resource_models import OfferAllocation, PriceOffer, Product, Supplier
from app.main import app
from app.schemas.admin_resources import OfferPatch
from app.services import admin_resources, stock
from app.services.admin_resources import offer_day

DAY = date(2026, 12, 1)
NEXT = date(2026, 12, 2)


async def seed_offer(sessions, *, total=None, status="available", product_status="on_shelf",
                     supplier_status="active", day=DAY):
    async with sessions.begin() as db:
        supplier = Supplier(
            id=f"s-{uuid4()}", name="库存供应商", settlement_name="库存供应商",
            kind="hotel", status=supplier_status,
        )
        db.add(supplier)
        await db.flush()
        product = Product(
            id=f"p-{uuid4()}", supplier_id=supplier.id, name="标准间", type="hotel_room", city="北京",
            attributes={"room_name": "标准大床房", "occupancy": 2, "breakfast": "不含早"},
            status=product_status,
        )
        db.add(product)
        await db.flush()
        offer = PriceOffer(
            product_id=product.id, service_date=day, cost_fen=7000, sale_fen=10000,
            status=status, total_quantity=total,
        )
        db.add(offer)
        return product.id


async def load_offer(sessions, product_id, day=DAY):
    async with sessions() as db:
        return await db.get(PriceOffer, (product_id, day))


async def check_unverified_stock_is_not_sellable(sessions, client):
    product_id = await seed_offer(sessions, total=None)
    offer = await load_offer(sessions, product_id)
    entry = offer_day("on_shelf", "active", DAY, offer)
    assert entry.can_sell is False
    assert "unverified_stock" in entry.reasons
    assert entry.quote.total_quantity is None
    assert entry.quote.remaining is None and entry.quote.stock_verified is False


async def check_verified_stock_is_sellable(sessions, client):
    product_id = await seed_offer(sessions, total=2)
    offer = await load_offer(sessions, product_id)
    entry = offer_day("on_shelf", "active", DAY, offer)
    assert entry.can_sell is True and entry.reasons == []
    assert entry.quote.remaining == 2 and entry.quote.stock_verified is True


async def check_sold_out_after_reservation(sessions, client):
    product_id = await seed_offer(sessions, total=1)
    async with sessions.begin() as db:
        await stock.reserve(db, "order-a", [(product_id, DAY, 1)])
    offer = await load_offer(sessions, product_id)
    entry = offer_day("on_shelf", "active", DAY, offer)
    assert entry.can_sell is False and entry.reasons == ["sold_out"]
    assert entry.quote.remaining == 0


async def check_confirm_moves_reserved_to_confirmed(sessions, client):
    product_id = await seed_offer(sessions, total=3)
    async with sessions.begin() as db:
        await stock.reserve(db, "order-b", [(product_id, DAY, 2)])
    async with sessions.begin() as db:
        assert await stock.confirm(db, "order-b") == 1
    offer = await load_offer(sessions, product_id)
    assert (offer.reserved_quantity, offer.confirmed_quantity, offer.remaining_quantity) == (0, 2, 1)
    async with sessions.begin() as db:
        assert await stock.confirm(db, "order-b") == 0
    offer = await load_offer(sessions, product_id)
    assert offer.confirmed_quantity == 2


async def check_release_only_reserved_rows(sessions, client):
    product_id = await seed_offer(sessions, total=3)
    async with sessions.begin() as db:
        await stock.reserve(db, "order-c", [(product_id, DAY, 1)])
    async with sessions.begin() as db:
        assert await stock.release(db, "order-c") == 1
    offer = await load_offer(sessions, product_id)
    assert offer.reserved_quantity == 0 and offer.confirmed_quantity == 0
    async with sessions.begin() as db:
        assert await stock.release(db, "order-c") == 0
    async with sessions() as db:
        rows = (await db.scalars(select(OfferAllocation).where(
            OfferAllocation.order_id == "order-c"))).all()
    assert [row.state for row in rows] == ["released"]


async def check_expired_reservation_is_reclaimed(sessions, client):
    product_id = await seed_offer(sessions, total=1)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with sessions.begin() as db:
        db.add(Order(id="order-d", order_no="test-expiry", user_id="fixture",
                     contact_name="测试", contact_phone="000", total_sale_fen=0, total_cost_fen=0, expires_at=past))
        await stock.reserve(db, "order-d", [(product_id, DAY, 1)], now=past - timedelta(minutes=20))
    async with sessions.begin() as db:
        assert await stock.expire_due(db) == 1
    offer = await load_offer(sessions, product_id)
    assert offer.reserved_quantity == 0
    async with sessions.begin() as db:
        allocations = await stock.reserve(db, "order-e", [(product_id, DAY, 1)])
    assert len(allocations) == 1


async def check_oversell_is_rejected(sessions, client):
    product_id = await seed_offer(sessions, total=1)
    async with sessions.begin() as db:
        await stock.reserve(db, "order-f", [(product_id, DAY, 1)])
    try:
        async with sessions.begin() as db:
            await stock.reserve(db, "order-g", [(product_id, DAY, 1)])
    except stock.StockUnavailable as error:
        assert error.conflicts[0]["reason"] == "sold_out"
    else:
        raise AssertionError("超卖未被拒绝")
    offer = await load_offer(sessions, product_id)
    assert offer.reserved_quantity == 1


async def check_duplicate_entries_are_merged(sessions, client):
    product_id = await seed_offer(sessions, total=5)
    async with sessions.begin() as db:
        allocations = await stock.reserve(db, "order-h", [(product_id, DAY, 1), (product_id, DAY, 2)])
    assert len(allocations) == 1 and allocations[0].quantity == 3
    offer = await load_offer(sessions, product_id)
    assert offer.reserved_quantity == 3


async def check_total_cannot_drop_below_committed(sessions, client):
    product_id = await seed_offer(sessions, total=2)
    async with sessions.begin() as db:
        await stock.reserve(db, "order-i", [(product_id, DAY, 2)])
    async with sessions.begin() as db:
        product = await db.get(Product, product_id)
        try:
            await admin_resources.update_offer(db, product, DAY, OfferPatch(total_quantity=1))
        except HTTPException as error:
            assert error.status_code == 409
            assert error.detail["committed"] == 2
        else:
            raise AssertionError("投放数量被降到占用之下却没有报错")
    async with sessions.begin() as db:
        product = await db.get(Product, product_id)
        result = await admin_resources.update_offer(db, product, DAY, OfferPatch(total_quantity=5))
    assert result.quote.total_quantity == 5


async def check_legacy_database_is_upgraded(sessions, client):
    legacy = database.create_db_engine(
        f"sqlite+aiosqlite:///{database_module.DB_PATH.parent / f'legacy-{token_hex(6)}.db'}",
        poolclass=NullPool,
    )
    try:
        async with legacy.begin() as conn:
            await conn.exec_driver_sql(
                "CREATE TABLE suppliers (id VARCHAR(36) PRIMARY KEY, name VARCHAR(160), "
                "settlement_name VARCHAR(160), contact_name VARCHAR(100), contact_info VARCHAR(160), "
                "notes TEXT, status VARCHAR(16), contract_attachment_ref VARCHAR(255), "
                "settlement_workflow_ref VARCHAR(255), created_at DATETIME, updated_at DATETIME)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE products (id VARCHAR(36) PRIMARY KEY, supplier_id VARCHAR(36), "
                "name VARCHAR(160), type VARCHAR(24), city VARCHAR(100), attributes JSON, poi JSON, "
                "status VARCHAR(16), created_at DATETIME, updated_at DATETIME)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE price_offers (product_id VARCHAR(36), service_date DATE, "
                "cost_fen INTEGER, sale_fen INTEGER, status VARCHAR(16), "
                "PRIMARY KEY (product_id, service_date), "
                "FOREIGN KEY (product_id) REFERENCES products (id))"
            )
            await conn.exec_driver_sql(
                "INSERT INTO suppliers (id, name, settlement_name, status) "
                "VALUES ('old-s', '旧供应商', '旧供应商', 'active')"
            )
            await conn.exec_driver_sql(
                "INSERT INTO products (id, supplier_id, name, type, city, attributes, status) "
                "VALUES ('old-p', 'old-s', '旧房型', 'hotel_room', '北京', '{}', 'on_shelf')"
            )
            await conn.exec_driver_sql(
                "INSERT INTO price_offers VALUES ('old-p', '2026-12-01', 7000, 10000, 'available')"
            )

        original = database_module.engine
        database_module.engine = legacy
        try:
            await database.init_db()
            await database.init_db()
        finally:
            database_module.engine = original

        async with legacy.begin() as conn:
            supplier_columns = {column["name"] for column in
                                await conn.run_sync(lambda sync: sa_inspect(sync).get_columns("suppliers"))}
            offer_columns = {column["name"] for column in
                             await conn.run_sync(lambda sync: sa_inspect(sync).get_columns("price_offers"))}
            row = (await conn.exec_driver_sql(
                "SELECT cost_fen, sale_fen, status, total_quantity, reserved_quantity, confirmed_quantity "
                "FROM price_offers"
            )).one()
        assert "kind" in supplier_columns
        assert {"total_quantity", "reserved_quantity", "confirmed_quantity"} <= offer_columns
        assert row == (7000, 10000, "available", None, 0, 0)
    finally:
        await legacy.dispose()


SCENARIOS = [
    check_unverified_stock_is_not_sellable,
    check_verified_stock_is_sellable,
    check_sold_out_after_reservation,
    check_confirm_moves_reserved_to_confirmed,
    check_release_only_reserved_rows,
    check_expired_reservation_is_reclaimed,
    check_oversell_is_rejected,
    check_duplicate_entries_are_merged,
    check_total_cannot_drop_below_committed,
    check_legacy_database_is_upgraded,
]


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = database.create_db_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'stock.db'}", poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "stock.db")
    for module in (database, deps, routes):
        monkeypatch.setattr(module, "async_session", factory)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
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
def test_stock_lifecycle(api, sessions, scenario):
    asyncio.run(scenario(sessions, api))
