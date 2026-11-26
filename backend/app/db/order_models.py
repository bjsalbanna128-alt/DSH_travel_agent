"""Orders: trading state, fund state, snapshots, payments, refunds and events."""

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

ORDER_STATUSES = (
    "pending_payment", "paid_pending_review", "confirmed", "cancel_requested", "cancelled", "completed",
)
FUND_STATUSES = ("unpaid", "processing", "paid", "refunding", "refunded", "refund_failed")


def _new_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _status_check() -> str:
    return "status IN ({})".format(", ".join(f"'{value}'" for value in ORDER_STATUSES))


def _fund_check() -> str:
    return "fund_status IN ({})".format(", ".join(f"'{value}'" for value in FUND_STATUSES))


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(_status_check(), name="ck_order_status"),
        CheckConstraint(_fund_check(), name="ck_order_fund_status"),
        CheckConstraint("total_sale_fen >= 0 AND total_cost_fen >= 0", name="ck_order_amounts"),
        CheckConstraint("version > 0", name="ck_order_version"),
        UniqueConstraint("user_id", "client_key", name="uq_order_client_key"),
        Index("ix_order_status_created", "status", "created_at"),
        Index("ix_order_user", "user_id"),
        Index("ix_order_expiry", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    order_no: Mapped[str] = mapped_column(String(24), unique=True)
    user_id: Mapped[str] = mapped_column(String(36))
    trip_id: Mapped[str | None] = mapped_column(String(36))
    client_key: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="pending_payment", server_default="pending_payment")
    fund_status: Mapped[str] = mapped_column(String(16), default="unpaid", server_default="unpaid")
    contact_name: Mapped[str] = mapped_column(String(50))
    contact_phone: Mapped[str] = mapped_column(String(32))
    total_sale_fen: Mapped[int] = mapped_column(Integer)
    total_cost_fen: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    reviewed_by: Mapped[str | None] = mapped_column(String(36))
    reviewed_by_name: Mapped[str | None] = mapped_column(String(50))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now,
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_item_quantity"),
        CheckConstraint("unit_sale_fen >= 0 AND unit_cost_fen >= 0", name="ck_order_item_amounts"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(String(36))
    supplier_id: Mapped[str] = mapped_column(String(36))
    product_name: Mapped[str] = mapped_column(String(160))
    product_type: Mapped[str] = mapped_column(String(24))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    service_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_sale_fen: Mapped[int] = mapped_column(Integer)
    unit_cost_fen: Mapped[int] = mapped_column(Integer)
    subtotal_sale_fen: Mapped[int] = mapped_column(Integer)
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class OrderTraveler(Base):
    """Only masked identifiers are kept with the order; full PII stays in the profile."""

    __tablename__ = "order_travelers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    document_type: Mapped[str] = mapped_column(String(16), default="", server_default="")
    document_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    document_mask: Mapped[str] = mapped_column(String(32), default="", server_default="")
    phone_mask: Mapped[str] = mapped_column(String(32), default="", server_default="")
    is_lead: Mapped[bool] = mapped_column(default=False)


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (Index("ix_order_event", "order_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str | None] = mapped_column(String(24))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    actor_name: Mapped[str | None] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class OrderPayment(Base):
    __tablename__ = "order_payments"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_payment_order"),
        UniqueConstraint("event_id", name="uq_payment_event"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(16), default="mock", server_default="mock")
    amount_fen: Mapped[int] = mapped_column(Integer)
    event_id: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class OrderRefund(Base):
    __tablename__ = "order_refunds"
    __table_args__ = (
        UniqueConstraint("refund_no", name="uq_refund_no"),
        CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name="ck_refund_status"),
        CheckConstraint("amount_fen >= 0", name="ck_refund_amount"),
        Index("ix_refund_pending", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    refund_no: Mapped[str] = mapped_column(String(32))
    amount_fen: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str] = mapped_column(String(200), default="", server_default="")
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class OrderSequence(Base):
    __tablename__ = "order_sequences"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
