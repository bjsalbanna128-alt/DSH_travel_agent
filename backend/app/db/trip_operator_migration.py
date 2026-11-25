"""Add the confirmed-version column and the operator trip index to older databases."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.db.models import Trip

COLUMN = "confirmed_version"
INDEX_NAME = "ix_trips_user_status_updated"


def ensure_trip_operator_support(conn: Connection) -> None:
    """Idempotently add the column and index that the operator trip query relies on."""
    columns = {column["name"] for column in inspect(conn).get_columns(Trip.__table__.name)}
    if COLUMN not in columns:
        conn.execute(text(f"ALTER TABLE {Trip.__table__.name} ADD COLUMN {COLUMN} INTEGER"))

    index = next(item for item in Trip.__table__.indexes if item.name == INDEX_NAME)
    if any(item["name"] == INDEX_NAME for item in inspect(conn).get_indexes(Trip.__table__.name)):
        return
    index.create(conn)
