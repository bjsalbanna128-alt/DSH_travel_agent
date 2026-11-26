from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ScenicRestriction(Base):
    __tablename__ = "scenic_restrictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    revision: Mapped[int]
    published_version: Mapped[int]
    active: Mapped[bool]
    draft: Mapped[dict] = mapped_column(JSON)
    city_key: Mapped[str] = mapped_column(String(100), index=True)
    name_key: Mapped[str] = mapped_column(String(160))
    updated_by: Mapped[str] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScenicRestrictionVersion(Base):
    __tablename__ = "scenic_restriction_versions"

    restriction_id: Mapped[str] = mapped_column(
        ForeignKey("scenic_restrictions.id", ondelete="RESTRICT"), primary_key=True,
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    draft_revision: Mapped[int]
    detail: Mapped[dict] = mapped_column(JSON)
    city_key: Mapped[str] = mapped_column(String(100), index=True)
    published_by: Mapped[str] = mapped_column(String(36))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlanningQualityReport(Base):
    __tablename__ = "planning_quality_reports"
    __table_args__ = (Index("ix_quality_report_order", "checked_at", "trip_id", "version"),)

    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    destination: Mapped[str] = mapped_column(String(100))
    stage: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(16))
    findings: Mapped[list] = mapped_column(JSON)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlanningQualityRule(Base):
    __tablename__ = "planning_quality_report_rules"
    __table_args__ = (
        ForeignKeyConstraint(["trip_id", "version"],
                             ["planning_quality_reports.trip_id", "planning_quality_reports.version"],
                             ondelete="CASCADE"),
        Index("ix_quality_rule_type", "rule", "trip_id", "version"),
    )

    trip_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    rule: Mapped[str] = mapped_column(String(24), primary_key=True)
