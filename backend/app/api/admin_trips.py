"""Read-only operator trip query routes."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession as DB
from app.api.support import Page
from app.schemas.admin_resources import ResourcePage
from app.schemas.admin_trips import TripDetail, TripSummary, TripVersionDetail
from app.services import admin_trips

router = APIRouter(prefix="/trips")


@router.get("", response_model=ResourcePage[TripSummary])
async def trip_list(
    db: DB, page: Page,
    username: Annotated[str, Query(max_length=50)] = "",
    destination: Annotated[str, Query(max_length=100)] = "",
    start: date | None = None, end: date | None = None,
):
    return await admin_trips.list_trips(
        db, username=username, destination=destination, start=start, end=end,
        offset=page.offset, limit=page.limit,
    )


@router.get("/{trip_id}", response_model=TripDetail)
async def trip_detail(trip_id: str, db: DB):
    return await admin_trips.trip_detail(db, trip_id)


@router.get("/{trip_id}/versions/{version}", response_model=TripVersionDetail)
async def trip_version(trip_id: str, version: int, db: DB):
    return await admin_trips.trip_version(db, trip_id, version)
