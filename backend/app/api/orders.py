"""Tourist orders and the operator review queue."""

import logging

from fastapi import APIRouter, Depends, Header, Query

from app.api.deps import CurrentAccount, CurrentOperator, DbSession as DB, WriteDbSession as WriteDB
from app.api.support import Page, no_store
from app.db import database
from app.db.order_models import Order
from app.schemas.orders import (
    CancelOrder, CreateOrder, OrderDetail, OrderPage, OrderStatus, OrderSummary, PayOrder,
    RejectDecision, ResolveCancelRequest, ReviewDecision, SweepResult,
)
from app.services import orders
from app.services.member_points import record_payment, record_refund

logger = logging.getLogger(__name__)

tourist_router = APIRouter(prefix="/v1/orders", dependencies=[Depends(no_store)])
admin_router = APIRouter(prefix="/orders", dependencies=[Depends(no_store)])


async def _award_mock_points(order, payment) -> None:
    """Mock points run after the order commits so a failure cannot undo the payment."""
    try:
        await record_payment(
            database.async_session, order_id=order.id, member_id=order.user_id,
            amount_fen=payment.amount_fen, paid_at=payment.paid_at,
            event_id=f"mock-{payment.id}",
        )
    except Exception:
        logger.warning("模拟积分入账失败，订单 %s 可手动重试", order.order_no, exc_info=True)


async def _return_mock_points(order, refund) -> None:
    try:
        await record_refund(
            database.async_session, order_id=order.id, refund_id=f"mock-{refund.id}",
            amount_fen=refund.amount_fen, refunded_at=orders.as_utc(refund.processed_at) if refund.processed_at else orders.now_utc(),
        )
    except Exception:
        logger.warning("模拟积分冲回失败，订单 %s", order.order_no, exc_info=True)


# ── 游客端 ────────────────────────────────────────────────────


@tourist_router.get("", response_model=OrderPage)
async def my_orders(account: CurrentAccount, db: DB, page: Page,
                    status: OrderStatus | None = None):
    rows, total = await orders.list_orders(
        db, user_id=account.id, status=status, keyword="",
        offset=page.offset, limit=page.limit,
    )
    return OrderPage(items=[await _summary(db, row) for row in rows], total=total)


async def _summary(db, order) -> dict:
    detail = await orders.order_detail(db, order)
    detail.pop("items", None)
    detail.pop("travelers", None)
    detail.pop("events", None)
    detail.pop("payments", None)
    detail.pop("refunds", None)
    detail.pop("user_id", None)
    detail.pop("contact_name", None)
    detail.pop("contact_phone", None)
    detail.pop("total_cost_fen", None)
    detail.pop("review_note", None)
    detail.pop("cancel_reason", None)
    detail.pop("cancelled_at", None)
    detail.pop("trip_id", None)
    return detail


