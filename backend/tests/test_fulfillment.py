"""Dispatch: assignment guards, overlap conflicts, release and candidates.

pytest 可收集；本机没有 pytest 时用 `python tests/test_fulfillment.py` 直接跑。
"""

import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from secrets import token_hex
from uuid import uuid4

try:
    import pytest
except ModuleNotFoundError:  # 本机可能没有 pytest，仍允许直接 python 运行
    import types

    class _Mark:
        @staticmethod
        def parametrize(*args, **kwargs):
            return lambda fn: fn

    pytest = types.SimpleNamespace(fixture=lambda *a, **k: (lambda fn: fn), mark=_Mark)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.config import settings  # noqa: E402
from app.db import database  # noqa: E402
from app.db.fulfillment_models import FulfillmentTask  # noqa: E402
from app.db.order_models import Order, OrderItem  # noqa: E402
from app.db.resource_models import Driver, Supplier, Vehicle  # noqa: E402
from app.services import fulfillment  # noqa: E402

DAY = date.today() + timedelta(days=3)
FLEET, OTHER_FLEET = "fleet-a", "fleet-b"
VEHICLE_A, VEHICLE_B = "veh-a", "veh-b"
DRIVER_A, DRIVER_B = "drv-a", "drv-b"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


async def seed(sessions):
    async with sessions.begin() as db:
        db.add_all([
            Supplier(id=FLEET, name="车队A", settlement_name="车队A", kind="vehicle_fleet"),
            Supplier(id=OTHER_FLEET, name="车队B", settlement_name="车队B", kind="vehicle_fleet"),
        ])
        await db.flush()
        db.add_all([
            Vehicle(id=VEHICLE_A, supplier_id=FLEET, plate_no="京A00001", model_name="5 座",
                    model_code="car5", seats=4, luggage=2, status="active"),
            Vehicle(id=VEHICLE_B, supplier_id=FLEET, plate_no="京A00002", model_name="7 座",
                    model_code="car7", seats=6, luggage=4, status="active"),
            Driver(id=DRIVER_A, supplier_id=FLEET, name="张师傅", phone="13800000001",
                   license_type="C1", service_cities=["北京"], model_codes=["car5"], status="active"),
            Driver(id=DRIVER_B, supplier_id=FLEET, name="李师傅", phone="13800000002",
                   license_type="B1", service_cities=["北京"], model_codes=["car5", "car7"],
                   status="active"),
        ])
        order = Order(id=str(uuid4()), order_no=f"ZY{uuid4().hex[:10].upper()}", user_id="guest",
                      status="confirmed", fund_status="paid", contact_name="张三",
                      contact_phone="13800000000", total_sale_fen=30000, total_cost_fen=20000,
                      expires_at=datetime.now(timezone.utc) + timedelta(minutes=15))
        db.add(order)
        await db.flush()
        db.add(OrderItem(id=str(uuid4()), order_id=order.id, product_id="p1", supplier_id=FLEET,
                         product_name="5 座 · 接机", product_type="vehicle",
                         attributes={"fleet": {"purpose": "airport_transfer"}}, service_date=DAY,
                         quantity=1, unit_sale_fen=30000, unit_cost_fen=20000,
                         subtotal_sale_fen=30000))
        return order.id


async def make_tasks(sessions, order_id: str, count: int, start_time: str = "09:00"):
    async with sessions.begin() as db:
        await fulfillment.generate_for_order(db, order_id)
        tasks = (await db.scalars(select(FulfillmentTask).where(
            FulfillmentTask.order_id == order_id))).all()
        for task in tasks:
            task.start_time = start_time
        return [task.id for task in tasks]


async def new_day_trip(sessions, order_id: str, start_time: str):
    """Add one more vehicle item so a second trip can be scheduled."""
    async with sessions.begin() as db:
        db.add(OrderItem(id=str(uuid4()), order_id=order_id, product_id="p1", supplier_id=FLEET,
                         product_name="5 座 · 包车", product_type="vehicle",
                         attributes={"fleet": {"purpose": "charter"}}, service_date=DAY,
                         quantity=1, unit_sale_fen=60000, unit_cost_fen=40000,
                         subtotal_sale_fen=60000))
        await db.flush()
        await fulfillment.generate_for_order(db, order_id)
        task = await db.scalar(select(FulfillmentTask).where(
            FulfillmentTask.order_id == order_id,
            FulfillmentTask.task_type == "vehicle_charter",
            FulfillmentTask.start_time.is_(None),
        ))
        task.start_time = start_time
        return task.id


