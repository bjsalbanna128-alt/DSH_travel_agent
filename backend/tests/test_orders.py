"""Order trading: reservation, mock payment, review, cancellation and refunds."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from secrets import token_hex
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api import deps, routes
from app.config import settings
from app.db import database
from app.db.models import User
from app.db.order_models import Order, OrderPayment, OrderRefund
from app.db.resource_models import PriceOffer, Product, Supplier
from app.main import app
from app.services import orders as order_service
from app.services.auth_service import create_access_token

GUEST, OTHER, OPERATOR = "order-guest", "order-other", "order-operator"
DAY = date.today() + timedelta(days=3)
API = "/api/v1/orders"
ADMIN = "/api/v1/admin/orders"


def auth(user: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


async def seed_room(sessions, total=5, sale_fen=50000):
    async with sessions.begin() as db:
        supplier = Supplier(id=str(uuid4()), name="订单供应商", settlement_name="订单供应商", kind="hotel")
        db.add(supplier)
        await db.flush()
        product = Product(
            id=str(uuid4()), supplier_id=supplier.id, name="标准大床房", type="hotel_room", city="北京",
            attributes={"room_name": "标准大床房", "occupancy": 2, "breakfast": "不含早"},
            status="on_shelf",
        )
        db.add(product)
        await db.flush()
        for offset in range(3):
            db.add(PriceOffer(
                product_id=product.id, service_date=DAY + timedelta(days=offset),
                cost_fen=sale_fen - 10000, sale_fen=sale_fen, status="available",
                total_quantity=total, reserved_quantity=0, confirmed_quantity=0,
            ))
        return product.id


async def seed_users(sessions):
    async with sessions.begin() as db:
        db.add_all([
            User(id=GUEST, username=GUEST, email="g@x.com", password_hash="x", role="tourist"),
            User(id=OTHER, username=OTHER, email="o@x.com", password_hash="x", role="tourist"),
            User(id=OPERATOR, username=OPERATOR, email="a@x.com", password_hash="x", role="operator"),
        ])


def body(product_id, quantity=1, nights=1):
    return {
        "contact_name": "张三", "contact_phone": "13800000000",
        "travelers": [{"name": "张三", "document_type": "身份证", "document_number": "110101199001010011"}],
        "selected": [{
            "kind": "hotel", "product_id": product_id,
            "check_in": DAY.isoformat(), "check_out": (DAY + timedelta(days=nights)).isoformat(),
            "quantity": quantity,
        }],
    }


async def create(sessions, client, product_id, **kwargs):
    return client.post(API, json=body(product_id, **kwargs), headers=auth(GUEST))


async def stock_row(sessions, product_id, day=DAY):
    async with sessions() as db:
        return await db.get(PriceOffer, (product_id, day))


async def check_create_reserves_stock(sessions, client):
    await seed_users(sessions)
    product_id = await seed_room(sessions, total=5)
    response = await create(sessions, client, product_id, quantity=2, nights=2)
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "pending_payment" and order["fund_status"] == "unpaid"
    assert order["order_no"].startswith("ZY") and len(order["order_no"]) == 14
    assert order["total_sale_fen"] == 50000 * 2 * 2
    assert len(order["items"]) == 2  # 两晚各一行
    assert order["travelers"][0]["document_mask"] != "110101199001010011"
    offer = await stock_row(sessions, product_id)
    assert offer.reserved_quantity == 2


async def check_duplicate_submit_returns_same_order(sessions, client):
    await seed_users(sessions)
    product_id = await seed_room(sessions)
    headers = {**auth(GUEST), "Idempotency-Key": "same-key"}
    first = client.post(API, json=body(product_id), headers=headers)
    second = client.post(API, json=body(product_id), headers=headers)
    assert first.json()["id"] == second.json()["id"]
    offer = await stock_row(sessions, product_id)
    assert offer.reserved_quantity == 1


async def check_pay_then_review_confirm(sessions, client):
    await seed_users(sessions)
    product_id = await seed_room(sessions)
    order = (await create(sessions, client, product_id)).json()
    paid = client.post(f"{API}/{order['id']}/payments", json={"idempotency_key": "pay-1"},
                       headers=auth(GUEST))
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid_pending_review"
    assert paid.json()["fund_status"] == "paid"

    approved = client.post(f"{ADMIN}/{order['id']}/approve", json={"note": "已核实"},
                           headers=auth(OPERATOR))
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "confirmed"
    offer = await stock_row(sessions, product_id)
    assert (offer.reserved_quantity, offer.confirmed_quantity) == (0, 1)


async def check_payment_is_idempotent(sessions, client):
    await seed_users(sessions)
    product_id = await seed_room(sessions)
    order = (await create(sessions, client, product_id)).json()
    client.post(f"{API}/{order['id']}/payments", json={"idempotency_key": "k1"}, headers=auth(GUEST))
    again = client.post(f"{API}/{order['id']}/payments", json={"idempotency_key": "k1"},
                        headers=auth(GUEST))
    assert again.status_code == 200
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(OrderPayment)) == 1


async def check_expired_order_is_closed(sessions, client):
    await seed_users(sessions)
    product_id = await seed_room(sessions)
    order = (await create(sessions, client, product_id)).json()
    async with sessions.begin() as db:
        row = await db.get(Order, order["id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    late = client.post(f"{API}/{order['id']}/payments", json={"idempotency_key": "late"},
                       headers=auth(GUEST))
    assert late.status_code == 409, late.text
    async with sessions.begin() as db:
        assert await order_service.expire_due(db) == 1
    offer = await stock_row(sessions, product_id)
    assert offer.reserved_quantity == 0
    async with sessions() as db:
        assert (await db.get(Order, order["id"])).status == "cancelled"


async def check_cancel_before_review_refunds(sessions, client):
    await seed_users(sessions)
    product_id = await seed_room(sessions)
    order = (await create(sessions, client, product_id)).json()
    client.post(f"{API}/{order['id']}/payments", json={"idempotency_key": "p"}, headers=auth(GUEST))
    cancelled = client.post(f"{API}/{order['id']}/cancel", json={"reason": "临时有事"},
                            headers=auth(GUEST))
    assert cancelled.status_code == 200, cancelled.text
    payload = cancelled.json()
    assert payload["status"] == "cancelled" and payload["fund_status"] == "refunded"
    assert payload["refunds"][0]["status"] == "succeeded"
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(OrderRefund)) == 1
    offer = await stock_row(sessions, product_id)
    assert (offer.reserved_quantity, offer.confirmed_quantity) == (0, 0)


async def check_reject_refunds_and_releases(sessions, client):
    await seed_users(sessions)
    product_id = await seed_room(sessions)
    order = (await create(sessions, client, product_id)).json()
    client.post(f"{API}/{order['id']}/payments", json={"idempotency_key": "p"}, headers=auth(GUEST))
    rejected = client.post(f"{ADMIN}/{order['id']}/reject", json={"reason": "供应商无法供给"},
                           headers=auth(OPERATOR))
    assert rejected.status_code == 200, rejected.text
    payload = rejected.json()
    assert payload["status"] == "cancelled" and payload["fund_status"] == "refunded"
    assert payload["review_note"] == "供应商无法供给"
    offer = await stock_row(sessions, product_id)
    assert offer.reserved_quantity == 0


async def check_cancel_request_flow(sessions, client):
    await seed_users(sessions)
    product_id = await seed_room(sessions)
    order = (await create(sessions, client, product_id)).json()
    client.post(f"{API}/{order['id']}/payments", json={"idempotency_key": "p"}, headers=auth(GUEST))
    client.post(f"{ADMIN}/{order['id']}/approve", json={}, headers=auth(OPERATOR))
    requested = client.post(f"{API}/{order['id']}/cancel-request", json={"reason": "行程变化"},
                            headers=auth(GUEST))
    assert requested.json()["status"] == "cancel_requested"
    declined = client.post(f"{ADMIN}/{order['id']}/cancel-request",
                           json={"approve": False, "note": "供应商暂不同意"},
                           headers=auth(OPERATOR))
    assert declined.json()["status"] == "confirmed"
    client.post(f"{API}/{order['id']}/cancel-request", json={"reason": "行程变化"}, headers=auth(GUEST))
    approved = client.post(f"{ADMIN}/{order['id']}/cancel-request",
                           json={"approve": True, "note": "酒店已同意退订"}, headers=auth(OPERATOR))
    payload = approved.json()
    assert payload["status"] == "cancelled" and payload["fund_status"] == "refunded"
    offer = await stock_row(sessions, product_id)
    assert (offer.reserved_quantity, offer.confirmed_quantity) == (0, 0)


async def check_oversell_is_rejected(sessions, client):
    await seed_users(sessions)
    product_id = await seed_room(sessions, total=1)
    first = await create(sessions, client, product_id, quantity=1)
    assert first.status_code == 201
    second = client.post(API, json=body(product_id), headers=auth(OTHER))
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["items"][0]["reason"] == "sold_out"
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Order)) == 1


async def check_ownership_is_enforced(sessions, client):
    await seed_users(sessions)
    product_id = await seed_room(sessions)
    order = (await create(sessions, client, product_id)).json()
    assert client.get(f"{API}/{order['id']}", headers=auth(OTHER)).status_code == 404
    assert client.get(f"{API}/{order['id']}", headers=auth(GUEST)).status_code == 200
    assert client.get(ADMIN, headers=auth(GUEST)).status_code == 403
    assert client.get(ADMIN, headers=auth(OPERATOR)).status_code == 200


SCENARIOS = [
    check_create_reserves_stock,
    check_duplicate_submit_returns_same_order,
    check_pay_then_review_confirm,
    check_payment_is_idempotent,
    check_expired_order_is_closed,
    check_cancel_before_review_refunds,
    check_reject_refunds_and_releases,
    check_cancel_request_flow,
    check_oversell_is_rejected,
    check_ownership_is_enforced,
]


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = database.create_db_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'orders.db'}", poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", factory)
    for module in (deps, routes):
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
def test_orders(api, sessions, scenario):
    asyncio.run(scenario(sessions, api))

