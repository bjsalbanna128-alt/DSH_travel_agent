"""Add the encrypted document column to an existing order_travelers table."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

COLUMN = "document_ciphertext"


def ensure_order_traveler_ciphertext(conn: Connection) -> None:
    inspector = inspect(conn)
    if not inspector.has_table("order_travelers"):
        return
    columns = {column["name"] for column in inspector.get_columns("order_travelers")}
    if COLUMN in columns:
        return
    conn.execute(text(f"ALTER TABLE order_travelers ADD COLUMN {COLUMN} BLOB"))