async def assign(sessions, task_id, vehicle_id, driver_id):
    async with sessions.begin() as db:
        task = await db.get(FulfillmentTask, task_id)
        await fulfillment.assign_task(db, task, vehicle_id=vehicle_id, driver_id=driver_id,
                                      actor_id="op", actor_name="ops")
        return task.status


async def check_assign_marks_ready(sessions, order_id):
    task_id = (await make_tasks(sessions, order_id, 1))[0]
    status = await assign(sessions, task_id, VEHICLE_A, DRIVER_A)
    check("指派成功并转为 ready", status == "ready", status)


async def check_overlap_conflicts(sessions, order_id):
    first = (await make_tasks(sessions, order_id, 1, "09:00"))[0]
    await assign(sessions, first, VEHICLE_A, DRIVER_A)
    second = await new_day_trip(sessions, order_id, "09:30")
    try:
        await assign(sessions, second, VEHICLE_A, DRIVER_B)
    except Exception as error:
        detail = getattr(error, "detail", {})
        conflict = isinstance(detail, dict) and detail.get("conflicts")
        check("同车重叠时段被拒", getattr(error, "status_code", 0) == 409 and bool(conflict), str(detail))
    else:
        check("同车重叠时段被拒", False, "没有报错")


async def check_adjacent_is_allowed(sessions, order_id):
    first = (await make_tasks(sessions, order_id, 1, "09:00"))[0]
    await assign(sessions, first, VEHICLE_A, DRIVER_A)
    # 接机 120 分钟后正好结束，下一趟从 11:00 开始
    second = await new_day_trip(sessions, order_id, "11:00")
    status = await assign(sessions, second, VEHICLE_A, DRIVER_B)
    check("首尾相接时段可接续", status == "ready", status)


async def check_same_driver_blocks(sessions, order_id):
    first = (await make_tasks(sessions, order_id, 1, "09:00"))[0]
    await assign(sessions, first, VEHICLE_A, DRIVER_A)
    second = await new_day_trip(sessions, order_id, "09:30")
    try:
        await assign(sessions, second, VEHICLE_B, DRIVER_A)
    except Exception as error:
        check("同司机重叠时段被拒", getattr(error, "status_code", 0) == 409, str(error))
    else:
        check("同司机重叠时段被拒", False, "没有报错")


async def check_cross_fleet_rejected(sessions, order_id):
    task_id = (await make_tasks(sessions, order_id, 1))[0]
    async with sessions.begin() as db:
        db.add(Vehicle(id="veh-x", supplier_id=OTHER_FLEET, plate_no="京B00001", model_name="5 座",
                       model_code="car5", seats=4, luggage=2, status="active"))
        db.add(Driver(id="drv-x", supplier_id=OTHER_FLEET, name="王师傅", phone="13800000003",
                      license_type="C1", service_cities=["北京"], model_codes=["car5"], status="active"))
    async with sessions.begin() as db:
        task = await db.get(FulfillmentTask, task_id)
        try:
            await fulfillment.assign_task(db, task, vehicle_id="veh-x", driver_id=DRIVER_A)
        except Exception as error:
            check("跨车队车辆被拒", getattr(error, "status_code", 0) == 409, str(error))
        else:
            check("跨车队车辆被拒", False, "没有报错")
    async with sessions.begin() as db:
        task = await db.get(FulfillmentTask, task_id)
        try:
            await fulfillment.assign_task(db, task, vehicle_id=VEHICLE_A, driver_id="drv-x")
        except Exception as error:
            check("车与司机不同车队被拒", getattr(error, "status_code", 0) == 409, str(error))
        else:
            check("车与司机不同车队被拒", False, "没有报错")


