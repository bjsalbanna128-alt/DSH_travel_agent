"""Add stock counters and supplier kind to an existing database, idempotently."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

SUPPLIER_COLUMN = "kind"
OFFER_COLUMNS = {
    "total_quantity": "INTEGER",
    "reserved_quantity": "INTEGER NOT NULL DEFAULT 0",
    "confirmed_quantity": "INTEGER NOT NULL DEFAULT 0",
}
# A table with these columns is our own schema; anything else is the legacy
# incompatible table that check_existing_price_offers must keep rejecting.
OUR_OFFER_COLUMNS = {"product_id", "service_date", "cost_fen", "sale_fen", "status"}


def ensure_stock_columns(conn: Connection) -> None:
    inspector = inspect(conn)
    if inspector.has_table("suppliers"):
        columns = {column["name"] for column in inspector.get_columns("suppliers")}
        if SUPPLIER_COLUMN not in columns:
            conn.execute(text(
                "ALTER TABLE suppliers ADD COLUMN kind VARCHAR(24) NOT NULL DEFAULT 'other'"
            ))

    if not inspector.has_table("price_offers"):
        return
    columns = {column["name"] for column in inspector.get_columns("price_offers")}
    if not OUR_OFFER_COLUMNS <= columns:
        return
    for name, ddl in OFFER_COLUMNS.items():
        if name not in columns:
            conn.execute(text(f"ALTER TABLE price_offers ADD COLUMN {name} {ddl}"))
