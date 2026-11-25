"""Add account roles to databases created before roles existed."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.db.models import USER_ROLE_CHECK, UserRole


def ensure_user_role_column(conn: Connection) -> None:
    if any(column["name"] == "role" for column in inspect(conn).get_columns("users")):
        return

    # SQLite startup already holds a write lock. PostgreSQL can guard the ADD itself.
    if_not_exists = "IF NOT EXISTS " if conn.dialect.name == "postgresql" else ""
    conn.execute(text(
        f"ALTER TABLE users ADD COLUMN {if_not_exists}role VARCHAR(20) "
        f"DEFAULT '{UserRole.TOURIST}' NOT NULL CONSTRAINT ck_users_role CHECK ({USER_ROLE_CHECK})"
    ))
