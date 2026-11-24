"""Install the unique trip-revision index on databases created before it existed."""

from itertools import groupby

from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.engine import Connection

from app.db.models import Trip, TripVersion


def ensure_trip_version_index(conn: Connection) -> None:
    table = TripVersion.__table__
    index = next(index for index in table.indexes if index.unique)
    if any(item["name"] == index.name for item in inspect(conn).get_indexes(table.name)):
        return
    if conn.dialect.name == "postgresql":
        conn.execute(text("LOCK TABLE trip_versions IN SHARE ROW EXCLUSIVE MODE"))
        if any(item["name"] == index.name for item in inspect(conn).get_indexes(table.name)):
            return

    duplicate_trips = conn.scalars(
        select(table.c.trip_id)
        .group_by(table.c.trip_id, table.c.version)
        .having(func.count() > 1)
    )
    for trip_id in set(duplicate_trips):
        current = conn.execute(
            select(Trip.version, Trip.itinerary).where(Trip.id == trip_id)
        ).one_or_none()
        rows = conn.execute(
            select(table).where(table.c.trip_id == trip_id)
            .order_by(table.c.version, table.c.created_at.desc().nulls_last(), table.c.id.desc())
        ).mappings().all()
        last_version = max(rows[-1]["version"], current.version if current else 0)
        for number, group in groupby(rows, key=lambda row: row["version"]):
            revisions = list(group)
            keeper = revisions[0]
            if current and current.version == number:
                keeper = next(
                    (row for row in revisions if row["itinerary"] == current.itinerary), keeper
                )
            for row in revisions:
                if row["id"] == keeper["id"]:
                    continue
                last_version += 1
                itinerary = row["itinerary"]
                values = {"version": last_version}
                if isinstance(itinerary, dict):
                    values["itinerary"] = {**itinerary, "version": last_version}
                label = f"原版本 {number} · "
                values["description"] = (label + (row["description"] or ""))[:500]
                conn.execute(update(table).where(table.c.id == row["id"]).values(**values))

    index.create(conn)
