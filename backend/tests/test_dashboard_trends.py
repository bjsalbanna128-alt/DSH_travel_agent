"""Dashboard trends: Beijing day bucketing, refunds, categories, tasks and fleet.

pytest 可收集；本机没有 pytest 时用 `python tests/test_dashboard_trends.py` 直接跑。
"""

import asyncio
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from secrets import token_hex
from uuid import uuid4

try:
    import pytest
except ModuleNotFoundError:  # 本机可能没有 pytest
    import types

    class _Mark:
        @staticmethod
        def parametrize(*args, **kwargs):
            return lambda fn: fn

    pytest = types.SimpleNamespace(fixture=lambda *a, **k: (lambda fn: fn), mark=_Mark)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import database  # noqa: E402
from app.db.fulfillment_models import FulfillmentTask  # noqa: E402
from app.db.fleet_models import FleetAllocation  # noqa: E402
from app.db.order_models import Order, OrderItem, OrderPayment, OrderRefund  # noqa: E402
from app.db.resource_models import Supplier, Vehicle  # noqa: E402
from app.services.dashboard import load_trends  # noqa: E402
from app.services.member_points import BEIJING  # noqa: E402

RESULTS = []
SUPPLIER = "sup-1"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def beijing_today() -> date:
    return datetime.now(timezone.utc).astimezone(BEIJING).date()


def beijing_at(day: date, hour: int, minute: int = 0) -> datetime:
    """UTC instant for a Beijing wall clock time."""
    return datetime.combine(day, time(hour, minute), tzinfo=BEIJING).astimezone(timezone.utc)


async def ensure_supplier(db):
    db.add(Supplier(id=SUPPLIER, name="车队", settlement_name="车队", kind="vehicle_fleet"))


