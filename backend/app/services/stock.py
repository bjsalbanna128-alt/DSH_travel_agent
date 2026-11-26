"""Stock reservation, confirmation and release for sellable offers.

口径见 `backend/specs/features/2026-11-26-履约模块前置修改`：
报价保存总投放、预占、确认占用三个数量，剩余 = 总投放 − 预占 − 确认占用。
未设置总投放的报价视为库存未核实，不参与任何占用。
"""

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.resource_models import OfferAllocation, PriceOffer

RESERVATION_TTL = timedelta(minutes=15)
MAX_QUANTITY = 1_000_000

Entry = tuple[str, date, int]  # (product_id, service_date, quantity)


class StockUnavailable(Exception):
    """Raised when one or more entries cannot be reserved."""

    def __init__(self, conflicts: list[dict]):
        super().__init__("库存不足或不可售")
        self.conflicts = conflicts

    def detail(self) -> dict:
        return {"message": "部分项目库存不足或不可售，请调整后重试。", "items": self.conflicts}


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def remaining(offer: PriceOffer) -> int | None:
    if offer.total_quantity is None:
        return None
    return offer.total_quantity - offer.reserved_quantity - offer.confirmed_quantity


def merge_entries(entries: Iterable[Entry]) -> list[Entry]:
    """Merge repeated product/day pairs so one lock covers the whole order."""
    merged: dict[tuple[str, date], int] = {}
    for product_id, service_date, quantity in entries:
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise ValueError("预占数量必须是正整数")
        if quantity > MAX_QUANTITY:
            raise ValueError("预占数量超出上限")
        merged[(product_id, service_date)] = merged.get((product_id, service_date), 0) + quantity
    if not merged:
        raise ValueError("没有需要预占的项目")
    return [(product_id, service_date, quantity) for (product_id, service_date), quantity in sorted(merged.items())]


async def _release_one(db: AsyncSession, allocation: OfferAllocation) -> None:
    result = await db.execute(
        update(PriceOffer)
        .where(
            PriceOffer.product_id == allocation.product_id,
            PriceOffer.service_date == allocation.service_date,
            PriceOffer.reserved_quantity >= allocation.quantity,
        )
        .values(reserved_quantity=PriceOffer.reserved_quantity - allocation.quantity)
    )
    if result.rowcount != 1:
        raise StockUnavailable([_missing(allocation.product_id, allocation.service_date)])
    allocation.state = "released"
    allocation.expires_at = None


async def reserve(
    db: AsyncSession, order_id: str, entries: Iterable[Entry], *,
    now: datetime | None = None, ttl: timedelta = RESERVATION_TTL,
) -> list[OfferAllocation]:
    """Atomically reserve stock for an order. Raises StockUnavailable on any conflict."""
    clock = _now(now)
    merged = merge_entries(entries)
    conflicts: list[dict] = []

    for product_id, service_date, quantity in merged:
        offer = await db.scalar(select(PriceOffer).where(
            PriceOffer.product_id == product_id, PriceOffer.service_date == service_date,
        ).with_for_update().execution_options(populate_existing=True))
        if offer is None:
            conflicts.append({"product_id": product_id, "service_date": service_date.isoformat(),
                              "reason": "unquoted"})
            continue
        if offer.status != "available":
            conflicts.append({"product_id": product_id, "service_date": service_date.isoformat(),
                              "reason": "offer_stopped"})
            continue
        if offer.total_quantity is None:
            conflicts.append({"product_id": product_id, "service_date": service_date.isoformat(),
                              "reason": "unverified_stock"})
            continue
        if (offer.remaining_quantity or 0) < quantity:
            conflicts.append({"product_id": product_id, "service_date": service_date.isoformat(),
                              "reason": "sold_out", "remaining": offer.remaining_quantity})

    if conflicts:
        raise StockUnavailable(conflicts)

    allocations: list[OfferAllocation] = []
    for product_id, service_date, quantity in merged:
        result = await db.execute(
            update(PriceOffer)
            .where(
                PriceOffer.product_id == product_id,
                PriceOffer.service_date == service_date,
                PriceOffer.status == "available",
                PriceOffer.total_quantity.is_not(None),
                PriceOffer.total_quantity - PriceOffer.reserved_quantity
                - PriceOffer.confirmed_quantity >= quantity,
            )
            .values(reserved_quantity=PriceOffer.reserved_quantity + quantity)
        )
        if result.rowcount != 1:
            raise StockUnavailable([{
                "product_id": product_id, "service_date": service_date.isoformat(), "reason": "sold_out",
            }])
        allocation = OfferAllocation(
            order_id=order_id, product_id=product_id, service_date=service_date,
            quantity=quantity, state="reserved", expires_at=clock + ttl,
        )
        db.add(allocation)
        allocations.append(allocation)
    await db.flush()
    return allocations


