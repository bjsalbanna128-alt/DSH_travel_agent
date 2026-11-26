"""Order trading: create with stock reservation, mock payment, review, cancel and refund."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.order_models import (
    Order, OrderEvent, OrderItem, OrderPayment, OrderRefund, OrderSequence, OrderTraveler,
)
from app.db.resource_models import PriceOffer, Product, Supplier
from app.config import settings
from app.services import stock
from app.services.member_privacy import mask_number

BEIJING = ZoneInfo("Asia/Shanghai")
PAYMENT_WINDOW = timedelta(minutes=settings.order_payment_window_minutes)
REVIEW_ALERT_MINUTES = settings.order_review_alert_minutes


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


_as_utc = as_utc


def _today() -> date:
    return now_utc().astimezone(BEIJING).date()


def _order_no(year_day: date, sequence: int) -> str:
    return f"ZY{year_day.strftime('%Y%m%d')}{sequence:04d}"


async def _next_sequence(db: AsyncSession, day: date) -> int:
    row = await db.get(OrderSequence, day, with_for_update=True)
    if row is None:
        row = OrderSequence(day=day, next_value=1)
        db.add(row)
        await db.flush()
    value = row.next_value
    if value > 9999:
        raise HTTPException(409, "当日订单号已用尽，请次日再试。")
    row.next_value = value + 1
    await db.flush()
    return value


async def _event(
    db: AsyncSession, order: Order, kind: str, *, from_status: str | None,
    actor_id: str | None = None, actor_name: str | None = None, reason: str = "",
    before: dict | None = None, after: dict | None = None,
) -> None:
    db.add(OrderEvent(
        order_id=order.id, kind=kind, from_status=from_status, to_status=order.status,
        before=before, after=after, actor_id=actor_id, actor_name=actor_name, reason=reason,
    ))


def _day(value) -> date:
    """Accept a date or an ISO string; pydantic already coerces most callers."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _expand_items(selected: list[dict]) -> list[dict]:
    """Hotel ranges become one entry per night; tickets stay as one dated entry."""
    entries: list[dict] = []
    for entry in selected:
        quantity = int(entry.get("quantity") or 0)
        if quantity <= 0:
            raise HTTPException(422, "购买数量必须大于 0。")
        if entry.get("kind") == "hotel":
            check_in = _day(entry["check_in"])
            check_out = _day(entry["check_out"])
            if check_out <= check_in:
                raise HTTPException(422, "退房日必须晚于入住日。")
            nights = (check_out - check_in).days
            for offset in range(nights):
                entries.append({
                    "product_id": entry["product_id"], "service_date": check_in + timedelta(days=offset),
                    "quantity": quantity,
                })
        else:
            entries.append({
                "product_id": entry["product_id"],
                "service_date": _day(entry["service_date"]),
                "quantity": quantity,
            })
    if not entries:
        raise HTTPException(422, "请至少选择一项商品。")
    return entries


async def _price_entries(db: AsyncSession, entries: list[dict]) -> list[dict]:
    priced: list[dict] = []
    for entry in entries:
        service_date = entry["service_date"]
        if service_date < _today():
            raise HTTPException(422, "服务日不能早于今天。")
        row = (await db.execute(
            select(Product, Supplier, PriceOffer)
            .join(Supplier, Supplier.id == Product.supplier_id)
            .join(PriceOffer, PriceOffer.product_id == Product.id)
            .where(
                Product.id == entry["product_id"],
                PriceOffer.service_date == service_date,
            )
        )).one_or_none()
        if row is None:
            raise HTTPException(409, {"message": "所选商品在该日期没有报价。",
                                      "product_id": entry["product_id"],
                                      "service_date": service_date.isoformat()})
        product, supplier, offer = row
        if product.status != "on_shelf" or supplier.status != "active":
            raise HTTPException(409, {"message": "该商品当前不可售。", "product_id": product.id})
        if offer.status != "available" or offer.total_quantity is None:
            raise HTTPException(409, {"message": "该日期不可售或库存未核定。",
                                      "product_id": product.id,
                                      "service_date": service_date.isoformat()})
        priced.append({**entry, "product": product, "supplier": supplier, "offer": offer})
    return priced


