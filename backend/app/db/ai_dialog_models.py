from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class DialogDraft(Base):
    __tablename__ = "ai_dialog_draft"

    id: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int]
    current_version: Mapped[int]
    config: Mapped[dict] = mapped_column(JSON)
    updated_by: Mapped[str | None] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DialogVersion(Base):
    __tablename__ = "ai_dialog_versions"

    version: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int]
    config: Mapped[dict] = mapped_column(JSON)
    published_by: Mapped[str | None] = mapped_column(String(36))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DialogSession(Base):
    __tablename__ = "ai_dialog_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[int] = mapped_column(ForeignKey("ai_dialog_versions.version"))
    turn: Mapped[int]
    answers: Mapped[dict] = mapped_column(JSON)


class DialogTurn(Base):
    __tablename__ = "ai_dialog_turns"
    __table_args__ = (
        ForeignKeyConstraint(["user_id", "thread_id"], ["ai_dialog_sessions.user_id", "ai_dialog_sessions.thread_id"],
                             ondelete="CASCADE"),
    )

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    turn: Mapped[int] = mapped_column(primary_key=True)
    query_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