async def check_inactive_and_qualification(sessions, order_id):
    task_id = (await make_tasks(sessions, order_id, 1))[0]
    async with sessions.begin() as db:
        vehicle = await db.get(Vehicle, VEHICLE_B)
        vehicle.status = "inactive"
    async with sessions.begin() as db:
        task = await db.get(FulfillmentTask, task_id)
        try:
            await fulfillment.assign_task(db, task, vehicle_id=VEHICLE_B, driver_id=DRIVER_B)
        except Exception as error:
            check("停用车辆被拒", getattr(error, "status_code", 0) == 409, str(error))
        else:
            check("停用车辆被拒", False, "没有报错")
    async with sessions.begin() as db:
        task = await db.get(FulfillmentTask, task_id)
        try:
            await fulfillment.assign_task(db, task, vehicle_id=VEHICLE_B, driver_id=DRIVER_A)
        except Exception as error:
            check("车型资格不符被拒", getattr(error, "status_code", 0) in (409, 401), str(error))
        else:
            check("车型资格不符被拒", False, "没有报错")


async def check_release_then_reassign(sessions, order_id):
    task_id = (await make_tasks(sessions, order_id, 1))[0]
    await assign(sessions, task_id, VEHICLE_A, DRIVER_A)
    async with sessions.begin() as db:
        task = await db.get(FulfillmentTask, task_id)
        await fulfillment.release_assignment(db, task, actor_id="op", actor_name="ops")
        released = task.status
    status = await assign(sessions, task_id, VEHICLE_A, DRIVER_A)
    check("撤派回到 pending 且可再派", released == "pending" and status == "ready",
          f"{released}->{status}")


async def check_vehicle_task_requires_assignment_to_start(sessions, order_id):
    task_id = (await make_tasks(sessions, order_id, 1))[0]
    async with sessions.begin() as db:
        task = await db.get(FulfillmentTask, task_id)
        await fulfillment.confirm_credentials(db, task, confirmation_no="V-1", actor_id="op")
    async with sessions.begin() as db:
        task = await db.get(FulfillmentTask, task_id)
        try:
            await fulfillment.start_task(db, task, actor_id="op")
        except Exception as error:
            check("未指派不能开始", getattr(error, "status_code", 0) == 409, str(error))
        else:
            check("未指派不能开始", False, "没有报错")


async def check_candidates_exclude_busy(sessions, order_id):
    first = (await make_tasks(sessions, order_id, 1, "09:00"))[0]
    await assign(sessions, first, VEHICLE_A, DRIVER_A)
    second = await new_day_trip(sessions, order_id, "09:30")
    async with sessions() as db:
        task = await db.get(FulfillmentTask, second)
        candidates = await fulfillment.candidate_resources(db, task)
    vehicles = [item["id"] for item in candidates["vehicles"]]
    drivers = [item["id"] for item in candidates["drivers"]]
    check("候选中排除占用车辆", VEHICLE_A not in vehicles, str(vehicles))
    check("候选中排除占用司机", DRIVER_A not in drivers, str(drivers))
    check("候选中保留空闲车辆", VEHICLE_B in vehicles, str(vehicles))


SCENARIOS = [
    (check_assign_marks_ready, True),
    (check_overlap_conflicts, True),
    (check_adjacent_is_allowed, True),
    (check_same_driver_blocks, True),
    (check_cross_fleet_rejected, True),
    (check_inactive_and_qualification, True),
    (check_release_then_reassign, True),
    (check_vehicle_task_requires_assignment_to_start, True),
    (check_candidates_exclude_busy, True),
]


async def run_one(scenario):
    name = scenario.__name__.removeprefix("check_")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"_ff_{name}.db")
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
        order_id = await seed(sessions)
        await scenario(sessions, order_id)
        return list(RESULTS)
    finally:
        await engine.dispose()
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = database.create_db_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'ff.db'}", poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", factory)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
    asyncio.run(database.init_db())
    yield factory
    asyncio.run(engine.dispose())


@pytest.mark.parametrize("scenario", [item[0] for item in SCENARIOS],
                         ids=lambda fn: fn.__name__.removeprefix("check_"))
def test_dispatch(sessions, scenario):
    async def run():
        RESULTS.clear()
        order_id = await seed(sessions)
        await scenario(sessions, order_id)
    asyncio.run(run())
    failed = [detail for _, ok, detail in RESULTS if not ok]
    assert not failed, failed


if __name__ == "__main__":
    passed = failed = 0
    for scenario, _ in SCENARIOS:
        rows = asyncio.run(run_one(scenario))
        for name, ok, detail in rows:
            print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail and not ok else ""))
            passed += 1 if ok else 0
            failed += 0 if ok else 1
    print(f"\n合计 {passed + failed} 项，通过 {passed}，失败 {failed}")
    raise SystemExit(1 if failed else 0)