async def add_order(db, *, paid_at=None, refund=None, items=(), status="confirmed"):
    order = Order(
        id=str(uuid4()), order_no=f"ZY{uuid4().hex[:10].upper()}", user_id="guest",
        status=status, fund_status="paid" if paid_at else "unpaid", contact_name="张三",
        contact_phone="13800000000",
        total_sale_fen=sum(item["subtotal"] for item in items),
        total_cost_fen=0,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(order)
    await db.flush()
    for item in items:
        db.add(OrderItem(
            id=str(uuid4()), order_id=order.id, product_id="p1", supplier_id=SUPPLIER,
            product_name=item["type"], product_type=item["type"], attributes={},
            service_date=item.get("service_date") or beijing_today(),
            quantity=1, unit_sale_fen=item["subtotal"], unit_cost_fen=0,
            subtotal_sale_fen=item["subtotal"],
        ))
    if paid_at is not None:
        db.add(OrderPayment(
            id=str(uuid4()), order_id=order.id, provider="mock", amount_fen=order.total_sale_fen,
            event_id=f"evt-{uuid4().hex}", idempotency_key=f"idem-{uuid4().hex}", paid_at=paid_at,
        ))
    if refund is not None:
        amount, processed_at = refund
        db.add(OrderRefund(
            id=str(uuid4()), order_id=order.id, refund_no=f"RF{uuid4().hex[:12].upper()}",
            amount_fen=amount, status="succeeded", processed_at=processed_at,
        ))
    return order


def series_row(payload, day: date):
    for row in payload.series:
        if row.date == day:
            return row
    return None


async def scenario_empty(sessions):
    today = beijing_today()
    async with sessions() as db:
        payload = await load_trends(db, 7)
    check("空库返回 7 天", len(payload.series) == 7, str(len(payload.series)))
    check("最后一天是北京时间今天", payload.series[-1].date == today, str(payload.series[-1].date))
    check("序列连续", all(
        (payload.series[index + 1].date - payload.series[index].date).days == 1
        for index in range(6)
    ))
    check("空库全部为 0", all(point.paid_fen == 0 and point.orders == 0 for point in payload.series))
    check("序列化含 from/to", {"from", "to"} <= set(payload.model_dump(by_alias=True)), str(
        set(payload.model_dump(by_alias=True))))


async def scenario_today_and_yesterday(sessions):
    today = beijing_today()
    yesterday = today - timedelta(days=1)
    async with sessions.begin() as db:
        await ensure_supplier(db)
        await add_order(db, paid_at=beijing_at(today, 10), items=[{"type": "hotel_room", "subtotal": 50000}])
        await add_order(db, paid_at=beijing_at(yesterday, 9), items=[{"type": "hotel_room", "subtotal": 30000}])
    async with sessions() as db:
        payload = await load_trends(db, 7)
    today_row, yesterday_row = series_row(payload, today), series_row(payload, yesterday)
    check("今日收款计入今日", today_row.paid_fen == 50000, str(today_row))
    check("昨日收款归昨日", yesterday_row.paid_fen == 30000, str(yesterday_row))
    check("客单价按日计算", today_row.avg_order_fen == 50000 and yesterday_row.avg_order_fen == 30000)
    check("总计等于各日之和", payload.totals.paid_fen == 80000 and payload.totals.orders == 2)


async def scenario_utc_boundary(sessions):
    today = beijing_today()
    # 北京时间今日 00:30 == UTC 昨日 16:30，必须归入今日
    async with sessions.begin() as db:
        await ensure_supplier(db)
        await add_order(db, paid_at=beijing_at(today, 0, 30), items=[
            {"type": "attraction_ticket", "subtotal": 6000}])
    async with sessions() as db:
        payload = await load_trends(db, 7)
    row = series_row(payload, today)
    check("UTC 跨日归入北京日", row.paid_fen == 6000, str(row))


async def scenario_refund(sessions):
    today = beijing_today()
    async with sessions.begin() as db:
        await ensure_supplier(db)
        await add_order(db, paid_at=beijing_at(today, 9),
                        items=[{"type": "hotel_room", "subtotal": 20000}],
                        refund=(12000, beijing_at(today, 11)))
    async with sessions() as db:
        payload = await load_trends(db, 7)
    row = series_row(payload, today)
    check("退款计入当日", row.refund_fen == 12000, str(row))
    check("净收款为收款减退款", row.net_fen == 8000, str(row))
    check("退款不回改历史收款", row.paid_fen == 20000, str(row))
    check("全额退款订单仍计入订单数", row.orders == 1, str(row))


async def scenario_categories(sessions):
    today = beijing_today()
    async with sessions.begin() as db:
        await ensure_supplier(db)
        await add_order(db, paid_at=beijing_at(today, 8), items=[
            {"type": "hotel_room", "subtotal": 35000},
            {"type": "attraction_ticket", "subtotal": 6000},
            {"type": "vehicle", "subtotal": 30000},
        ])
    async with sessions() as db:
        payload = await load_trends(db, 7)
    amounts = {row.product_type: row.amount_fen for row in payload.by_category}
    check("品类金额正确", amounts == {"hotel_room": 35000, "attraction_ticket": 6000,
                                      "vehicle": 30000}, str(amounts))
    check("品类之和等于收款", sum(amounts.values()) == payload.totals.paid_fen, str(amounts))


async def scenario_tasks_and_fleet(sessions):
    from sqlalchemy import select

    today = beijing_today()
    async with sessions.begin() as db:
        await ensure_supplier(db)
        order = await add_order(db, paid_at=beijing_at(today, 8), items=[
            {"type": "vehicle", "subtotal": 30000},
            {"type": "vehicle", "subtotal": 30000},
        ])
        db.add(Vehicle(id="veh-1", supplier_id=SUPPLIER, plate_no="京A00001",
                       model_name="5 座", model_code="car5", seats=4, luggage=2, status="active"))
        db.add(Vehicle(id="veh-2", supplier_id=SUPPLIER, plate_no="京A00002",
                       model_name="5 座", model_code="car5", seats=4, luggage=2, status="inactive"))
        await db.flush()
        items = (await db.scalars(select(OrderItem).where(OrderItem.order_id == order.id))).all()
        for status in ("ready", "pending", "cancelled"):
            db.add(FulfillmentTask(
                id=str(uuid4()), order_id=order.id, order_item_id=str(uuid4()),
                task_type="vehicle_charter", service_date=today.isoformat(),
                duration_minutes=600, quantity=1, status=status,
            ))
        starts = beijing_at(today, 9)
        db.add(FleetAllocation(
            order_item_id=items[0].id, order_id=order.id, supplier_id=SUPPLIER,
            service_key="k1", model_code="car5", starts_at=starts,
            ends_at=starts + timedelta(minutes=600), passengers=2, luggage=1,
            state="confirmed", vehicle_id="veh-1",
        ))
        db.add(FleetAllocation(
            order_item_id=items[1].id, order_id=order.id, supplier_id=SUPPLIER,
            service_key="k2", model_code="car5", starts_at=starts,
            ends_at=starts + timedelta(minutes=600), passengers=2, luggage=1,
            state="confirmed", vehicle_id=None,
        ))
    async with sessions() as db:
        payload = await load_trends(db, 7)
    row = series_row(payload, today)
    check("履约任务排除作废", row.fulfillment_total == 2, str(row))
    check("就绪数只算 ready 及以上", row.fulfillment_ready == 1, str(row))
    check("车队占用只算已固定人车", row.fleet_used == 1, str(row))
    check("车队容量只算启用车辆", row.fleet_capacity == 1, str(row))


async def scenario_invalid_days(sessions):
    async with sessions() as db:
        try:
            await load_trends(db, 15)
        except ValueError:
            check("服务层拒绝非 7/30", True)
        else:
            check("服务层拒绝非 7/30", False, "没有报错")
    from app.main import app
    parameters = app.openapi()["paths"]["/api/v1/admin/dashboard/trends"]["get"]["parameters"]
    days = next(item for item in parameters if item["name"] == "days")
    schema = days["schema"]
    check("days 是整数参数", schema.get("type") == "integer" or "anyOf" in schema, str(schema))
    source = open(__file__, encoding="utf-8").read()
    route = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                              "app", "api", "admin.py"), encoding="utf-8").read()
    check("路由对非法 days 返回 422", "days 只能是 7 或 30" in route, "缺少 422 守卫")


