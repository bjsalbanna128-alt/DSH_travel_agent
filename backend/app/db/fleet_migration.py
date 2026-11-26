from sqlalchemy import inspect, text


def ensure_fleet_columns(conn):
    inspector = inspect(conn)
    for table, fields in {
        "suppliers": {"fleet_city": "VARCHAR(100) NOT NULL DEFAULT ''"},
        "price_offers": {"trip_priced": "BOOLEAN NOT NULL DEFAULT FALSE"},
        "vehicles": {"model_code": "VARCHAR(40)"},
        "drivers": {"model_codes": "JSON"},
    }.items():
        if not inspector.has_table(table):
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column, clause in fields.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {clause}"))
