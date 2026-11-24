"""REST API routes for trips, versions, history, and profile."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db, async_session
from app.db.models import UserProfile
from app.api.deps import CurrentUserId
from app.services import trip_store
from app.services.planning_review import DraftDecision, ReviewError, remember_confirmed_trip, review_draft

router = APIRouter(prefix="/v1", tags=["api"])


@router.get("/trips/{trip_id}")
async def get_trip(trip_id: str, user_id: CurrentUserId, db: AsyncSession = Depends(get_db)):
    """Retrieve a trip by ID."""
    trip = await trip_store.get_trip(db, trip_id, user_id=user_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.get("/trips")
async def list_trips(
    user_id: CurrentUserId,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List recent trips for a user."""
    trips = await trip_store.list_trips(db, user_id=user_id, limit=limit)
    return {"trips": trips, "total": len(trips)}


@router.post("/trips/{trip_id}/decision")
async def decide_trip(
    trip_id: str, body: DraftDecision, user_id: CurrentUserId, background: BackgroundTasks
):
    try:
        trip, newly_confirmed = await review_draft(async_session, user_id, body, trip_id=trip_id)
    except ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if newly_confirmed:
        background.add_task(remember_confirmed_trip, user_id, trip)
    return trip


@router.get("/trips/{trip_id}/versions")
async def list_versions(trip_id: str, user_id: CurrentUserId, db: AsyncSession = Depends(get_db)):
    """List itinerary versions for a trip."""
    versions = await trip_store.get_trip_versions(db, trip_id, user_id=user_id)
    if versions is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return {"trip_id": trip_id, "versions": versions}


@router.post("/trips/{trip_id}/rollback/{version}")
async def rollback_trip(
    trip_id: str,
    version: int,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
):
    """Roll back to a specific itinerary version."""
    try:
        trip = await trip_store.rollback_trip(db, trip_id, version, user_id=user_id)
    except trip_store.TripRevisionConflict as exc:
        raise HTTPException(status_code=409, detail="行程待确认或版本已变化，请刷新后重试") from exc
    if not trip:
        raise HTTPException(status_code=404, detail="Trip or version not found")
    return trip


@router.put("/trips/{trip_id}")
async def update_trip(
    trip_id: str, body: dict, user_id: CurrentUserId, db: AsyncSession = Depends(get_db)
):
    """Save edited itinerary as a new version."""
    itinerary = body.get("itinerary")
    if not itinerary:
        raise HTTPException(status_code=400, detail="itinerary is required")
    try:
        trip = await trip_store.update_trip(db, trip_id, itinerary, user_id=user_id)
    except trip_store.TripRevisionConflict as exc:
        raise HTTPException(status_code=409, detail="行程待确认或版本已变化，请刷新后重试") from exc
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.get("/profile")
async def get_profile(
    user_id: CurrentUserId,
):
    """Get user travel preference profile."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                return {"profile": None, "user_id": user_id}
            return {
                "profile": {
                    "user_id": profile.user_id,
                    "interest_tags": profile.interest_tags or [],
                    "pace_preference": profile.pace_preference or "moderate",
                    "preferred_hotel_stars": profile.preferred_hotel_stars or 4,
                    "cuisine_preferences": profile.cuisine_preferences or [],
                    "dietary_restrictions": profile.dietary_restrictions or [],
                    "avg_budget_per_day_cny": profile.avg_budget_per_day_cny or 0,
                    "frequent_destinations": profile.frequent_destinations or [],
                    "feedback_scores": profile.feedback_scores or [],
                    "travel_count": profile.travel_count or 0,
                    "updated_at": profile.updated_at.isoformat() if profile.updated_at else "",
                },
                "user_id": user_id,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
