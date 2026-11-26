"""Order trading: create with stock reservation, mock payment, review, cancel and refund."""

import hmac
import json
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.order_models import (
    Order, OrderEvent, OrderItem, OrderPayment, OrderRefund, OrderSequence, OrderTraveler,
)
from app.db.models import User
from app.db.resource_models import OfferAllocation, PriceOffer, Product, Supplier
from app.db.support_models import Ticket
from app.config import settings
from app.services import demo_points, stock
from app.services.member_privacy import MemberPrivacy, mask_number, normalize_document

BEIJING = ZoneInfo("Asia/Shanghai")
PAYMENT_WINDOW = timedelta(minutes=settings.order_payment_window_minutes)
logger = logging.getLogger(__name__)


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
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    await db.execute(insert(OrderSequence).values(day=day, next_value=1).on_conflict_do_nothing())
    row = await db.get(OrderSequence, day, with_for_update=True)
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
            nights = (check_out - check_in).days
            if not 1 <= nights <= 30 or quantity > 5:
                raise HTTPException(422, "酒店需选择 1 至 30 晚、1 至 5 间。")
            for offset in range(nights):
                entries.append({
                    "product_id": entry["product_id"], "service_date": check_in + timedelta(days=offset),
                    "quantity": quantity, "kind": "hotel",
                    "stay": {"check_in": check_in.isoformat(), "check_out": check_out.isoformat()},
                })
        elif entry.get("kind") == "ticket" and quantity <= 20:
            entries.append({
                "product_id": entry["product_id"],
                "service_date": _day(entry["service_date"]),
                "quantity": quantity, "kind": "ticket",
            })
        else:
            raise HTTPException(422, "门票数量须在 1 至 20 张，当前仅支持房型和门票。")
    if not entries:
        raise HTTPException(422, "请至少选择一项商品。")
    if len({(row["product_id"], row["service_date"]) for row in entries}) != len(entries):
        raise HTTPException(422, "同一商品日期不能重复提交。")
    return entries


async def _price_entries(db: AsyncSession, entries: list[dict], today: date) -> list[dict]:
    priced: list[dict] = []
    issues = []
    products = {product_id: await db.get(Product, product_id, with_for_update=True, populate_existing=True)
                for product_id in sorted({entry["product_id"] for entry in entries})}
    suppliers = {supplier_id: await db.get(Supplier, supplier_id, with_for_update=True, populate_existing=True)
                 for supplier_id in sorted({product.supplier_id for product in products.values() if product})}
    for entry in sorted(entries, key=lambda row: (row["product_id"], row["service_date"])):
        service_date = entry["service_date"]
        if service_date < today:
            raise HTTPException(422, "服务日不能早于今天。")
        product = products[entry["product_id"]]
        if product and product.type != {"hotel": "hotel_room", "ticket": "attraction_ticket"}[entry["kind"]]:
            raise HTTPException(422, "所选品类与商品类型不一致。")
        supplier = suppliers.get(product.supplier_id) if product else None
        offer = await db.get(PriceOffer, (product.id, service_date), with_for_update=True,
                             populate_existing=True) if product else None
        if not product or not supplier or not offer:
            issues.append({"product_id": entry["product_id"], "service_date": service_date.isoformat(),
                           "reason": "unquoted" if product and supplier else "product_unavailable"})
            continue
        priced.append({**entry, "product": product, "supplier": supplier, "offer": offer})
    if issues:
        raise HTTPException(409, {"message": "部分项目已无法购买，请重新确认。", "items": issues})
    return priced


