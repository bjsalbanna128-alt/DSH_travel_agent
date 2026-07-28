"""Async database engine and session management (SQLite)."""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# SQLite path — store in backend/data/
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DATA_DIR.mkdir(exist_ok=True)

DB_PATH = _DATA_DIR / "travel_agent.db"
SQLITE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# Use SQLite by default; switch to PostgreSQL if configured via .env
DATABASE_URL = SQLITE_URL
if settings.database_url and "postgresql" in settings.database_url:
    DATABASE_URL = settings.database_url

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables."""
    # Ensure all models are imported so they register with Base.metadata
    import app.db.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"[DB] Initialized at {DB_PATH}")


async def get_db() -> AsyncSession:
    """Dependency for FastAPI route handlers."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
