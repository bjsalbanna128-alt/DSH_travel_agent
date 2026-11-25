"""Recommendation drafts, publication snapshots, and immutable cover images."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _new_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RecommendationImage(Base):
    __tablename__ = "recommendation_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    mime: Mapped[str] = mapped_column(String(24))
    width: Mapped[int]
    height: Mapped[int]
    size_bytes: Mapped[int]


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint("visibility IN ('draft', 'published', 'unpublished')", name="ck_recommendation_visibility"),
        CheckConstraint("published_version >= 0 AND revision > 0 AND display_order >= 0", name="ck_recommendation_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    title: Mapped[str] = mapped_column(String(40))
    place: Mapped[str] = mapped_column(String(100), default="", server_default="")
    short_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    display_order: Mapped[int] = mapped_column(default=100, server_default="100")
    cover_id: Mapped[str | None] = mapped_column(ForeignKey("recommendation_images.id", ondelete="RESTRICT"), index=True)
    visibility: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft", index=True)
    published_version: Mapped[int] = mapped_column(default=0, server_default="0")
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    created_by: Mapped[str] = mapped_column(String(36))
    updated_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class RecommendationVersion(Base):
    __tablename__ = "recommendation_versions"
    __table_args__ = (
        Index("ix_recommendation_version_display_order", "display_order", "recommendation_id"),
        CheckConstraint("display_order >= 0 AND version > 0", name="ck_recommendation_version_order"),
    )

    recommendation_id: Mapped[str] = mapped_column(
        ForeignKey("recommendations.id", ondelete="RESTRICT"), primary_key=True,
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(40))
    place: Mapped[str] = mapped_column(String(100))
    short_text: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int]
    cover_id: Mapped[str] = mapped_column(ForeignKey("recommendation_images.id", ondelete="RESTRICT"), index=True)
    published_by: Mapped[str] = mapped_column(String(36))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
