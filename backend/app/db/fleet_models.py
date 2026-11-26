"""Vehicle models and the time commitments created by vehicle order items."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class FleetModel(Base):
    __tablename__ = "fleet_models"

    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))


class FleetAllocation(Base):
    __tablename__ = "fleet_allocations"
    __table_args__ = (
        UniqueConstraint("order_id", "service_key", name="uq_fleet_order_service"),
        CheckConstraint("starts_at < ends_at AND passengers > 0 AND luggage >= 0", name="ck_fleet_trip"),
        CheckConstraint("state IN ('reserved', 'confirmed', 'released')", name="ck_fleet_allocation_state"),
        Index("ix_fleet_allocation_interval", "supplier_id", "state", "starts_at", "ends_at"),
    )

    order_item_id: Mapped[str] = mapped_column(ForeignKey("order_items.id", ondelete="RESTRICT"), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"))
    service_key: Mapped[str] = mapped_column(String(64))
    model_code: Mapped[str] = mapped_column(String(40))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    passengers: Mapped[int]
    luggage: Mapped[int]
    state: Mapped[str] = mapped_column(String(12), default="reserved", server_default="reserved")
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id", ondelete="RESTRICT"), index=True)
    driver_id: Mapped[str | None] = mapped_column(ForeignKey("drivers.id", ondelete="RESTRICT"), index=True)
