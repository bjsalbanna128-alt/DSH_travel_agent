"""Read-only operator views over confirmed tourist trips.

Trips are only visible once the tourist confirmed them. Drafts are filtered out of
every query, and an unknown or draft id yields the same 404 so their existence is
never leaked.
"""

from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Trip, TripVersion, User
from app.schemas.admin_resources import ResourcePage
from app.schemas.admin_trips import TripDetail, TripSummary, TripVersionDetail, TripVersionSummary
from app.services.member_points import BEIJING

COMPLETED = "completed"
NOT_FOUND = "行程不存在。"


def _midnight(day: date) -> datetime:
    """Local midnight expressed as the naive UTC value used by the trip columns."""
    clock = datetime.combine(day, time.min, tzinfo=BEIJING).astimezone(timezone.utc)
    return clock.replace(tzinfo=None)


def _date_filters(start: date | None, end: date | None) -> list:
    if start and end and start > end:
        raise HTTPException(422, "开始日期不能晚于结束日期。")
    filters = []
    if start and start > date.min:
        filters.append(Trip.updated_at >= _midnight(start))
    if end and end < date.max:
        filters.append(Trip.updated_at < _midnight(end + timedelta(days=1)))
    return filters


def _summary(trip: Trip, username: str) -> TripSummary:
    return TripSummary(
        id=trip.id, username=username, title=trip.title or "", destination=trip.destination or "",
        duration_days=trip.duration_days or 0, budget_total=float(trip.budget_total or 0),
        version=trip.version or 0, confirmed_version=trip.confirmed_version,
        created_at=trip.created_at, updated_at=trip.updated_at,
    )


async def _confirmed_trip(db: AsyncSession, trip_id: str) -> tuple[Trip, str]:
    row = (await db.execute(
        _confirmed(select(Trip, User.username)).where(Trip.id == trip_id)
    )).one_or_none()
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row[0], row[1]


def _confirmed(query):
    return query.select_from(Trip).join(User, User.id == Trip.user_id).where(Trip.status == COMPLETED)


async def count_confirmed_trips(db: AsyncSession, *filters) -> int:
    return await db.scalar(_confirmed(select(func.count())).where(*filters)) or 0


async def list_trips(
    db: AsyncSession, *, username: str, destination: str, start: date | None, end: date | None,
    offset: int, limit: int,
) -> ResourcePage[TripSummary]:
    filters = _date_filters(start, end)
    if username.strip():
        filters.append(User.username.icontains(username.strip(), autoescape=True))
    if destination.strip():
        filters.append(Trip.destination.icontains(destination.strip(), autoescape=True))

    total = await count_confirmed_trips(db, *filters)
    rows = await db.execute(
        _confirmed(select(Trip, User.username)).where(*filters)
        .order_by(Trip.updated_at.desc(), Trip.id.desc()).offset(offset).limit(limit)
    )
    return ResourcePage[TripSummary](
        items=[_summary(trip, name) for trip, name in rows], total=total or 0,
    )


async def _versions(db: AsyncSession, trip: Trip) -> list[TripVersionSummary]:
    rows = await db.scalars(
        select(TripVersion).where(TripVersion.trip_id == trip.id).order_by(TripVersion.version.desc())
    )
    return [
        TripVersionSummary(
            version=row.version, description=row.description or "", created_at=row.created_at,
            is_current=row.version == trip.version,
            is_confirmed=row.version is not None and row.version == trip.confirmed_version,
        )
        for row in rows
    ]


async def trip_detail(db: AsyncSession, trip_id: str) -> TripDetail:
    trip, username = await _confirmed_trip(db, trip_id)
    summary = _summary(trip, username)
    return TripDetail(
        **summary.model_dump(), status=trip.status,
        travel_request=trip.travel_request or {}, itinerary=trip.itinerary or {},
        versions=await _versions(db, trip),
    )


async def trip_version(db: AsyncSession, trip_id: str, version: int) -> TripVersionDetail:
    trip, _ = await _confirmed_trip(db, trip_id)
    row = await db.scalar(
        select(TripVersion).where(TripVersion.trip_id == trip_id, TripVersion.version == version)
    )
    if row is None:
        raise HTTPException(404, "版本不存在。")
    return TripVersionDetail(
        trip_id=trip_id, version=row.version, description=row.description or "",
        created_at=row.created_at, is_current=row.version == trip.version,
        is_confirmed=row.version == trip.confirmed_version, itinerary=row.itinerary or {},
    )
