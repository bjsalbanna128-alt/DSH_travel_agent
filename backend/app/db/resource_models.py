"""Enterprise suppliers, products and daily sale offers."""

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _new_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (CheckConstraint("status IN ('active', 'inactive')", name="ck_supplier_status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(160), index=True)
    settlement_name: Mapped[str] = mapped_column(String(160))
    contact_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    contact_info: Mapped[str] = mapped_column(String(160), default="", server_default="")
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active", index=True)
    contract_attachment_ref: Mapped[str | None] = mapped_column(String(255))
    settlement_workflow_ref: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("type IN ('hotel_room', 'attraction_ticket', 'vehicle')", name="ck_product_type"),
        CheckConstraint("status IN ('off_shelf', 'on_shelf')", name="ck_product_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    type: Mapped[str] = mapped_column(String(24), index=True)
    city: Mapped[str] = mapped_column(String(100))
    attributes: Mapped[dict] = mapped_column(JSON)
    poi: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    status: Mapped[str] = mapped_column(String(16), default="off_shelf", server_default="off_shelf", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)


class PriceOffer(Base):
    __tablename__ = "price_offers"
    __table_args__ = (
        CheckConstraint("cost_fen >= 0 AND sale_fen >= 0", name="ck_offer_nonnegative"),
        CheckConstraint("status IN ('available', 'stopped')", name="ck_offer_status"),
    )

    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True)
    service_date: Mapped[date] = mapped_column(Date, primary_key=True)
    cost_fen: Mapped[int] = mapped_column(Integer)
    sale_fen: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))


def check_existing_price_offers(conn: Connection) -> None:
    """Stop before adopting an incompatible legacy price table."""
    inspector = inspect(conn)
    if not inspector.has_table(PriceOffer.__tablename__):
        return
    columns = {column["name"]: column["type"] for column in inspector.get_columns("price_offers")}
    primary_key = inspector.get_pk_constraint("price_offers")["constrained_columns"]
    foreign_keys = inspector.get_foreign_keys("price_offers")
    if (
        not set(PriceOffer.__table__.columns.keys()) <= columns.keys()
        or set(primary_key or ()) != {"product_id", "service_date"}
        or not isinstance(columns.get("service_date"), Date)
        or not all(isinstance(columns.get(field), Integer) for field in ("cost_fen", "sale_fen"))
        or not any(key["referred_table"] == "products" and key["constrained_columns"] == ["product_id"]
                   for key in foreign_keys)
    ):
        raise RuntimeError("检测到不兼容的旧 price_offers 表，请先核对字段、金额单位与商品映射后迁移")