SCENARIOS = [
    scenario_empty,
    scenario_today_and_yesterday,
    scenario_utc_boundary,
    scenario_refund,
    scenario_categories,
    scenario_tasks_and_fleet,
    scenario_invalid_days,
]


async def run_one(scenario):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"_trends_{scenario.__name__}.db")
    if os.path.exists(path):
        os.remove(path)
    engine = database.create_db_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    database.engine = engine
    database.async_session = sessions
    settings.jwt_secret_key = token_hex(32)
    await database.init_db()
    try:
        RESULTS.clear()
        await scenario(sessions)
        return list(RESULTS)
    finally:
        await engine.dispose()
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = database.create_db_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'trends.db'}", poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", factory)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
    asyncio.run(database.init_db())
    yield factory
    asyncio.run(engine.dispose())


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda fn: fn.__name__.removeprefix("scenario_"))
def test_trends(sessions, scenario):
    async def run():
        RESULTS.clear()
        await scenario(sessions)
    asyncio.run(run())
    failed = [detail for _, ok, detail in RESULTS if not ok]
    assert not failed, failed


if __name__ == "__main__":
    passed = failed = 0
    for scenario in SCENARIOS:
        rows = asyncio.run(run_one(scenario))
        for name, ok, detail in rows:
            print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail and not ok else ""))
            passed += 1 if ok else 0
            failed += 0 if ok else 1
    print(f"\n合计 {passed + failed} 项，通过 {passed}，失败 {failed}")
    raise SystemExit(1 if failed else 0)
