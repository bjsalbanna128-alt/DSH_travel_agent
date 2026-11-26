"""A durable simulated-money ledger, isolated from member rewards."""

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import aliased

from app.db.membership_models import PointAccount, PointLot, PointTransaction
from app.db.order_models import DemoPointEvent, Order, OrderDataMigration, OrderPayment, OrderRefund
from app.services.member_points import point_expiry, stored_utc, utc_now


def _insert(connection, model):
    return (sqlite_insert if connection.dialect.name == "sqlite" else pg_insert)(model)


async def queue_event(db, order, kind, amount, occurred_at):
    await db.execute(_insert(db.get_bind(), DemoPointEvent).values(
        order_id=order.id, user_id=order.user_id, kind=kind, amount_fen=amount, occurred_at=occurred_at,
    ).on_conflict_do_nothing())


async def apply_events(db, order_id=None):
    pending = select(DemoPointEvent.order_id).where(DemoPointEvent.posted_at.is_(None)).distinct()
    if order_id is not None:
        pending = pending.where(DemoPointEvent.order_id == order_id)
    for key in await db.scalars(pending.order_by(DemoPointEvent.order_id)):
        # Money transitions and consumers share the order lock.
        await db.get(Order, key, with_for_update=True)
        paid = await db.get(DemoPointEvent, (key, "payment"))
        if paid is None:
            continue
        if paid.posted_at is None:
            paid.posted_at = utc_now()
        refund = await db.get(DemoPointEvent, (key, "refund"))
        if refund is not None and refund.posted_at is None:
            refund.posted_at = utc_now()


async def overview(db, user_id=None, *, now=None):
    payment, refund = aliased(DemoPointEvent), aliased(DemoPointEvent)
    query = select(payment.amount_fen, payment.occurred_at, refund.amount_fen).outerjoin(
        refund, and_(refund.order_id == payment.order_id, refund.kind == "refund", refund.posted_at.is_not(None)),
    ).where(payment.kind == "payment", payment.posted_at.is_not(None))
    if user_id is not None:
        query = query.where(payment.user_id == user_id)
    clock = now or utc_now()
    rows = (await db.execute(query)).all()
    balance = sum(max(0, paid - (refunded or 0)) // 10 for paid, when, refunded in rows
                  if point_expiry(stored_utc(when)) > clock)
    return {"balance": balance, "payments": len(rows), "refunds": sum(refunded is not None for _, _, refunded in rows)}


async def migrate_old_points(conn):
    inserted = await conn.scalar(_insert(conn, OrderDataMigration).values(name="isolated-demo-points-v1")
        .on_conflict_do_nothing().returning(OrderDataMigration.name))
    if not inserted:
        return
    rows = (await conn.execute(select(
        Order.id, Order.user_id, OrderPayment.id, OrderPayment.amount_fen, OrderPayment.paid_at,
        OrderRefund.amount_fen.label("refund_amount"), OrderRefund.processed_at.label("refund_at"),
    ).join(OrderPayment, OrderPayment.order_id == Order.id).outerjoin(
        OrderRefund, and_(OrderRefund.order_id == Order.id, OrderRefund.status == "succeeded"),
    ).where(OrderPayment.provider == "mock"))).all()
    affected = set()
    for row in rows:
        for kind, amount, at in (("payment", row.amount_fen, row.paid_at), ("refund", row.refund_amount, row.refund_at)):
            if amount is None:
                continue
            await conn.execute(_insert(conn, DemoPointEvent).values(
                order_id=row[0], user_id=row.user_id, kind=kind, amount_fen=amount, occurred_at=at or row.paid_at,
                posted_at=utc_now(),
            ).on_conflict_do_nothing())
        old_payment = await conn.scalar(select(PointTransaction.id).where(
            PointTransaction.order_id == row[0], PointTransaction.user_id == row.user_id,
            PointTransaction.event_key == f"payment:mock-{row[2]}",
        ))
        if old_payment is not None:
            await conn.execute(delete(PointTransaction).where(PointTransaction.order_id == row[0]))
            await conn.execute(delete(PointLot).where(PointLot.order_id == row[0]))
            affected.add(row.user_id)
    for member in sorted(affected):
        await conn.execute(select(PointAccount.user_id).where(PointAccount.user_id == member).with_for_update())
        balance = 0
        transactions = await conn.execute(select(PointTransaction.id, PointTransaction.delta).where(
            PointTransaction.user_id == member,
        ).order_by(PointTransaction.sequence))
        for txn_id, delta in transactions:
            balance += delta
            await conn.execute(update(PointTransaction).where(PointTransaction.id == txn_id).values(book_balance_after=balance))
        await conn.execute(update(PointAccount).where(PointAccount.user_id == member).values(book_balance=balance))
