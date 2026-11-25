"""Ticket processing history and transactional notification outbox."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class MessageSetting(Base):
    __tablename__ = "message_settings"
    __table_args__ = (CheckConstraint("revision > 0", name="ck_message_settings_revision"),)

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    revision: Mapped[int] = mapped_column(default=1)
    updated_by: Mapped[str | None] = mapped_column(String(36))
    updated_by_name: Mapped[str | None] = mapped_column(String(50))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("category IN ('inquiry', 'complaint', 'suggestion')", name="ck_ticket_category"),
        CheckConstraint("priority IN ('low', 'normal', 'high')", name="ck_ticket_priority"),
        CheckConstraint(
            "(status = 'new' AND assignee_id IS NULL) OR "
            "(status IN ('processing', 'closed') AND assignee_id IS NOT NULL)", name="ck_ticket_status_owner",
        ),
        CheckConstraint("revision > 0", name="ck_ticket_revision"),
        Index("ix_ticket_submitter_updated", "submitter_id", "updated_at", "id"),
        Index("ix_ticket_status_assignee", "status", "assignee_id", "updated_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    number: Mapped[str] = mapped_column(String(34), unique=True)
    submitter_id: Mapped[str] = mapped_column(String(36))
    order_id: Mapped[str | None] = mapped_column(String(36))
    category: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="new")
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    assignee_id: Mapped[str | None] = mapped_column(String(36), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TicketHandling(Base):
    __tablename__ = "ticket_handlings"
    __table_args__ = (
        CheckConstraint("round > 0", name="ck_ticket_handling_round"),
        CheckConstraint(
            "(completed_at IS NULL AND completed_by IS NULL AND result IS NULL) OR "
            "(completed_at IS NOT NULL AND completed_by IS NOT NULL AND result IS NOT NULL)",
            name="ck_ticket_handling_completion",
        ),
        Index("uq_ticket_open_handling", "ticket_id", unique=True,
              sqlite_where=text("completed_at IS NULL"), postgresql_where=text("completed_at IS NULL")),
    )

    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id", ondelete="RESTRICT"), primary_key=True)
    round: Mapped[int] = mapped_column(primary_key=True)
    handler_id: Mapped[str] = mapped_column(String(36))
    handler_name: Mapped[str] = mapped_column(String(50))
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[str | None] = mapped_column(String(36))
    result: Mapped[str | None] = mapped_column(Text)


class NotificationEvent(Base):
    __tablename__ = "notification_events"
    __table_args__ = (Index("ix_notification_pending", "delivered_at", "next_attempt_at", "key"),)

    key: Mapped[str] = mapped_column(String(112), primary_key=True)
    code: Mapped[str] = mapped_column(ForeignKey("message_settings.code", ondelete="RESTRICT"))
    target_type: Mapped[str] = mapped_column(String(24))
    target_id: Mapped[str] = mapped_column(String(36))
    target_version: Mapped[int | None]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSON)
    recipients: Mapped[list[dict]] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("event_key", "code", "recipient_id", name="uq_message_delivery"),
        CheckConstraint("recipient_role IN ('operator', 'tourist')", name="ck_message_recipient_role"),
        CheckConstraint("status IN ('sent', 'failed')", name="ck_message_delivery_status"),
        CheckConstraint(
            "target_type IN ('trip_confirmation', 'admin_ticket', 'tourist_ticket')", name="ck_message_target",
        ),
        Index("ix_message_inbox", "recipient_role", "recipient_id", "status", "sent_at", "id"),
        Index("ix_message_unread", "recipient_role", "recipient_id", "status", "read_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_key: Mapped[str] = mapped_column(ForeignKey("notification_events.key", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(String(32))
    recipient_id: Mapped[str] = mapped_column(String(36))
    recipient_role: Mapped[str] = mapped_column(String(16))
    target_type: Mapped[str] = mapped_column(String(24))
    target_id: Mapped[str] = mapped_column(String(36))
    target_version: Mapped[int | None]
    title: Mapped[str] = mapped_column(String(260), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12))
    error_summary: Mapped[str | None] = mapped_column(String(255))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
