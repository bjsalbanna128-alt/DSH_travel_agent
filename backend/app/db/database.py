"""Async database engine and session management (SQLite)."""

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
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

def create_db_engine(url: str, **kwargs) -> AsyncEngine:
    db_engine = create_async_engine(url, **kwargs)
    if db_engine.dialect.name == "sqlite":
        @event.listens_for(db_engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return db_engine


engine = create_db_engine(DATABASE_URL)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables."""
    # Ensure all models are imported so they register with Base.metadata
    from app.db import (
        content_models, membership_models, order_models, recommendation_models, scenic_models,
    )  # noqa: F401
    from app.db.resource_models import check_existing_price_offers
    from app.db.order_migration import ensure_order_traveler_ciphertext
    from app.db.stock_migration import ensure_stock_columns
    from app.db.template_models import ItineraryTemplate, ItineraryTemplateVersion  # noqa: F401
    from app.db.trip_operator_migration import ensure_trip_operator_support
    from app.db.trip_version_migration import ensure_trip_version_index
    from app.db.user_role_migration import ensure_user_role_column
    from app.services.ai_dialog import seed_dialog
    from app.services.notifications import seed_message_settings
    from app.services.recommendation_delivery import seed_deliveries

    async with engine.begin() as conn:
        if conn.dialect.name == "sqlite":
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.run_sync(ensure_stock_columns)
        await conn.run_sync(check_existing_price_offers)
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(ensure_user_role_column)
        await conn.run_sync(ensure_trip_version_index)
        await conn.run_sync(ensure_trip_operator_support)
        await conn.run_sync(ensure_order_traveler_ciphertext)
        await seed_message_settings(conn)
        await seed_dialog(conn)
        await seed_deliveries(conn)
    print(f"[DB] Initialized at {DB_PATH}")


async def reserve_write(db: AsyncSession) -> AsyncSession:
    if db.get_bind().dialect.name == "sqlite":
        await db.execute(text("BEGIN IMMEDIATE"))
    return db


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependency for FastAPI route handlers."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

