"""Generate fulfillment tasks from confirmed orders and drive their lifecycle."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.fulfillment_models import DispatchAssignment, FulfillmentEvent, FulfillmentTask
from app.db.order_models import Order, OrderItem

TERMINAL = {"completed", "cancelled"}
DURATIONS = {"hotel_checkin": 0, "ticket_entry": 0, "vehicle_pickup": 120, "vehicle_charter": 600}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _task_type(item: OrderItem) -> str:
    if item.product_type == "hotel_room":
        return "hotel_checkin"
    if item.product_type == "attraction_ticket":
        return "ticket_entry"
    if item.product_type == "vehicle":
        purpose = str((item.attributes or {}).get("fleet", {}).get("purpose")
                      or (item.attributes or {}).get("purpose") or "charter")
        return "vehicle_pickup" if purpose == "airport_transfer" else "vehicle_charter"
    return "other"


async def _event(db, task, kind, *, actor_id=None, actor_name=None, reason="", before=None, after=None,
                 from_status=None) -> None:
    db.add(FulfillmentEvent(
        task_id=task.id, kind=kind, from_status=from_status, to_status=task.status,
        before=before, after=after, actor_id=actor_id, actor_name=actor_name, reason=reason,
    ))


async def generate_for_order(db: AsyncSession, order_id: str) -> int:
    """Idempotent: one task per order item, only for confirmed orders."""
    order = await db.get(Order, order_id)
    if order is None or order.status != "confirmed":
        return 0
    items = (await db.scalars(select(OrderItem).where(OrderItem.order_id == order_id))).all()
    existing = set((await db.scalars(select(FulfillmentTask.order_item_id).where(
        FulfillmentTask.order_id == order_id))).all())
    created = 0
    for item in items:
        if item.id in existing:
            continue
        task_type = _task_type(item)
        task = FulfillmentTask(
            order_id=order_id, order_item_id=item.id, user_id=order.user_id, task_type=task_type,
            service_date=item.service_date.isoformat(), duration_minutes=DURATIONS.get(task_type, 0),
            quantity=item.quantity, product_name=item.product_name,
            supplier_id=item.supplier_id, supplier_name="",
            status="pending", version=1,
        )
        db.add(task)
        await db.flush()
        await _event(db, task, "created", from_status=None)
        created += 1
    await db.flush()
    return created


async def get_task(db: AsyncSession, task_id: str) -> FulfillmentTask:
    task = await db.get(FulfillmentTask, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task


def _check_version(task: FulfillmentTask, expected: int | None) -> None:
    if expected is not None and expected != task.version:
        raise HTTPException(409, {"message": "该任务已被其他操作修改，请刷新后重试。",
                                  "current_version": task.version})


async def confirm_credentials(
    db, task, *, voucher_no: str = "", confirmation_no: str = "", actor_id=None, actor_name=None,
    expected_version: int | None = None,
) -> FulfillmentTask:
    _check_version(task, expected_version)
    if task.status not in ("pending",):
        raise HTTPException(409, {"message": "只有待处理的任务可以登记凭证。", "status": task.status})
    if not voucher_no.strip() and not confirmation_no.strip():
        raise HTTPException(422, "请至少填写票号或供应商确认号。")
    before = {"voucher_no": task.voucher_no, "confirmation_no": task.confirmation_no}
    task.voucher_no = voucher_no.strip()[:64]
    task.confirmation_no = confirmation_no.strip()[:64]
    task.status = "ready"
    task.version += 1
    await _event(db, task, "confirmed", from_status="pending",
                 actor_id=actor_id, actor_name=actor_name,
                 before=before, after={"voucher_no": task.voucher_no})
    await db.flush()
    return task


async def start_task(db, task, *, actor_id=None, actor_name=None, expected_version=None):
    _check_version(task, expected_version)
    if task.status != "ready":
        raise HTTPException(409, {"message": "只有已就绪的任务可以开始。", "status": task.status})
    if task.task_type in ("hotel_checkin", "ticket_entry") and not (task.voucher_no or task.confirmation_no):
        raise HTTPException(409, "缺少凭证或供应商确认号，不能开始。")
    assignment = await db.scalar(select(DispatchAssignment).where(
        DispatchAssignment.task_id == task.id, DispatchAssignment.released_at.is_(None)))
    if task.task_type in ("vehicle_pickup", "vehicle_charter") and assignment is None:
        raise HTTPException(409, "用车任务尚未指派车辆与司机，不能开始。")
    task.status = "in_progress"
    task.started_at = _now()
    task.version += 1
    await _event(db, task, "started", from_status="ready", actor_id=actor_id, actor_name=actor_name)
    await db.flush()
    return task


async def complete_task(db, task, *, actor_id=None, actor_name=None, expected_version=None):
    _check_version(task, expected_version)
    if task.status != "in_progress":
        raise HTTPException(409, {"message": "只有进行中的任务可以完成。", "status": task.status})
    task.status = "completed"
    task.completed_at = _now()
    task.version += 1
    await _event(db, task, "completed", from_status="in_progress",
                 actor_id=actor_id, actor_name=actor_name)
    await db.flush()
    return task


async def mark_exception(db, task, *, reason: str, actor_id=None, actor_name=None,
                         expected_version=None):
    _check_version(task, expected_version)
    if task.status in TERMINAL:
        raise HTTPException(409, {"message": "已结束的任务不能登记异常。", "status": task.status})
    if not reason.strip():
        raise HTTPException(422, "请填写异常原因。")
    task.previous_status = task.status
    task.exception_reason = reason.strip()[:1000]
    task.status = "exception"
    task.version += 1
    await _event(db, task, "exception", from_status=task.previous_status, reason=task.exception_reason,
                 actor_id=actor_id, actor_name=actor_name)
    await db.flush()
    return task


async def recover_task(db, task, *, actor_id=None, actor_name=None, expected_version=None):
    _check_version(task, expected_version)
    if task.status != "exception":
        raise HTTPException(409, {"message": "只有异常任务可以恢复。", "status": task.status})
    target = task.previous_status or "pending"
    task.status = target
    task.exception_reason = ""
    task.previous_status = None
    task.version += 1
    await _event(db, task, "recovered", from_status="exception", actor_id=actor_id, actor_name=actor_name)
    await db.flush()
    return task


async def cancel_task(db, task, *, reason: str, actor_id=None, actor_name=None, expected_version=None):
    _check_version(task, expected_version)
    if task.status in TERMINAL:
        raise HTTPException(409, {"message": "该任务已经结束。", "status": task.status})
    if not reason.strip():
        raise HTTPException(422, "请填写作废原因。")
    from_status = task.status
    task.status = "cancelled"
    task.version += 1
    await db.execute(
        DispatchAssignment.__table__.update()
        .where(DispatchAssignment.task_id == task.id, DispatchAssignment.released_at.is_(None))
        .values(released_at=_now())
    )
    await _event(db, task, "cancelled", from_status=from_status, reason=reason.strip()[:500],
                 actor_id=actor_id, actor_name=actor_name)
    await db.flush()
    return task


async def list_tasks(db, *, status=None, task_type=None, service_date=None, order_id=None,
                     offset=0, limit=20):
    filters = []
    if status:
        filters.append(FulfillmentTask.status == status)
    if task_type:
        filters.append(FulfillmentTask.task_type == task_type)
    if service_date:
        filters.append(FulfillmentTask.service_date == service_date.isoformat())
    if order_id:
        filters.append(FulfillmentTask.order_id == order_id)
    total = await db.scalar(select(func.count()).select_from(FulfillmentTask).where(*filters))
    rows = (await db.scalars(
        select(FulfillmentTask).where(*filters)
        .order_by(FulfillmentTask.service_date, FulfillmentTask.created_at)
        .offset(offset).limit(limit))).all()
    return rows, total or 0


def _window(task):
    """Left-closed right-open UTC window; missing start time means unknown."""
    from datetime import date as _date, datetime, time, timedelta, timezone

    if not task.start_time:
        return None
    try:
        hour, minute = (int(part) for part in task.start_time.split(":"))
    except ValueError:
        return None
    start = datetime.combine(_date.fromisoformat(task.service_date), time(hour, minute),
                             tzinfo=timezone.utc)
    return start, start + timedelta(minutes=max(1, task.duration_minutes or 60))


async def _conflicts(db, *, vehicle_id, driver_id, window, task_id) -> list:
    rows = (await db.execute(
        select(DispatchAssignment, FulfillmentTask)
        .join(FulfillmentTask, FulfillmentTask.id == DispatchAssignment.task_id)
        .where(DispatchAssignment.released_at.is_(None),
               DispatchAssignment.task_id != task_id,
               FulfillmentTask.status != "cancelled")
    )).all()
    hits = []
    for assignment, other in rows:
        if vehicle_id and assignment.vehicle_id != vehicle_id:
            if not (driver_id and assignment.driver_id == driver_id):
                continue
        elif not vehicle_id and (not driver_id or assignment.driver_id != driver_id):
            continue
        other_window = _window(other)
        if window is None or other_window is None or (
            window[0] < other_window[1] and other_window[0] < window[1]
        ):
            hits.append(other)
    return hits


async def assign_task(db, task, *, vehicle_id: str, driver_id: str, actor_id=None,
                      actor_name=None, expected_version=None):
    from datetime import datetime, timezone

    from app.db.resource_models import Driver, Supplier, Vehicle

    _check_version(task, expected_version)
    if task.task_type not in ("vehicle_pickup", "vehicle_charter"):
        raise HTTPException(409, "只有用车任务需要指派车辆与司机。")
    if task.status not in ("pending", "ready"):
        raise HTTPException(409, {"message": "该任务当前不能指派。", "status": task.status})
    vehicle, driver = await db.get(Vehicle, vehicle_id), await db.get(Driver, driver_id)
    if vehicle is None or driver is None:
        raise HTTPException(404, "车辆或司机不存在")
    if vehicle.status != "active" or driver.status != "active":
        raise HTTPException(409, "车辆或司机已停用，不能指派。")
    if vehicle.supplier_id != driver.supplier_id:
        raise HTTPException(409, "车辆与司机必须属于同一车队。")
    if task.supplier_id and vehicle.supplier_id != task.supplier_id:
        raise HTTPException(409, "该任务只能派给订单约定的车队。")
    supplier = await db.get(Supplier, vehicle.supplier_id)
    if supplier is None or supplier.status != "active":
        raise HTTPException(409, "车队已停用，不能指派。")
    if driver.model_codes and vehicle.model_code and vehicle.model_code not in driver.model_codes:
        raise HTTPException(409, "该司机不具备此车型资格。")
    hits = await _conflicts(db, vehicle_id=vehicle_id, driver_id=driver_id,
                            window=_window(task), task_id=task.id)
    if hits:
        raise HTTPException(409, {
            "message": "车辆或司机在该时段已有任务，请换人或换时段。",
            "conflicts": [{"task_id": hit.id, "service_date": hit.service_date,
                           "start_time": hit.start_time} for hit in hits],
        })
    await db.execute(DispatchAssignment.__table__.update().where(
        DispatchAssignment.task_id == task.id, DispatchAssignment.released_at.is_(None),
    ).values(released_at=datetime.now(timezone.utc)))
    db.add(DispatchAssignment(task_id=task.id, vehicle_id=vehicle_id, driver_id=driver_id,
                              assigned_by=actor_id or "system", assigned_by_name=actor_name or ""))
    from_status = task.status
    task.status = "ready"
    task.version += 1
    await _event(db, task, "assigned", from_status=from_status, actor_id=actor_id,
                 actor_name=actor_name, after={"vehicle_id": vehicle_id, "driver_id": driver_id})
    await db.flush()


async def release_assignment(db, task, *, actor_id=None, actor_name=None, expected_version=None):
    from datetime import datetime, timezone

    _check_version(task, expected_version)
    if task.status == "in_progress":
        raise HTTPException(409, "进行中的任务不能撤派。")
    assignment = await db.scalar(select(DispatchAssignment).where(
        DispatchAssignment.task_id == task.id, DispatchAssignment.released_at.is_(None)))
    if assignment is None:
        raise HTTPException(409, "该任务当前没有指派。")
    assignment.released_at = datetime.now(timezone.utc)
    task.status = "pending"
    task.version += 1
    await _event(db, task, "released", from_status="ready", actor_id=actor_id, actor_name=actor_name)
    await db.flush()


async def candidate_resources(db, task) -> dict:
    from app.db.resource_models import Driver, Vehicle

    if not task.supplier_id:
        return {"vehicles": [], "drivers": []}
    window = _window(task)
    vehicles = (await db.scalars(select(Vehicle).where(
        Vehicle.supplier_id == task.supplier_id, Vehicle.status == "active"))).all()
    drivers = (await db.scalars(select(Driver).where(
        Driver.supplier_id == task.supplier_id, Driver.status == "active"))).all()
    free_vehicles = [
        {"id": v.id, "plate_no": v.plate_no, "model_name": v.model_name, "seats": v.seats}
        for v in vehicles
        if not await _conflicts(db, vehicle_id=v.id, driver_id=None, window=window, task_id=task.id)
    ]
    free_drivers = [
        {"id": d.id, "name": d.name, "license_type": d.license_type}
        for d in drivers
        if not await _conflicts(db, vehicle_id=None, driver_id=d.id, window=window, task_id=task.id)
    ]
    return {"vehicles": free_vehicles, "drivers": free_drivers}


async def void_tasks_for_order(db, order_id: str, *, reason: str, actor_id=None, actor_name=None) -> int:
    """订单取消后作废未完成任务；已完成与已作废的保留历史。"""
    tasks = (await db.scalars(select(FulfillmentTask).where(
        FulfillmentTask.order_id == order_id,
        FulfillmentTask.status.not_in(("completed", "cancelled")),
    ))).all()
    for task in tasks:
        await cancel_task(db, task, reason=reason, actor_id=actor_id, actor_name=actor_name)
    return len(tasks)


async def order_completion_blockers(db, order_id: str) -> dict:
    """完成守卫：没有未完成任务，且至少一项实际完成。"""
    tasks = (await db.scalars(select(FulfillmentTask).where(
        FulfillmentTask.order_id == order_id))).all()
    unfinished = [task for task in tasks if task.status not in ("completed", "cancelled")]
    completed = [task for task in tasks if task.status == "completed"]
    return {"total": len(tasks), "unfinished": unfinished, "completed": len(completed),
            "ok": not unfinished and len(completed) > 0}


async def board(db, *, day=None, days: int = 7) -> dict:
    """今日、未来 N 天与异常清单。"""
    from datetime import date as _date, timedelta

    today = day or _date.today()
    horizon = today + timedelta(days=max(1, days))
    rows = (await db.scalars(select(FulfillmentTask).where(
        FulfillmentTask.service_date >= today.isoformat(),
        FulfillmentTask.service_date < horizon.isoformat(),
    ))).all()
    by_status: dict[str, int] = {}
    for task in rows:
        by_status[task.status] = by_status.get(task.status, 0) + 1
    per_day, exceptions = [], []
    for offset in range(max(1, days)):
        current = (today + timedelta(days=offset)).isoformat()
        of_day = [task for task in rows if task.service_date == current]
        per_day.append({
            "date": current, "total": len(of_day),
            "ready": sum(1 for t in of_day if t.status == "ready"),
            "in_progress": sum(1 for t in of_day if t.status == "in_progress"),
            "pending": sum(1 for t in of_day if t.status == "pending"),
        })
    for task in rows:
        if task.status == "exception":
            exceptions.append({"id": task.id, "task_type": task.task_type,
                               "service_date": task.service_date,
                               "reason": task.exception_reason})
    return {"today": today.isoformat(), "by_status": by_status, "per_day": per_day,
            "exceptions": exceptions, "total": len(rows)}


async def task_detail(db, task_id: str) -> dict:
    task = await get_task(db, task_id)
    events = (await db.scalars(select(FulfillmentEvent).where(
        FulfillmentEvent.task_id == task_id).order_by(FulfillmentEvent.created_at))).all()
    assignment = await db.scalar(select(DispatchAssignment).where(
        DispatchAssignment.task_id == task_id, DispatchAssignment.released_at.is_(None)))
    return {"task": task, "events": events, "assignment": assignment}


