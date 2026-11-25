"""Trusted order-event handlers. No HTTP route calls these writers."""

from calendar import monthrange
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.database import reserve_write
from app.db.membership_models import PointAccount, PointLot, PointTransaction
from app.db.models import User, UserRole

BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")
BIGINT_MAX = 2**63 - 1


class PointEventError(ValueError):
    pass


class PointEventConflict(PointEventError):
    pass


class OriginalPaymentPending(PointEventError):
    """The order adapter can retry this event after the payment arrives."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stored_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _event_time(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise PointEventError("Event time must include a timezone")
    return stored_utc(value)


def point_expiry(paid_at: datetime) -> datetime:
    local = paid_at.astimezone(BEIJING)
    year = local.year + 1
    day = min(local.day, monthrange(year, local.month)[1])
    return local.replace(year=year, day=day)


def _key(value: str, max_length: int = 128) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= max_length or value.strip() != value or not value.isprintable():
        raise PointEventError("Invalid order, account or source event identifier")
    return value


def _amount(value: int, minimum: int) -> None:
    if type(value) is not int or not minimum <= value <= BIGINT_MAX:
        raise PointEventError("Order amounts must be valid integer fen")


async def _account(db: AsyncSession, user_id: str, *, create: bool = False) -> PointAccount:
    if create:
        if await db.scalar(select(User.role).where(User.id == user_id)) != UserRole.TOURIST:
            raise PointEventError("Order points belong to an existing tourist")
        insert = postgres_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
        statement = insert(PointAccount).values(user_id=user_id, book_balance=0, last_sequence=0)
        await db.execute(statement.on_conflict_do_nothing(index_elements=[PointAccount.user_id]))
    return await db.get(PointAccount, user_id, with_for_update=True)


async def _existing(
    db: AsyncSession, event_key: str, order_id: str, amount_fen: int, user_id: str | None = None,
) -> PointTransaction | None:
    row = await db.scalar(select(PointTransaction).where(PointTransaction.event_key == event_key))
    if row is not None and (
        row.order_id != order_id or row.amount_fen != amount_fen or (user_id is not None and row.user_id != user_id)
    ):
        raise PointEventConflict("Source event conflicts with a recorded transaction")
    return row


def _append(
    db: AsyncSession, account: PointAccount, lot: PointLot, *, kind: str, event_key: str,
    delta: int, amount_fen: int | None, occurred_at: datetime, now: datetime, refund_id: str | None = None,
) -> PointTransaction:
    balance = account.book_balance + delta
    if not 0 <= balance <= BIGINT_MAX:
        raise PointEventError("Points balance is outside the ledger range")
    account.book_balance = balance
    account.last_sequence += 1
    row = PointTransaction(
        id=str(uuid4()), event_key=event_key, kind=kind, user_id=account.user_id, order_id=lot.order_id,
        refund_id=refund_id, delta=delta, amount_fen=amount_fen, occurred_at=occurred_at,
        recorded_at=now, book_balance_after=balance, sequence=account.last_sequence,
    )
    db.add(row)
    return row


def _expire(db: AsyncSession, account: PointAccount, lot: PointLot, now: datetime) -> bool:
    if lot.remaining_points == 0 or stored_utc(lot.expires_at) > now:
        return False
    _append(db, account, lot, kind="expiry", event_key=f"expiry:{lot.order_id}",
            delta=-lot.remaining_points, amount_fen=None, occurred_at=stored_utc(lot.expires_at), now=now)
    lot.remaining_points = 0
    return True


async def record_payment(
    sessions: async_sessionmaker, *, order_id: str, member_id: str, amount_fen: int,
    paid_at: datetime, event_id: str, now: datetime | None = None,
) -> PointTransaction:
    order_id, member_id = _key(order_id), _key(member_id, 36)
    key = f"payment:{_key(event_id)}"
    _amount(amount_fen, 0)
    paid_at, now = _event_time(paid_at), _event_time(now) if now else utc_now()
    try:
        async with sessions.begin() as db:
            await reserve_write(db)
            if previous := await _existing(db, key, order_id, amount_fen, member_id):
                return previous
            account = await _account(db, member_id, create=True)
            if previous := await _existing(db, key, order_id, amount_fen, member_id):
                return previous
            if await db.get(PointLot, order_id):
                raise PointEventConflict("The order already has a successful payment")
            earned = amount_fen // 10
            lot = PointLot(
                order_id=order_id, user_id=member_id, paid_fen=amount_fen, refunded_fen=0,
                earned_points=earned, remaining_points=earned,
                paid_at=paid_at, expires_at=stored_utc(point_expiry(paid_at)),
            )
            db.add(lot)
            await db.flush()
            payment = _append(db, account, lot, kind="payment", event_key=key, delta=earned,
                              amount_fen=amount_fen, occurred_at=paid_at, now=now)
            _expire(db, account, lot, now)
            return payment
    except IntegrityError:
        # The same source key or order can race across accounts on PostgreSQL.
        async with sessions() as db:
            if previous := await _existing(db, key, order_id, amount_fen, member_id):
                return previous
            if await db.get(PointLot, order_id):
                raise PointEventConflict("The order already has a successful payment") from None
        raise


async def record_refund(
    sessions: async_sessionmaker, *, order_id: str, refund_id: str,
    amount_fen: int, refunded_at: datetime, now: datetime | None = None,
) -> PointTransaction:
    order_id, refund_id = _key(order_id), _key(refund_id)
    key = f"refund:{refund_id}"
    _amount(amount_fen, 1)
    refunded_at, now = _event_time(refunded_at), _event_time(now) if now else utc_now()
    try:
        async with sessions.begin() as db:
            await reserve_write(db)
            if previous := await _existing(db, key, order_id, amount_fen):
                return previous
            member_id = await db.scalar(select(PointLot.user_id).where(PointLot.order_id == order_id))
            if member_id is None:
                raise OriginalPaymentPending("The original payment has not been recorded; retry after it arrives")
            account = await _account(db, member_id)
            lot = await db.get(PointLot, order_id, with_for_update=True)
            if previous := await _existing(db, key, order_id, amount_fen):
                return previous
            refunded_total = lot.refunded_fen + amount_fen
            if refunded_total > lot.paid_fen:
                raise PointEventConflict("Refunds exceed the original payment")

            _expire(db, account, lot, now)
            earned = (lot.paid_fen - refunded_total) // 10
            deducted = min(lot.earned_points - earned, lot.remaining_points)
            lot.refunded_fen, lot.earned_points = refunded_total, earned
            lot.remaining_points -= deducted
            return _append(db, account, lot, kind="refund", event_key=key, delta=-deducted,
                           amount_fen=amount_fen, occurred_at=refunded_at, now=now, refund_id=refund_id)
    except IntegrityError:
        async with sessions() as db:
            if previous := await _existing(db, key, order_id, amount_fen):
                return previous
        raise


async def expire_due(sessions: async_sessionmaker, *, now: datetime | None = None) -> int:
    cutoff = _event_time(now) if now else utc_now()
    expired = 0
    while True:
        async with sessions() as db:
            due = (await db.execute(
                select(PointLot.order_id, PointLot.user_id)
                .where(PointLot.expires_at <= cutoff, PointLot.remaining_points > 0)
                .order_by(PointLot.expires_at, PointLot.order_id).limit(100)
            )).all()
        if not due:
            return expired
        for order_id, member_id in due:
            async with sessions.begin() as db:
                await reserve_write(db)
                account = await _account(db, member_id)
                lot = await db.get(PointLot, order_id, with_for_update=True)
                if _expire(db, account, lot, cutoff):
                    expired += 1
