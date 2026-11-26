"""Fulfillment tasks derived from confirmed order items."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

TASK_STATUSES = ("pending", "ready", "in_progress", "completed", "exception", "cancelled")
TASK_TYPES = ("hotel_checkin", "ticket_entry", "vehicle_pickup", "vehicle_charter", "other")


def _new_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FulfillmentTask(Base):
    __tablename__ = "fulfillment_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in TASK_STATUSES)), name="ck_ft_status",
        ),
        CheckConstraint(
            "task_type IN ({})".format(", ".join(f"'{t}'" for t in TASK_TYPES)), name="ck_ft_type",
        ),
        Index("ix_ft_date_status", "service_date", "status"),
        Index("ix_ft_order", "order_id"),
        Index("ix_ft_supplier", "supplier_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    order_id: Mapped[str] = mapped_column(String(36))
    order_item_id: Mapped[str] = mapped_column(String(36), unique=True)
    user_id: Mapped[str | None] = mapped_column(String(36))
    task_type: Mapped[str] = mapped_column(String(24))
    service_date: Mapped[str] = mapped_column(String(10))
    start_time: Mapped[str | None] = mapped_column(String(5))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    location_name: Mapped[str] = mapped_column(String(160), default="", server_default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    product_name: Mapped[str] = mapped_column(String(160), default="", server_default="")
    supplier_id: Mapped[str | None] = mapped_column(String(36))
    supplier_name: Mapped[str] = mapped_column(String(160), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    voucher_no: Mapped[str] = mapped_column(String(64), default="", server_default="")
    confirmation_no: Mapped[str] = mapped_column(String(64), default="", server_default="")
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    exception_reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    previous_status: Mapped[str | None] = mapped_column(String(16))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now,
    )


class DispatchAssignment(Base):
    __tablename__ = "dispatch_assignments"
    __table_args__ = (Index("ix_dispatch_task", "task_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("fulfillment_tasks.id", ondelete="RESTRICT"))
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"))
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id", ondelete="RESTRICT"))
    assigned_by: Mapped[str] = mapped_column(String(36))
    assigned_by_name: Mapped[str] = mapped_column(String(50))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")


class FulfillmentEvent(Base):
    __tablename__ = "fulfillment_events"
    __table_args__ = (Index("ix_fe_task", "task_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("fulfillment_tasks.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(24))
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str | None] = mapped_column(String(16))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    actor_name: Mapped[str | None] = mapped_column(String(50))
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
