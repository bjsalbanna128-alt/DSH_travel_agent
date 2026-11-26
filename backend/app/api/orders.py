"""Tourist checkout and the operator review queue."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.api.deps import CurrentAccount, CurrentOperator, DbSession as DB, WriteDbSession as WriteDB
from app.api.support import Page, no_store, require_tourist
from app.db.database import reserve_write
from app.schemas.orders import (
    AdminOrderPage, CancelOrder, CreateOrder, OrderDetail, OrderPage, OrderStatus, PayOrder,
    RejectDecision, ResolveCancelRequest, ReviewDecision, SweepResult, TouristOrderDetail,
)
from app.services import orders
from app.services import fulfillment

class OrderInputRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def sanitized(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                issues = [{"loc": issue["loc"] if issue["type"] != "extra_forbidden" else ("body",),
                           "msg": issue["msg"]} for issue in error.errors()]
                raise HTTPException(422, issues) from None
        return sanitized


tourist_router = APIRouter(prefix="/v1/orders", dependencies=[Depends(no_store), Depends(require_tourist)],
                           route_class=OrderInputRoute)
admin_router = APIRouter(prefix="/orders", dependencies=[Depends(no_store)])


@tourist_router.get("", response_model=OrderPage)
async def my_orders(account: CurrentAccount, db: WriteDB, page: Page, status: OrderStatus | None = None):
    await orders.expire_due(db, user_id=account.id)
    rows, total = await orders.list_orders(db, user_id=account.id, status=status, keyword="",
                                          offset=page.offset, limit=page.limit)
    return {"items": rows, "total": total}


@tourist_router.post("", response_model=TouristOrderDetail, status_code=201)
async def create_order(
    data: CreateOrder, account: CurrentAccount, db: WriteDB,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")],
):
    # Reclaim independently so a stale quote or failed checkout cannot undo an expiry.
    await orders.expire_due(db, product_ids={item.product_id for item in data.selected})
    await db.commit()
    await reserve_write(db)
    order = await orders.create_order(
        db, user_id=account.id, trip_id=data.trip_id, departure_date=data.departure_date,
        contact_name=data.contact_name, contact_phone=data.contact_phone,
        travelers=[traveler.model_dump() for traveler in data.travelers],
        selected=[item.model_dump() for item in data.selected], client_key=idempotency_key,
    )
    return await orders.order_detail(db, order)


@tourist_router.get("/{order_id}", response_model=TouristOrderDetail)
async def my_order(order_id: str, account: CurrentAccount, db: WriteDB):
    order = await orders.get_order(db, order_id, user_id=account.id, lock=True)
    await orders.expire_order(db, order, orders.now_utc())
    return await orders.order_detail(db, order)


@tourist_router.post("/{order_id}/payments", response_model=TouristOrderDetail)
async def pay_order(order_id: str, data: PayOrder, account: CurrentAccount, db: WriteDB):
    order = await orders.get_order(db, order_id, user_id=account.id, lock=True)
    try:
        await orders.pay_order(db, order, idempotency_key=data.idempotency_key)
    except orders.PaymentExpired:
        await db.commit()
        raise
    await orders.apply_demo_events(db, order.id)
    return await orders.order_detail(db, order)


@tourist_router.post("/{order_id}/cancel", response_model=TouristOrderDetail)
async def cancel_order(order_id: str, data: CancelOrder, account: CurrentAccount, db: WriteDB):
    order = await orders.get_order(db, order_id, user_id=account.id, lock=True)
    if await orders.cancel_order(db, order, actor_id=account.id, actor_name=account.username,
                                 reason=data.reason or "游客取消"):
        await orders.process_refunds(db, order_id=order.id)
    return await orders.order_detail(db, order)


@tourist_router.post("/{order_id}/cancel-request", response_model=TouristOrderDetail)
async def request_cancel(order_id: str, data: CancelOrder, account: CurrentAccount, db: WriteDB):
    order = await orders.get_order(db, order_id, user_id=account.id, lock=True)
    await orders.request_cancel(db, order, user_id=account.id, reason=data.reason)
    return await orders.order_detail(db, order)


@admin_router.get("", response_model=AdminOrderPage)
async def review_queue(db: DB, page: Page, status: OrderStatus | None = None, keyword: str = Query("", max_length=32)):
    rows, total = await orders.list_orders(db, user_id=None, status=status, keyword=keyword,
                                          offset=page.offset, limit=page.limit)
    return {"items": rows, "total": total}


@admin_router.post("/sweep", response_model=SweepResult)
async def sweep(db: WriteDB):
    expired = await orders.expire_due(db)
    refunds = await orders.process_refunds(db)
    await orders.apply_demo_events(db)
    return SweepResult(expired=expired, refunds=refunds)


@admin_router.get("/inventory-audit")
async def audit_inventory(db: DB):
    return await orders.inventory_audit(db)


@admin_router.get("/{order_id}", response_model=OrderDetail)
async def admin_order(order_id: str, db: DB):
    return await orders.order_detail(db, await orders.get_order(db, order_id))


@admin_router.post("/{order_id}/approve", response_model=OrderDetail)
async def approve(order_id: str, data: ReviewDecision, operator: CurrentOperator, db: WriteDB):
    order = await orders.get_order(db, order_id, lock=True)
    await orders.approve_order(db, order, operator_id=operator.id, operator_name=operator.username, note=data.note)
    return await orders.order_detail(db, order)


@admin_router.post("/{order_id}/reject", response_model=OrderDetail)
async def reject(order_id: str, data: RejectDecision, operator: CurrentOperator, db: WriteDB):
    order = await orders.get_order(db, order_id, lock=True)
    await orders.reject_order(db, order, operator_id=operator.id, operator_name=operator.username,
                              reason=data.reason, category=data.category, rejected_items=data.items)
    await orders.process_refunds(db, order_id=order.id)
    return await orders.order_detail(db, order)


@admin_router.post("/{order_id}/cancel-request", response_model=OrderDetail)
async def resolve_cancel(order_id: str, data: ResolveCancelRequest, operator: CurrentOperator, db: WriteDB):
    order = await orders.get_order(db, order_id, lock=True)
    if await orders.resolve_cancel_request(db, order, operator_id=operator.id, operator_name=operator.username,
                                          approve=data.approve, note=data.note, usage=data.usage):
        await orders.process_refunds(db, order_id=order.id)
    return await orders.order_detail(db, order)

