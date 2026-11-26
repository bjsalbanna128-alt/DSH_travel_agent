"""Enterprise suppliers, products and daily sale offers."""

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
    inspect, text,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _new_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_supplier_status"),
        CheckConstraint(
            "kind IN ('hotel', 'ticket', 'vehicle_fleet', 'other')", name="ck_supplier_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(160), index=True)
    settlement_name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(24), default="other", server_default="other", index=True)
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
        CheckConstraint(
            "total_quantity IS NULL OR total_quantity >= 0", name="ck_offer_total_nonnegative",
        ),
        CheckConstraint(
            "reserved_quantity >= 0 AND confirmed_quantity >= 0", name="ck_offer_allocations_nonnegative",
        ),
        CheckConstraint(
            "total_quantity IS NULL OR reserved_quantity + confirmed_quantity <= total_quantity",
            name="ck_offer_within_total",
        ),
    )

    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True)
    service_date: Mapped[date] = mapped_column(Date, primary_key=True)
    cost_fen: Mapped[int] = mapped_column(Integer)
    sale_fen: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    # 总投放为空表示库存未核实：可以查看历史，但游客不能下单。
    total_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    confirmed_quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    @property
    def stock_verified(self) -> bool:
        return self.total_quantity is not None

    @property
    def remaining_quantity(self) -> int | None:
        if self.total_quantity is None:
            return None
        return self.total_quantity - self.reserved_quantity - self.confirmed_quantity


class OfferAllocation(Base):
    """One row per order and service day, tracking reserved or confirmed stock."""

    __tablename__ = "offer_allocations"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", "service_date", name="uq_allocation_order_day"),
        CheckConstraint("quantity > 0", name="ck_allocation_positive"),
        CheckConstraint(
            "state IN ('reserved', 'confirmed', 'released')", name="ck_allocation_state",
        ),
        Index("ix_allocation_order", "order_id"),
        Index("ix_allocation_expiry", "state", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    order_id: Mapped[str] = mapped_column(String(36), index=True)
    order_item_id: Mapped[str | None] = mapped_column(String(36))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    service_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), default="reserved", server_default="reserved")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now,
    )


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("supplier_id", "plate_no", name="uq_vehicle_plate"),
        CheckConstraint("seats > 0", name="ck_vehicle_seats"),
        CheckConstraint("luggage >= 0", name="ck_vehicle_luggage"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_vehicle_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    plate_no: Mapped[str] = mapped_column(String(16))
    model_name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    seats: Mapped[int] = mapped_column(Integer)
    luggage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now,
    )


class Driver(Base):
    __tablename__ = "drivers"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_driver_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(32))
    license_type: Mapped[str] = mapped_column(String(16), default="", server_default="")
    service_cities: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now,
    )


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