def _missing(product_id, day):
    return {"product_id": product_id, "service_date": day.isoformat(), "reason": "reservation_missing"}


async def _allocations(db, order_id, state):
    return (await db.scalars(select(OfferAllocation).where(
        OfferAllocation.order_id == order_id, OfferAllocation.state == state,
    ).order_by(OfferAllocation.product_id, OfferAllocation.service_date).with_for_update())).all()


def _reconcile(allocations, expected):
    actual = {(row.product_id, row.service_date): row.quantity for row in allocations}
    wanted = {(product_id, day): quantity for product_id, day, quantity in merge_entries(expected)}
    issues = [_missing(*key) for key in sorted(wanted.keys() | actual.keys()) if wanted.get(key) != actual.get(key)]
    if issues:
        raise StockUnavailable(issues)


async def _verify_reserved(db, allocations):
    issues = []
    for row in allocations:
        offer = await db.get(PriceOffer, (row.product_id, row.service_date),
                             with_for_update=True, populate_existing=True)
        if offer is None or offer.reserved_quantity < row.quantity:
            issues.append(_missing(row.product_id, row.service_date))
    if issues:
        raise StockUnavailable(issues)


async def protect_paid(db, order_id, expected):
    allocations = await _allocations(db, order_id, "reserved")
    _reconcile(allocations, expected)
    await _verify_reserved(db, allocations)
    for row in allocations:
        row.expires_at = None


async def confirm(db: AsyncSession, order_id: str, *, now: datetime | None = None, expected=None) -> int:
    """Turn this order's reservations into confirmed occupancy; idempotent."""
    allocations = await _allocations(db, order_id, "reserved")
    if expected is not None:
        _reconcile(allocations, expected)
    else:
        clock = _now(now)
        allocations = [row for row in allocations if row.expires_at is None or (
            row.expires_at.replace(tzinfo=row.expires_at.tzinfo or timezone.utc) > clock
        )]
    await _verify_reserved(db, allocations)
    for allocation in allocations:
        result = await db.execute(
            update(PriceOffer)
            .where(
                PriceOffer.product_id == allocation.product_id,
                PriceOffer.service_date == allocation.service_date,
                PriceOffer.reserved_quantity >= allocation.quantity,
            )
            .values(
                reserved_quantity=PriceOffer.reserved_quantity - allocation.quantity,
                confirmed_quantity=PriceOffer.confirmed_quantity + allocation.quantity,
            )
        )
        if result.rowcount != 1:
            raise StockUnavailable([{
                "product_id": allocation.product_id,
                "service_date": allocation.service_date.isoformat(),
                "reason": "reservation_missing",
            }])
        allocation.state = "confirmed"
        allocation.expires_at = None
    await db.flush()
    return len(allocations)


async def release(db: AsyncSession, order_id: str, *, now: datetime | None = None) -> int:
    """Release only still-reserved rows for this order; repeated calls are no-ops."""
    allocations = await _allocations(db, order_id, "reserved")
    for allocation in allocations:
        await _release_one(db, allocation)
    await db.flush()
    return len(allocations)


async def release_confirmed(db: AsyncSession, order_id: str, *, now: datetime | None = None) -> int:
    """Give back occupancy that was already confirmed (cancellation after review)."""
    allocations = await _allocations(db, order_id, "confirmed")
    for allocation in allocations:
        result = await db.execute(
            update(PriceOffer)
            .where(
                PriceOffer.product_id == allocation.product_id,
                PriceOffer.service_date == allocation.service_date,
                PriceOffer.confirmed_quantity >= allocation.quantity,
            )
            .values(confirmed_quantity=PriceOffer.confirmed_quantity - allocation.quantity)
        )
        if result.rowcount != 1:
            raise StockUnavailable([_missing(allocation.product_id, allocation.service_date)])
        allocation.state = "released"
    await db.flush()
    return len(allocations)


async def expire_due(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Expire entire unpaid orders through the trading state transition."""
    from app.services.orders import expire_due as expire_orders

    return await expire_orders(db, now=now)