async def create_order(
    db: AsyncSession, *, user_id: str, trip_id: str | None, contact_name: str, contact_phone: str,
    travelers: list[dict], selected: list[dict], client_key: str | None, now: datetime | None = None,
) -> Order:
    clock = now or now_utc()
    if client_key:
        existing = await db.scalar(select(Order).where(
            Order.user_id == user_id, Order.client_key == client_key,
        ))
        if existing is not None:
            return existing
    if not travelers:
        raise HTTPException(422, "请至少填写一位出行人。")

    entries = _expand_items(selected)
    priced = await _price_entries(db, entries)

    sequence = await _next_sequence(db, _today())
    total_sale = sum(int(row["offer"].sale_fen) * row["quantity"] for row in priced)
    total_cost = sum(int(row["offer"].cost_fen) * row["quantity"] for row in priced)

    order = Order(
        order_no=_order_no(_today(), sequence), user_id=user_id, trip_id=trip_id,
        client_key=client_key, status="pending_payment", fund_status="unpaid",
        contact_name=contact_name, contact_phone=contact_phone,
        total_sale_fen=total_sale, total_cost_fen=total_cost,
        expires_at=clock + PAYMENT_WINDOW,
    )
    db.add(order)
    await db.flush()

    for index, row in enumerate(priced):
        product, offer = row["product"], row["offer"]
        db.add(OrderItem(
            order_id=order.id, product_id=product.id, supplier_id=product.supplier_id,
            product_name=product.name, product_type=product.type,
            attributes=product.attributes or {}, service_date=row["service_date"],
            quantity=row["quantity"], unit_sale_fen=offer.sale_fen,
            unit_cost_fen=offer.cost_fen,
            subtotal_sale_fen=offer.sale_fen * row["quantity"], sort=index,
        ))
    for index, traveler in enumerate(travelers):
        number = str(traveler.get("document_number") or "")
        ciphertext = None
        if number:
            try:
                from app.services.member_privacy import MemberPrivacy, normalize_document

                ciphertext = MemberPrivacy().encrypt(
                    normalize_document(number), context=f"order:{order.id}:traveler:{index}".encode(),
                )
            except Exception:  # 未配置加密密钥时只保留掩码，敏感明文不落库
                ciphertext = None
        db.add(OrderTraveler(
            order_id=order.id, name=str(traveler.get("name", ""))[:50],
            document_type=str(traveler.get("document_type", ""))[:16],
            document_ciphertext=ciphertext,
            document_mask=mask_number(number) if number else "",
            phone_mask=mask_number(traveler["phone"]) if traveler.get("phone") else "",
            is_lead=bool(traveler.get("is_lead")) or index == 0,
        ))

    try:
        await stock.reserve(
            db, order.id,
            [(row["product_id"], row["service_date"], row["quantity"]) for row in priced],
            now=clock, ttl=PAYMENT_WINDOW,
        )
    except stock.StockUnavailable as error:
        raise HTTPException(409, error.detail()) from error

    await _event(db, order, "created", from_status=None, after={"total_sale_fen": total_sale})
    await db.flush()
    return order


async def get_order(db: AsyncSession, order_id: str, *, user_id: str | None = None) -> Order:
    order = await db.get(Order, order_id)
    if order is None or (user_id is not None and order.user_id != user_id):
        raise HTTPException(404, "订单不存在")
    return order