async def create_order(
    db: AsyncSession, *, user_id: str, trip_id: str | None, contact_name: str, contact_phone: str,
    travelers: list[dict], selected: list[dict], client_key: str, now: datetime | None = None,
    departure_date: date | None = None,
) -> Order:
    clock = now or now_utc()
    payload = json.dumps([trip_id, departure_date, contact_name, contact_phone, travelers, selected],
                         sort_keys=True, ensure_ascii=False, default=str).encode()
    fingerprint = hmac.digest(settings.jwt_secret_key.encode(), b"order-intent:" + payload, "sha256").hex()
    await db.get(User, user_id, with_for_update=True)
    existing = await db.scalar(select(Order).where(Order.user_id == user_id, Order.client_key == client_key))
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(409, "该提交标识已用于其他购买内容，请重新确认。")
        return existing
    if not travelers:
        raise HTTPException(422, "请至少填写一位出行人。")

    entries = _expand_items(selected)
    from app.services.checkout import itinerary_candidates, load_trip, validate_purchase

    today = clock.astimezone(BEIJING).date()
    trip = await load_trip(db, user_id, trip_id, lock=True)
    candidates = await itinerary_candidates(db, trip, departure_date, today, lock=True)
    if candidates[0] is None:
        raise HTTPException(422, "请选择出发日以查询价格和库存。")
    priced = await _price_entries(db, entries, today)
    departure_date = validate_purchase(trip, candidates, selected, priced, today)

    sequence = await _next_sequence(db, today)
    total_sale = sum(int(row["offer"].sale_fen) * row["quantity"] for row in priced)
    total_cost = sum(int(row["offer"].cost_fen) * row["quantity"] for row in priced)

    order = Order(
        order_no=_order_no(today, sequence), user_id=user_id, trip_id=trip_id, departure_date=departure_date,
        client_key=client_key, request_fingerprint=fingerprint, status="pending_payment", fund_status="unpaid",
        contact_name=contact_name, contact_phone=contact_phone,
        total_sale_fen=total_sale, total_cost_fen=total_cost,
        expires_at=clock + PAYMENT_WINDOW,
    )
    db.add(order)
    await db.flush()

    items = {}
    for index, row in enumerate(priced):
        product, offer = row["product"], row["offer"]
        item = OrderItem(
            order_id=order.id, product_id=product.id, supplier_id=product.supplier_id,
            product_name=product.name, product_type=product.type,
            attributes={**(product.attributes or {}), **({"stay": row["stay"]} if "stay" in row else {})},
            service_date=row["service_date"],
            quantity=row["quantity"], unit_sale_fen=offer.sale_fen,
            unit_cost_fen=offer.cost_fen,
            subtotal_sale_fen=offer.sale_fen * row["quantity"], sort=index,
        )
        db.add(item)
        items[(product.id, row["service_date"])] = item
    for index, traveler in enumerate(travelers):
        number = str(traveler.get("document_number") or "")
        ciphertext = None
        if number:
            normalized = normalize_document(number)
            try:
                ciphertext = MemberPrivacy().encrypt(normalized, context=f"order:{order.id}:traveler:{index}".encode())
            except Exception:
                raise HTTPException(503, "暂时无法安全保存证件，请稍后重试或清空选填证件号。") from None
        db.add(OrderTraveler(
            order_id=order.id, name=str(traveler.get("name", ""))[:50],
            document_type=str(traveler.get("document_type", ""))[:16],
            document_ciphertext=ciphertext,
            document_mask=mask_number(number) if number else "",
            phone_mask=mask_number(traveler["phone"]) if traveler.get("phone") else "",
            is_lead=bool(traveler.get("is_lead")) or index == 0,
        ))

    try:
        allocations = await stock.reserve(
            db, order.id,
            [(row["product_id"], row["service_date"], row["quantity"]) for row in priced],
            now=clock, ttl=PAYMENT_WINDOW,
        )
    except stock.StockUnavailable as error:
        raise HTTPException(409, error.detail()) from error
    for allocation in allocations:
        allocation.order_item_id = items[(allocation.product_id, allocation.service_date)].id

    await _event(db, order, "created", from_status=None, after={"total_sale_fen": total_sale})
    await db.flush()
    return order


async def get_order(db: AsyncSession, order_id: str, *, user_id: str | None = None, lock: bool = False) -> Order:
    order = await db.get(Order, order_id, with_for_update=lock, populate_existing=lock)
    if order is None or (user_id is not None and order.user_id != user_id):
        raise HTTPException(404, "订单不存在")
    return order


