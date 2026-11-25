"""Member records and the order points ledger."""

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, LargeBinary, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class PrivateContact:
    phone_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    phone_mask: Mapped[str | None] = mapped_column(String(25))
    document_type: Mapped[str | None] = mapped_column(String(20))
    document_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    document_mask: Mapped[str | None] = mapped_column(String(45))
    document_digest: Mapped[str | None] = mapped_column(String(64), deferred=True)


class MemberProfile(PrivateContact, Base):
    __tablename__ = "member_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    nickname: Mapped[str | None] = mapped_column(String(60))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    birthday: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(16))
    real_name: Mapped[str | None] = mapped_column(String(100))


class Traveler(PrivateContact, Base):
    __tablename__ = "travelers"
    __table_args__ = (
        Index("uq_traveler_document", "user_id", "document_type", "document_digest", unique=True),
        Index(
            "uq_traveler_default", "user_id", unique=True,
            sqlite_where=text("is_default"), postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    real_name: Mapped[str] = mapped_column(String(100))
    relationship: Mapped[str] = mapped_column(String(30))
    is_default: Mapped[bool] = mapped_column(default=False)


class PointAccount(Base):
    __tablename__ = "point_accounts"
    __table_args__ = (CheckConstraint("book_balance >= 0", name="ck_point_account_balance"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    book_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    last_sequence: Mapped[int] = mapped_column(BigInteger, default=0)


class PointLot(Base):
    __tablename__ = "point_lots"
    __table_args__ = (
        CheckConstraint("paid_fen >= refunded_fen AND refunded_fen >= 0", name="ck_point_lot_refunds"),
        CheckConstraint(
            "earned_points >= remaining_points AND remaining_points >= 0", name="ck_point_lot_remaining",
        ),
        Index("ix_point_lot_member_expiry", "user_id", "expires_at", "order_id"),
        Index("ix_point_lot_expiry", "expires_at", "order_id"),
    )

    order_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("point_accounts.user_id"))
    paid_fen: Mapped[int] = mapped_column(BigInteger)
    refunded_fen: Mapped[int] = mapped_column(BigInteger, default=0)
    earned_points: Mapped[int] = mapped_column(BigInteger)
    remaining_points: Mapped[int] = mapped_column(BigInteger)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PointTransaction(Base):
    __tablename__ = "point_transactions"
    __table_args__ = (
        CheckConstraint("kind IN ('payment', 'refund', 'expiry')", name="ck_point_transaction_kind"),
        UniqueConstraint("user_id", "sequence", name="uq_point_transaction_sequence"),
        Index("ix_point_transaction_member_order", "user_id", "order_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(136), unique=True)
    kind: Mapped[str] = mapped_column(String(12))
    user_id: Mapped[str] = mapped_column(ForeignKey("point_accounts.user_id"))
    order_id: Mapped[str] = mapped_column(ForeignKey("point_lots.order_id"))
    refund_id: Mapped[str | None] = mapped_column(String(128))
    delta: Mapped[int] = mapped_column(BigInteger)
    amount_fen: Mapped[int | None] = mapped_column(BigInteger)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    book_balance_after: Mapped[int] = mapped_column(BigInteger)
    sequence: Mapped[int] = mapped_column(BigInteger)