async def pay_order(
    db: AsyncSession, order: Order, *, idempotency_key: str, now: datetime | None = None,
) -> tuple[OrderPayment, bool]:
    """Mock payment. Returns (payment, newly_paid)."""
    clock = now or now_utc()
    existing = await db.scalar(select(OrderPayment).where(
        OrderPayment.order_id == order.id,
        OrderPayment.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        return existing, False
    if order.fund_status == "paid":
        existing = await db.scalar(select(OrderPayment).where(OrderPayment.order_id == order.id))
        if existing is not None:
            return existing, False
    if order.status != "pending_payment":
        raise HTTPException(409, {"message": "该订单当前不可支付。", "status": order.status})
    if clock >= _as_utc(order.expires_at):
        raise HTTPException(409, {"message": "订单已超过支付时限。", "status": order.status})

    payment = OrderPayment(
        order_id=order.id, provider="mock", amount_fen=order.total_sale_fen,
        event_id=f"mock-{order.id}-{idempotency_key[:32]}", idempotency_key=idempotency_key,
        paid_at=clock,
    )
    db.add(payment)
    order.status = "paid_pending_review"
    order.fund_status = "paid"
    order.version += 1
    await _event(db, order, "paid", from_status="pending_payment",
                 after={"amount_fen": order.total_sale_fen, "provider": "mock"})
    await db.flush()
    return payment, True


async def approve_order(
    db: AsyncSession, order: Order, *, operator_id: str, operator_name: str, note: str = "",
    now: datetime | None = None,
) -> None:
    if order.status != "paid_pending_review":
        raise HTTPException(409, {"message": "只有待复核的订单可以通过。", "status": order.status})
    await stock.confirm(db, order.id, now=now)
    order.status = "confirmed"
    order.confirmed_at = now or now_utc()
    order.reviewed_by = operator_id
    order.reviewed_by_name = operator_name
    order.reviewed_at = order.confirmed_at
    order.review_note = note
    order.version += 1
    await _event(db, order, "confirmed", from_status="paid_pending_review",
                 actor_id=operator_id, actor_name=operator_name, reason=note)
    await db.flush()


async def _start_refund(
    db: AsyncSession, order: Order, *, reason: str, now: datetime,
) -> OrderRefund:
    existing = await db.scalar(select(OrderRefund).where(OrderRefund.order_id == order.id))
    if existing is not None:
        return existing
    refund = OrderRefund(
        order_id=order.id, refund_no=f"RF{order.order_no}", amount_fen=order.total_sale_fen,
        status="pending", reason=reason,
    )
    db.add(refund)
    order.fund_status = "refunding"
    await db.flush()
    return refund


async def cancel_order(
    db: AsyncSession, order: Order, *, actor_id: str | None, actor_name: str | None, reason: str,
    now: datetime | None = None,
) -> OrderRefund | None:
    clock = now or now_utc()
    allowed = {"pending_payment", "paid_pending_review", "cancel_requested"}
    if order.status not in allowed:
        raise HTTPException(409, {"message": "该订单当前不能取消。", "status": order.status})

    was_paid = order.fund_status in ("paid", "refunding")
    from_status = order.status
    order.status = "cancelled"
    order.cancelled_at = clock
    order.cancel_reason = reason
    order.version += 1

    if from_status == "paid_pending_review" or was_paid:
        await stock.release_confirmed(db, order.id, now=clock)
    await stock.release(db, order.id, now=clock)

    refund = await _start_refund(db, order, reason=reason, now=clock) if was_paid else None
    await _event(db, order, "cancelled", from_status=from_status, actor_id=actor_id,
                 actor_name=actor_name, reason=reason)
    await db.flush()
    return refund


async def reject_order(
    db: AsyncSession, order: Order, *, operator_id: str, operator_name: str, reason: str,
    now: datetime | None = None,
) -> OrderRefund:
    if order.status != "paid_pending_review":
        raise HTTPException(409, {"message": "只有待复核的订单可以拒绝。", "status": order.status})
    clock = now or now_utc()
    order.status = "cancelled"
    order.cancelled_at = clock
    order.cancel_reason = reason
    order.reviewed_by = operator_id
    order.reviewed_by_name = operator_name
    order.reviewed_at = clock
    order.review_note = reason
    order.version += 1
    await stock.release(db, order.id, now=clock)
    refund = await _start_refund(db, order, reason=reason, now=clock)
    await _event(db, order, "rejected", from_status="paid_pending_review",
                 actor_id=operator_id, actor_name=operator_name, reason=reason)
    await db.flush()
    return refund


async def request_cancel(
    db: AsyncSession, order: Order, *, user_id: str, reason: str = "", now: datetime | None = None,
) -> None:
    if order.status != "confirmed":
        raise HTTPException(409, {"message": "只有已确认的订单可以申请取消。", "status": order.status})
    order.status = "cancel_requested"
    order.cancel_requested_at = now or now_utc()
    order.cancel_reason = reason
    order.version += 1
    await _event(db, order, "cancel_requested", from_status="confirmed",
                 actor_id=user_id, reason=reason)
    await db.flush()


async def resolve_cancel_request(
    db: AsyncSession, order: Order, *, operator_id: str, operator_name: str, approve: bool,
    note: str = "", now: datetime | None = None,
) -> OrderRefund | None:
    if order.status != "cancel_requested":
        raise HTTPException(409, {"message": "该订单没有待处理的取消申请。", "status": order.status})
    clock = now or now_utc()
    if not approve:
        order.status = "confirmed"
        order.version += 1
        await _event(db, order, "cancel_declined", from_status="cancel_requested",
                     actor_id=operator_id, actor_name=operator_name, reason=note)
        await db.flush()
        return None
    order.status = "cancelled"
    order.cancelled_at = clock
    order.version += 1
    await stock.release_confirmed(db, order.id, now=clock)
    refund = await _start_refund(db, order, reason=note or order.cancel_reason, now=clock)
    await _event(db, order, "cancelled", from_status="cancel_requested",
                 actor_id=operator_id, actor_name=operator_name, reason=note)
    await db.flush()
    return refund


async def expire_due(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Close unpaid orders past their window and give the stock back."""
    clock = now or now_utc()
    orders = (await db.scalars(select(Order).where(
        Order.status == "pending_payment", Order.expires_at <= clock,
    ))).all()
    for order in orders:
        order.status = "cancelled"
        order.cancelled_at = clock
        order.cancel_reason = "支付超时"
        order.version += 1
        await stock.release(db, order.id, now=clock)
        await _event(db, order, "expired", from_status="pending_payment", reason="支付超时")
    await db.flush()
    return len(orders)


async def process_refunds(
    db: AsyncSession, *, now: datetime | None = None, fail: bool = False,
    order_id: str | None = None,
) -> int:
    """Mock refund processor; pass ``order_id`` to touch only that order."""
    clock = now or now_utc()
    filters = [OrderRefund.status.in_(("pending", "failed"))]
    if order_id:
        filters.append(OrderRefund.order_id == order_id)
    refunds = (await db.scalars(select(OrderRefund).where(*filters))).all()
    for refund in refunds:
        refund.attempts += 1
        if fail:
            refund.status = "failed"
            refund.last_error = "模拟退款通道暂时不可用"
            order = await db.get(Order, refund.order_id)
            if order is not None:
                order.fund_status = "refund_failed"
            continue
        refund.status = "succeeded"
        refund.last_error = ""
        refund.processed_at = clock
        order = await db.get(Order, refund.order_id)
        if order is not None:
            order.fund_status = "refunded"
    await db.flush()
    return len(refunds)


async def order_detail(db: AsyncSession, order: Order, *, now: datetime | None = None) -> dict:
    """Assemble the read model shared by both ends."""
    clock = now or now_utc()
    items = (await db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)
                              .order_by(OrderItem.sort))).all()
    travelers = (await db.scalars(select(OrderTraveler).where(OrderTraveler.order_id == order.id))).all()
    events = (await db.scalars(select(OrderEvent).where(OrderEvent.order_id == order.id)
                               .order_by(OrderEvent.created_at))).all()
    payments = (await db.scalars(select(OrderPayment).where(OrderPayment.order_id == order.id))).all()
    refunds = (await db.scalars(select(OrderRefund).where(OrderRefund.order_id == order.id))).all()
    waiting = 0
    if order.status == "paid_pending_review":
        since = _as_utc(order.reviewed_at or order.created_at)
        waiting = max(0, int((clock - since).total_seconds() // 60))
    return {
        "id": order.id, "order_no": order.order_no, "user_id": order.user_id,
        "status": order.status, "fund_status": order.fund_status, "trip_id": order.trip_id,
        "contact_name": order.contact_name, "contact_phone": order.contact_phone,
        "total_sale_fen": order.total_sale_fen, "total_cost_fen": order.total_cost_fen,
        "expires_at": order.expires_at, "created_at": order.created_at,
        "review_note": order.review_note, "cancel_reason": order.cancel_reason,
        "cancelled_at": order.cancelled_at, "waiting_minutes": waiting,
        "review_alert_minutes": REVIEW_ALERT_MINUTES,
        "review_overdue": waiting >= REVIEW_ALERT_MINUTES,
        "items": items, "travelers": travelers, "events": events,
        "payments": payments, "refunds": refunds,
    }


async def list_orders(
    db: AsyncSession, *, user_id: str | None, status: str | None, keyword: str,
    offset: int, limit: int,
) -> tuple[list[Order], int]:
    filters = []
    if user_id:
        filters.append(Order.user_id == user_id)
    if status:
        filters.append(Order.status == status)
    if keyword.strip():
        filters.append(Order.order_no.icontains(keyword.strip(), autoescape=True))
    total = await db.scalar(select(func.count()).select_from(Order).where(*filters))
    rows = (await db.scalars(
        select(Order).where(*filters).order_by(Order.created_at.desc()).offset(offset).limit(limit)
    )).all()
    return rows, total or 0