async def _frozen_entries(db, order_id):
    rows = (await db.execute(select(OrderItem.product_id, OrderItem.service_date, OrderItem.quantity)
                              .where(OrderItem.order_id == order_id))).all()
    if not rows:
        raise HTTPException(409, "订单缺少冻结商品明细，请人工核实库存。")
    return rows


class PaymentExpired(HTTPException):
    def __init__(self):
        super().__init__(409, {"message": "订单已超过支付时限。", "status": "cancelled"})


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
    if order.status != "pending_payment" or order.fund_status != "unpaid":
        raise HTTPException(409, {"message": "该订单当前不可支付。", "status": order.status})
    if clock >= _as_utc(order.expires_at):
        await expire_order(db, order, clock)
        raise PaymentExpired()
    try:
        await stock.protect_paid(db, order.id, await _frozen_entries(db, order.id))
    except stock.StockUnavailable as error:
        raise HTTPException(409, error.detail()) from error

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
    await demo_points.queue_event(db, order, "payment", payment.amount_fen, clock)
    await db.flush()
    return payment, True


async def approve_order(
    db: AsyncSession, order: Order, *, operator_id: str, operator_name: str, note: str = "",
    now: datetime | None = None,
) -> None:
    if order.status != "paid_pending_review":
        raise HTTPException(409, {"message": "只有待复核的订单可以通过。", "status": order.status})
    try:
        await stock.confirm(db, order.id, expected=await _frozen_entries(db, order.id))
    except stock.StockUnavailable as error:
        raise HTTPException(409, {
            "message": "预占与订单明细不符，请人工核实后处理。", "items": error.conflicts,
        }) from error
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
    if order.status == "cancelled":
        return await db.scalar(select(OrderRefund).where(OrderRefund.order_id == order.id))
    allowed = {"pending_payment", "paid_pending_review"}
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
    rejected_items=(), category: str = "other", now: datetime | None = None,
) -> OrderRefund:
    if order.status == "cancelled" and order.reviewed_at is not None and not order.confirmed_at:
        previous = await db.scalar(select(OrderRefund).where(OrderRefund.order_id == order.id))
        if previous is not None:
            return previous
    if order.status != "paid_pending_review":
        raise HTTPException(409, {"message": "只有待复核的订单可以拒绝。", "status": order.status})
    clock = now or now_utc()
    if category == "stockout":
        wanted = {(pid, day) for pid, day, _ in await _frozen_entries(db, order.id)}
        missing = {(row.product_id, row.service_date) for row in rejected_items}
        if not missing or not missing <= wanted:
            raise HTTPException(422, "请选择本单缺货的商品和服务日期。")
        # Lock every price row in the same order used by the release path.
        for product_id, day in sorted(wanted):
            offer = await db.get(PriceOffer, (product_id, day), with_for_update=True)
            if offer is not None and (product_id, day) in missing:
                offer.status = "stopped"
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
                 actor_id=operator_id, actor_name=operator_name, reason=reason,
                 after={"category": category, "items": [row.model_dump(mode="json") for row in rejected_items]})
    await db.flush()
    return refund


async def request_cancel(
    db: AsyncSession, order: Order, *, user_id: str, reason: str = "", now: datetime | None = None,
) -> None:
    if order.status == "cancel_requested" or (order.status == "cancelled" and order.cancel_requested_at):
        return
    if await _after_sales_ticket_id(db, order):
        return
    if order.status == "completed":
        await _after_sales(db, order, reason)
        return
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
    note: str, usage: str, now: datetime | None = None,
) -> OrderRefund | None:
    if order.status == "cancelled":
        return await db.scalar(select(OrderRefund).where(OrderRefund.order_id == order.id))
    if order.status == "confirmed" and await _after_sales_ticket_id(db, order):
        return None
    if order.status != "cancel_requested":
        raise HTTPException(409, {"message": "该订单没有待处理的取消申请。", "status": order.status})
    clock = now or now_utc()
    if usage != "unused":
        if usage == "used":
            await _after_sales(db, order, order.cancel_reason)
            order.status = "confirmed"
        order.version += 1
        await _event(db, order, "cancel_verification", from_status="cancel_requested",
                     actor_id=operator_id, actor_name=operator_name, reason=note, after={"usage": usage})
        return None
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


