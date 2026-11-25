"""Editable enterprise templates and immutable published snapshots."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ItineraryTemplate(Base):
    __tablename__ = "itinerary_templates"
    __table_args__ = (
        CheckConstraint("visibility IN ('draft', 'published', 'unpublished')", name="ck_template_visibility"),
        CheckConstraint("published_version >= 0 AND revision > 0", name="ck_template_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    draft: Mapped[dict] = mapped_column(JSON)
    draft_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(160))
    destination: Mapped[str] = mapped_column(String(100))
    days_count: Mapped[int]
    visibility: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft", index=True)
    published_version: Mapped[int] = mapped_column(default=0, server_default="0")
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    created_by: Mapped[str] = mapped_column(String(36))
    updated_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ItineraryTemplateVersion(Base):
    __tablename__ = "itinerary_template_versions"
    __table_args__ = (Index("ix_template_version_published_at", "published_at", "template_id"),)

    template_id: Mapped[str] = mapped_column(
        ForeignKey("itinerary_templates.id", ondelete="RESTRICT"), primary_key=True,
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    draft_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(160))
    destination: Mapped[str] = mapped_column(String(100))
    days_count: Mapped[int]
    published_by: Mapped[str] = mapped_column(String(36))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
