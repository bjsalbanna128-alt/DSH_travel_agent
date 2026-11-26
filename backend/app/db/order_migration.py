"""Add the encrypted document column to an existing order_travelers table."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

def ensure_order_traveler_ciphertext(conn: Connection) -> None:
    inspector = inspect(conn)
    encrypted = "BYTEA" if conn.dialect.name == "postgresql" else "BLOB"
    for table, fields in (
        ("order_travelers", {"document_ciphertext": encrypted}),
        ("orders", {"request_fingerprint": "VARCHAR(64)", "departure_date": "DATE"}),
    ):
        if not inspector.has_table(table):
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        for name, sql_type in fields.items():
            if name not in present:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