async def _after_sales(db, order, reason):
    from app.schemas.support import SubmitTicket
    from app.services.tickets import create_ticket

    if not await _after_sales_ticket_id(db, order):
        await create_ticket(db, order.user_id, SubmitTicket(
            category="inquiry", subject="订单退订售后", content=reason or "该订单已执行，申请售后处理。",
        ), order_id=order.id)


async def _after_sales_ticket_id(db, order):
    return await db.scalar(select(Ticket.id).where(
        Ticket.order_id == order.id, Ticket.submitter_id == order.user_id, Ticket.subject == "订单退订售后",
    ).limit(1))


async def expire_order(db, order, clock):
    if (order.status != "pending_payment" or order.fund_status != "unpaid"
            or _as_utc(order.expires_at) > clock):
        return False
    await stock.release(db, order.id, now=clock)
    order.status = "cancelled"
    order.cancelled_at = clock
    order.cancel_reason = "支付超时"
    order.version += 1
    await _event(db, order, "expired", from_status="pending_payment", reason="支付超时")
    return True


async def expire_due(db: AsyncSession, *, now: datetime | None = None, user_id=None, product_ids=None) -> int:
    """Close unpaid orders past their window and give the stock back."""
    clock = now or now_utc()
    criteria = [Order.status == "pending_payment", Order.fund_status == "unpaid", Order.expires_at <= clock]
    if user_id is not None:
        criteria.append(Order.user_id == user_id)
    if product_ids is not None:
        criteria.append(exists().where(OrderItem.order_id == Order.id, OrderItem.product_id.in_(product_ids)))
    expired = 0
    ready = (await db.scalars(select(Order).where(*criteria).order_by(Order.id).with_for_update())).all()
    price_keys = (await db.execute(select(OfferAllocation.product_id, OfferAllocation.service_date).where(
        OfferAllocation.order_id.in_([row.id for row in ready]), OfferAllocation.state == "reserved",
    ).distinct().order_by(OfferAllocation.product_id, OfferAllocation.service_date))).all() if ready else []
    for product_id, service_date in price_keys:
        await db.get(PriceOffer, (product_id, service_date), with_for_update=True)
    for order in ready:
        try:
            async with db.begin_nested():
                expired += int(await expire_order(db, order, clock))
        except stock.StockUnavailable:
            # Leave inconsistent historical orders intact for operational reconciliation.
            continue
    return expired


async def inventory_audit(db):
    """Read-only reconciliation for historic paid or confirmed lines."""
    active = ("paid_pending_review", "confirmed", "cancel_requested", "completed")
    statement = (select(Order.id, Order.status, OrderItem.product_id, OrderItem.service_date,
                        func.sum(OrderItem.quantity))
                 .join(OrderItem, Order.id == OrderItem.order_id).where(Order.status.in_(active))
                 .group_by(Order.id, Order.status, OrderItem.product_id, OrderItem.service_date))
    allocations = (await db.execute(
        select(OfferAllocation.order_id, OfferAllocation.product_id, OfferAllocation.service_date,
               OfferAllocation.state, OfferAllocation.quantity)
        .join(Order, Order.id == OfferAllocation.order_id).where(Order.status.in_(active))
    )).all()
    actual = {(order, product, day, state): count for order, product, day, state, count in allocations}
    gaps = []
    for key, status, product, day, expected in (await db.execute(statement)).all():
        state = "reserved" if status == "paid_pending_review" else "confirmed"
        count = actual.get((key, product, day, state), 0)
        if expected != count:
            gaps.append({"order_id": key, "status": status, "product_id": product, "service_date": day,
                         "expected": expected, "allocated": count})
    return {"items": gaps, "total": len(gaps)}


