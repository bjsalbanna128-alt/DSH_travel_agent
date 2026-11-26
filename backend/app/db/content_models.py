"""Content layer: attraction and hotel descriptions independent of products."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _new_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlaceContent(Base):
    """One row per attraction or hotel, whether or not we sell it."""

    __tablename__ = "place_contents"
    __table_args__ = (
        UniqueConstraint("city", "name", name="uq_content_city_name"),
        CheckConstraint("kind IN ('attraction', 'hotel')", name="ck_content_kind"),
        CheckConstraint("status IN ('draft', 'published', 'unpublished')", name="ck_content_status"),
        Index("ix_content_kind_city_status", "kind", "city", "status"),
        Index("ix_content_name", "name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    kind: Mapped[str] = mapped_column(String(16))
    city: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(32), default="", server_default="")
    rating: Mapped[float | None] = mapped_column(Float)
    visit_duration_hours: Mapped[float | None] = mapped_column(Float)
    opening_hours: Mapped[str] = mapped_column(String(64), default="", server_default="")
    ticket_price_hint_cny: Mapped[float | None] = mapped_column(Float)
    star_rating: Mapped[int | None] = mapped_column(Integer)
    landmark_hint: Mapped[str] = mapped_column(String(160), default="", server_default="")
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    suitable_for: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    highlights: Mapped[list] = mapped_column(JSON, default=list)
    cover_image_url: Mapped[str] = mapped_column(String(500), default="", server_default="")
    source: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    created_by: Mapped[str | None] = mapped_column(String(36))
    updated_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now,
    )


class PlaceContentProduct(Base):
    """Content ↔ product binding; one content can sell several ticket types or rooms."""

    __tablename__ = "place_content_products"
    __table_args__ = (
        Index("ix_content_product_product", "product_id"),
    )

    content_id: Mapped[str] = mapped_column(
        ForeignKey("place_contents.id", ondelete="CASCADE"), primary_key=True,
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True,
    )
