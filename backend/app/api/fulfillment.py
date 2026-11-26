"""Operator fulfillment routes: task list, detail and lifecycle actions."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import CurrentOperator, DbSession as DB, WriteDbSession as WriteDB
from app.api.support import Page, no_store
from app.services import fulfillment

router = APIRouter(prefix="/fulfillment", dependencies=[Depends(no_store)])

TaskStatus = Literal["pending", "ready", "in_progress", "completed", "exception", "cancelled"]
TaskType = Literal["hotel_checkin", "ticket_entry", "vehicle_pickup", "vehicle_charter", "other"]


class ActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int | None = Field(None, ge=1)


class CredentialBody(ActionBody):
    voucher_no: str = Field("", max_length=64)
    confirmation_no: str = Field("", max_length=64)


class ReasonBody(ActionBody):
    reason: str = Field(min_length=1, max_length=1000)


class AssignBody(ActionBody):
    vehicle_id: str = Field(min_length=1, max_length=36)
    driver_id: str = Field(min_length=1, max_length=36)


def _summary(task) -> dict:
    return {
        "id": task.id, "order_id": task.order_id, "task_type": task.task_type,
        "service_date": task.service_date, "start_time": task.start_time,
        "product_name": task.product_name, "quantity": task.quantity, "status": task.status,
        "supplier_name": task.supplier_name, "version": task.version,
    }


def _detail(payload: dict) -> dict:
    task = payload["task"]
    return {
        **_summary(task),
        "order_item_id": task.order_item_id, "location_name": task.location_name,
        "voucher_no": task.voucher_no, "confirmation_no": task.confirmation_no,
        "notes": task.notes, "exception_reason": task.exception_reason,
        "started_at": task.started_at, "completed_at": task.completed_at,
        "assignment": None if payload["assignment"] is None else {
            "vehicle_id": payload["assignment"].vehicle_id,
            "driver_id": payload["assignment"].driver_id,
            "assigned_by_name": payload["assignment"].assigned_by_name,
            "assigned_at": payload["assignment"].assigned_at,
        },
        "events": [
            {"kind": event.kind, "from_status": event.from_status, "to_status": event.to_status,
             "actor_name": event.actor_name, "reason": event.reason, "created_at": event.created_at}
            for event in payload["events"]
        ],
    }


@router.get("")
async def list_tasks(
    db: DB, page: Page, status: TaskStatus | None = None, task_type: TaskType | None = None,
    service_date: date | None = None, order_id: str | None = None,
):
    rows, total = await fulfillment.list_tasks(
        db, status=status, task_type=task_type, service_date=service_date, order_id=order_id,
        offset=page.offset, limit=page.limit,
    )
    return {"items": [_summary(task) for task in rows], "total": total}


@router.get("/board")
async def board(db: DB, day: date | None = None, days: int = 7):
    """今日与未来 N 天的任务分布及异常清单。"""
    return await fulfillment.board(db, day=day, days=max(1, min(days, 30)))


@router.post("/generate/{order_id}")
async def generate(order_id: str, db: WriteDB):
    """Idempotent task generation for one confirmed order."""
    return {"created": await fulfillment.generate_for_order(db, order_id)}


@router.get("/{task_id}")
async def task_detail(task_id: str, db: DB):
    return _detail(await fulfillment.task_detail(db, task_id))


@router.get("/{task_id}/candidates")
async def candidates(task_id: str, db: DB):
    task = await fulfillment.get_task(db, task_id)
    return await fulfillment.candidate_resources(db, task)


@router.post("/{task_id}/assign")
async def assign(task_id: str, data: AssignBody, operator: CurrentOperator, db: WriteDB):
    task = await fulfillment.get_task(db, task_id)
    await fulfillment.assign_task(
        db, task, vehicle_id=data.vehicle_id, driver_id=data.driver_id,
        actor_id=operator.id, actor_name=operator.username, expected_version=data.expected_version,
    )
    return _detail(await fulfillment.task_detail(db, task_id))


@router.post("/{task_id}/release")
async def release(task_id: str, data: ActionBody, operator: CurrentOperator, db: WriteDB):
    task = await fulfillment.get_task(db, task_id)
    await fulfillment.release_assignment(
        db, task, actor_id=operator.id, actor_name=operator.username,
        expected_version=data.expected_version,
    )
    return _detail(await fulfillment.task_detail(db, task_id))


@router.post("/{task_id}/confirm")
async def confirm(task_id: str, data: CredentialBody, operator: CurrentOperator, db: WriteDB):
    task = await fulfillment.get_task(db, task_id)
    await fulfillment.confirm_credentials(
        db, task, voucher_no=data.voucher_no, confirmation_no=data.confirmation_no,
        actor_id=operator.id, actor_name=operator.username, expected_version=data.expected_version,
    )
    return _detail(await fulfillment.task_detail(db, task_id))


@router.post("/{task_id}/start")
async def start(task_id: str, data: ActionBody, operator: CurrentOperator, db: WriteDB):
    task = await fulfillment.get_task(db, task_id)
    await fulfillment.start_task(
        db, task, actor_id=operator.id, actor_name=operator.username,
        expected_version=data.expected_version,
    )
    return _detail(await fulfillment.task_detail(db, task_id))


@router.post("/{task_id}/complete")
async def complete(task_id: str, data: ActionBody, operator: CurrentOperator, db: WriteDB):
    task = await fulfillment.get_task(db, task_id)
    await fulfillment.complete_task(
        db, task, actor_id=operator.id, actor_name=operator.username,
        expected_version=data.expected_version,
    )
    return _detail(await fulfillment.task_detail(db, task_id))


@router.post("/{task_id}/exception")
async def mark_exception(task_id: str, data: ReasonBody, operator: CurrentOperator, db: WriteDB):
    task = await fulfillment.get_task(db, task_id)
    await fulfillment.mark_exception(
        db, task, reason=data.reason, actor_id=operator.id, actor_name=operator.username,
        expected_version=data.expected_version,
    )
    return _detail(await fulfillment.task_detail(db, task_id))


@router.post("/{task_id}/recover")
async def recover(task_id: str, data: ActionBody, operator: CurrentOperator, db: WriteDB):
    task = await fulfillment.get_task(db, task_id)
    await fulfillment.recover_task(
        db, task, actor_id=operator.id, actor_name=operator.username,
        expected_version=data.expected_version,
    )
    return _detail(await fulfillment.task_detail(db, task_id))


@router.post("/{task_id}/cancel")
async def cancel(task_id: str, data: ReasonBody, operator: CurrentOperator, db: WriteDB):
    task = await fulfillment.get_task(db, task_id)
    await fulfillment.cancel_task(
        db, task, reason=data.reason, actor_id=operator.id, actor_name=operator.username,
        expected_version=data.expected_version,
    )
    return _detail(await fulfillment.task_detail(db, task_id))