async def process_refunds(
    db: AsyncSession, *, now: datetime | None = None, fail: bool = False,
    order_id: str | None = None,
) -> int:
    """Mock refund processor; pass ``order_id`` to touch only that order."""
    clock = now or now_utc()
    filters = [OrderRefund.status.in_(("pending", "failed"))]
    if order_id:
        filters.append(OrderRefund.order_id == order_id)
    count = 0
    for refund_id, key in (await db.execute(select(OrderRefund.id, OrderRefund.order_id)
                                           .where(*filters).order_by(OrderRefund.order_id))).all():
        order = await db.get(Order, key, with_for_update=True, populate_existing=True)
        refund = await db.get(OrderRefund, refund_id, populate_existing=True)
        if refund.status not in {"pending", "failed"}:
            continue
        count += 1
        refund.attempts += 1
        if fail:
            refund.status = "failed"
            refund.last_error = "模拟退款通道暂时不可用"
            if order is not None:
                order.fund_status = "refund_failed"
            continue
        refund.status = "succeeded"
        refund.last_error = ""
        refund.processed_at = clock
        if order is not None:
            order.fund_status = "refunded"
            await demo_points.queue_event(db, order, "refund", refund.amount_fen, clock)
            await apply_demo_events(db, order.id)
    await db.flush()
    return count


async def apply_demo_events(db, order_id=None):
    try:
        async with db.begin_nested():
            await demo_points.apply_events(db, order_id)
    except SQLAlchemyError:
        logger.warning("模拟积分事件已保留，等待后台补偿", exc_info=True)


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
    ticket_id = await _after_sales_ticket_id(db, order)
    return {
        **order_summary(order, payments[0].paid_at if payments else None, clock),
        "user_id": order.user_id, "trip_id": order.trip_id, "departure_date": order.departure_date,
        "contact_name": order.contact_name, "contact_phone": order.contact_phone,
        "total_cost_fen": order.total_cost_fen,
        "review_note": order.review_note, "cancel_reason": order.cancel_reason,
        "cancelled_at": order.cancelled_at, "server_time": clock, "after_sales_ticket_id": ticket_id,
        "items": items, "travelers": travelers, "events": events,
        "payments": payments, "refunds": refunds,
    }


def order_summary(order, paid_at, clock):
    waiting = max(0, int((clock - _as_utc(paid_at)).total_seconds() // 60)) if (
        paid_at is not None and order.status == "paid_pending_review"
    ) else 0
    threshold = settings.order_review_alert_minutes
    return {
        "id": order.id, "order_no": order.order_no, "status": order.status, "fund_status": order.fund_status,
        "total_sale_fen": order.total_sale_fen, "expires_at": order.expires_at, "created_at": order.created_at,
        "waiting_minutes": waiting, "review_alert_minutes": threshold,
        "review_overdue": order.status == "paid_pending_review" and paid_at is not None and waiting >= threshold,
    }


async def list_orders(
    db: AsyncSession, *, user_id: str | None, status: str | None, keyword: str,
    offset: int, limit: int,
) -> tuple[list[dict], int]:
    filters = []
    if user_id:
        filters.append(Order.user_id == user_id)
    if status:
        filters.append(Order.status == status)
    if keyword.strip():
        filters.append(Order.order_no.icontains(keyword.strip(), autoescape=True))
    total = await db.scalar(select(func.count()).select_from(Order).where(*filters))
    statement = select(Order, OrderPayment.paid_at).outerjoin(OrderPayment, OrderPayment.order_id == Order.id)
    if not user_id:
        statement = statement.order_by(
            (Order.status == "paid_pending_review").desc(),
            OrderPayment.paid_at.asc().nulls_last(),
        )
    rows = (await db.execute(statement.where(*filters)
        .order_by(Order.created_at.desc(), Order.id).offset(offset).limit(limit))).all()
    clock = now_utc()
    return [order_summary(row, paid, clock) for row, paid in rows], total or 0