@tourist_router.post("", response_model=OrderDetail, status_code=201)
async def create_order(
    data: CreateOrder, account: CurrentAccount, db: WriteDB,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    order = await orders.create_order(
        db, user_id=account.id, trip_id=data.trip_id,
        contact_name=data.contact_name, contact_phone=data.contact_phone,
        travelers=[traveler.model_dump() for traveler in data.travelers],
        selected=[item.model_dump() for item in data.selected],
        client_key=idempotency_key,
    )
    return await orders.order_detail(db, order)


@tourist_router.get("/{order_id}", response_model=OrderDetail)
async def my_order(order_id: str, account: CurrentAccount, db: DB):
    order = await orders.get_order(db, order_id, user_id=account.id)
    return await orders.order_detail(db, order)


@tourist_router.post("/{order_id}/payments", response_model=OrderDetail)
async def pay_order(order_id: str, data: PayOrder, account: CurrentAccount, db: WriteDB):
    order = await orders.get_order(db, order_id, user_id=account.id)
    payment, newly_paid = await orders.pay_order(db, order, idempotency_key=data.idempotency_key)
    await db.commit()
    if newly_paid:
        await _award_mock_points(order, payment)
    return await orders.order_detail(db, order)


@tourist_router.post("/{order_id}/cancel", response_model=OrderDetail)
async def cancel_order(order_id: str, data: CancelOrder, account: CurrentAccount, db: WriteDB):
    order = await orders.get_order(db, order_id, user_id=account.id)
    refund = await orders.cancel_order(
        db, order, actor_id=account.id, actor_name=account.username,
        reason=data.reason or "游客取消",
    )
    await db.commit()
    if refund is not None:
        await _process_single_refund(order, refund)
    order = await _reload(db, order)
    return await orders.order_detail(db, order)


@tourist_router.post("/{order_id}/cancel-request", response_model=OrderDetail)
async def request_cancel(order_id: str, data: CancelOrder, account: CurrentAccount, db: WriteDB):
    order = await orders.get_order(db, order_id, user_id=account.id)
    await orders.request_cancel(db, order, user_id=account.id, reason=data.reason)
    return await orders.order_detail(db, order)


# ── 运营端 ────────────────────────────────────────────────────


@admin_router.get("", response_model=OrderPage)
async def review_queue(
    db: DB, page: Page, status: OrderStatus | None = None,
    keyword: str = Query("", max_length=32),
):
    rows, total = await orders.list_orders(
        db, user_id=None, status=status, keyword=keyword,
        offset=page.offset, limit=page.limit,
    )
    return OrderPage(items=[await _summary(db, row) for row in rows], total=total)


@admin_router.get("/{order_id}", response_model=OrderDetail)
async def admin_order(order_id: str, db: DB):
    order = await orders.get_order(db, order_id)
    return await orders.order_detail(db, order)


@admin_router.post("/{order_id}/approve", response_model=OrderDetail)
async def approve(order_id: str, data: ReviewDecision, operator: CurrentOperator, db: WriteDB):
    order = await orders.get_order(db, order_id)
    await orders.approve_order(
        db, order, operator_id=operator.id, operator_name=operator.username, note=data.note,
    )
    return await orders.order_detail(db, order)


@admin_router.post("/{order_id}/reject", response_model=OrderDetail)
async def reject(order_id: str, data: RejectDecision, operator: CurrentOperator, db: WriteDB):
    order = await orders.get_order(db, order_id)
    refund = await orders.reject_order(
        db, order, operator_id=operator.id, operator_name=operator.username, reason=data.reason,
    )
    await db.commit()
    await _process_single_refund(order, refund)
    order = await _reload(db, order)
    return await orders.order_detail(db, order)


@admin_router.post("/{order_id}/cancel-request", response_model=OrderDetail)
async def resolve_cancel(
    order_id: str, data: ResolveCancelRequest, operator: CurrentOperator, db: WriteDB,
):
    order = await orders.get_order(db, order_id)
    refund = await orders.resolve_cancel_request(
        db, order, operator_id=operator.id, operator_name=operator.username,
        approve=data.approve, note=data.note,
    )
    await db.commit()
    if refund is not None:
        await _process_single_refund(order, refund)
    order = await _reload(db, order)
    return await orders.order_detail(db, order)


@admin_router.post("/sweep", response_model=SweepResult)
async def sweep(db: WriteDB):
    """Close expired unpaid orders and push pending mock refunds."""
    expired = await orders.expire_due(db)
    refunds = await orders.process_refunds(db)
    return SweepResult(expired=expired, refunds=refunds)


async def _reload(db, order):
    """Re-read the order after the refund processor touched it in another session."""
    order_id = order.id
    db.expunge_all()
    return await db.get(Order, order_id)


async def _process_single_refund(order, refund) -> None:
    """Run the mock refund processor for one order, then mirror it into points."""
    if refund.status != "pending":
        return
    try:
        async with database.async_session() as session:
            await orders.process_refunds(session, order_id=order.id)
            await session.commit()
            refreshed = await session.get(type(refund), refund.id)
            succeeded = refreshed is not None and refreshed.status == "succeeded"
            processed_at = refreshed.processed_at if refreshed else None
    except Exception:
        logger.warning("模拟退款处理失败，订单 %s", order.order_no, exc_info=True)
        return
    if succeeded:
        refund.status, refund.processed_at = "succeeded", processed_at
        await _return_mock_points(order, refund)




