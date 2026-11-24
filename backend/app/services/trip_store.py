"""Trip persistence service — save/load trips from SQLite."""

import logging
from datetime import datetime

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Trip, TripVersion

logger = logging.getLogger(__name__)


class TripThreadConflict(Exception):
    """The thread ID is already assigned to another account's trip."""


async def save_trip(
    db: AsyncSession,
    thread_id: str,
    trip_data: dict,
    user_id: str,
) -> Trip:
    """Create or update a trip record."""
    # Check if trip already exists for this thread_id
    result = await db.execute(
        select(Trip).where(Trip.thread_id == thread_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None and existing.user_id != user_id:
        raise TripThreadConflict

    itinerary = trip_data.get("itinerary", trip_data)
    travel_request = trip_data.get("travel_request", {})

    if existing:
        existing.title = itinerary.get("title", existing.title)
        existing.destination = itinerary.get("destination", existing.destination)
        existing.duration_days = itinerary.get("duration_days", existing.duration_days)
        existing.budget_total = itinerary.get("total_budget_estimate_cny", existing.budget_total)
        existing.itinerary = itinerary
        existing.travel_request = travel_request
        existing.version = itinerary.get("version", existing.version)
        existing.updated_at = datetime.utcnow()
        trip = existing
        logger.info(f"[TripStore] Updated trip {trip.id} (v{trip.version})")
    else:
        trip = Trip(
            thread_id=thread_id,
            user_id=user_id,
            title=itinerary.get("title", ""),
            destination=itinerary.get("destination", ""),
            duration_days=itinerary.get("duration_days", 0),
            budget_total=itinerary.get("total_budget_estimate_cny", 0.0),
            itinerary=itinerary,
            travel_request=travel_request,
            version=itinerary.get("version", 1),
            status="completed",
        )
        db.add(trip)
        logger.info(f"[TripStore] Created trip {trip.id}")

    await db.flush()

    # Save version snapshot
    version = TripVersion(
        trip_id=trip.id,
        version=trip.version,
        itinerary=itinerary,
        description=f"Version {trip.version}",
    )
    db.add(version)
    await db.flush()

    return trip


async def _find_owned_trip(db: AsyncSession, trip_id: str, user_id: str) -> Trip | None:
    result = await db.execute(select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id))
    return result.scalar_one_or_none()


async def get_trip(db: AsyncSession, trip_id: str, *, user_id: str) -> dict | None:
    """Load a single trip by ID."""
    trip = await _find_owned_trip(db, trip_id, user_id)
    if not trip:
        return None
    return _trip_to_dict(trip)


async def list_trips(
    db: AsyncSession,
    user_id: str,
    limit: int = 20,
) -> list[dict]:
    """List recent trips for a user."""
    result = await db.execute(
        select(Trip)
        .where(Trip.user_id == user_id)
        .order_by(desc(Trip.updated_at))
        .limit(limit)
    )
    trips = result.scalars().all()
    return [_trip_to_dict(t) for t in trips]


async def get_trip_versions(
    db: AsyncSession, trip_id: str, *, user_id: str
) -> list[dict] | None:
    """List all versions of a trip."""
    if await _find_owned_trip(db, trip_id, user_id) is None:
        return None
    result = await db.execute(
        select(TripVersion)
        .where(TripVersion.trip_id == trip_id)
        .order_by(desc(TripVersion.version))
    )
    versions = result.scalars().all()
    return [
        {
            "id": v.id,
            "version": v.version,
            "description": v.description,
            "created_at": v.created_at.isoformat() if v.created_at else "",
        }
        for v in versions
    ]


async def rollback_trip(
    db: AsyncSession, trip_id: str, version: int, *, user_id: str
) -> dict | None:
    """Rollback trip to a specific version."""
    trip = await _find_owned_trip(db, trip_id, user_id)
    if trip is None:
        return None

    # Find the version
    result = await db.execute(
        select(TripVersion)
        .where(TripVersion.trip_id == trip_id, TripVersion.version == version)
    )
    ver = result.scalar_one_or_none()
    if not ver:
        return None

    # Update trip with version's itinerary
    trip.itinerary = ver.itinerary
    trip.version = version
    trip.updated_at = datetime.utcnow()
    await db.flush()

    return _trip_to_dict(trip)


async def update_trip(
    db: AsyncSession, trip_id: str, itinerary: dict, *, user_id: str
) -> dict | None:
    """Save edited itinerary as a new version."""
    trip = await _find_owned_trip(db, trip_id, user_id)
    if not trip:
        return None

    new_version = (trip.version or 0) + 1

    trip.itinerary = itinerary
    trip.title = itinerary.get("title", trip.title)
    trip.duration_days = itinerary.get("duration_days", trip.duration_days)
    trip.budget_total = itinerary.get("total_budget_estimate_cny", trip.budget_total)
    trip.version = new_version
    trip.updated_at = datetime.utcnow()
    await db.flush()

    version = TripVersion(
        trip_id=trip.id,
        version=new_version,
        itinerary=itinerary,
        description=f"手动编辑 v{new_version}",
    )
    db.add(version)
    await db.flush()

    logger.info(f"[TripStore] Updated trip {trip.id} to v{new_version}")
    return _trip_to_dict(trip)


def _trip_to_dict(trip: Trip) -> dict:
    return {
        "id": trip.id,
        "user_id": trip.user_id,
        "thread_id": trip.thread_id,
        "title": trip.title,
        "destination": trip.destination,
        "duration_days": trip.duration_days,
        "budget_total": trip.budget_total,
        "status": trip.status,
        "travel_request": trip.travel_request,
        "itinerary": trip.itinerary,
        "version": trip.version,
        "created_at": trip.created_at.isoformat() if trip.created_at else "",
        "updated_at": trip.updated_at.isoformat() if trip.updated_at else "",
    }
