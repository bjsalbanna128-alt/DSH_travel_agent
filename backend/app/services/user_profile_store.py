"""User profile store — long-term memory via SQLAlchemy + SQLite/PG."""

import logging
from typing import Optional

from sqlalchemy import select
from app.db.database import async_session
from app.db.models import UserProfile

logger = logging.getLogger(__name__)

PACE_WEIGHT = {"relaxed": 0.3, "moderate": 0.6, "intensive": 0.9}
PACE_REVERSE = {0.3: "relaxed", 0.6: "moderate", 0.9: "intensive"}


def _closest_pace(score: float) -> str:
    """Map a numeric pace score back to a label."""
    if score <= 0.4:
        return "relaxed"
    elif score <= 0.7:
        return "moderate"
    return "intensive"


def _build_profile_context(profile: UserProfile) -> str:
    """Convert a UserProfile row into a natural-language context string."""
    parts: list[str] = []

    if profile.interest_tags:
        parts.append(f"偏好类型：{'、'.join(profile.interest_tags[:5])}")
    if profile.pace_preference:
        parts.append(f"旅行节奏：{profile.pace_preference}")
    if profile.cuisine_preferences:
        parts.append(f"饮食偏好：{'、'.join(profile.cuisine_preferences[:5])}")
    if profile.avg_budget_per_day_cny and profile.avg_budget_per_day_cny > 0:
        parts.append(f"日均预算约{profile.avg_budget_per_day_cny:.0f}元")
    if profile.travel_count > 0:
        parts.append(f"历史旅行{profile.travel_count}次")

    return "。".join(parts) if parts else ""


async def get_profile_context(user_id: str) -> str:
    """Load user profile and return a natural-language context string."""
    if not user_id or user_id == "anonymous":
        return ""

    try:
        async with async_session() as db:
            result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                return ""
            return _build_profile_context(profile)
    except Exception as e:
        logger.warning(f"Failed to load profile for {user_id}: {e}")
        return ""


async def upsert_profile(user_id: str, data: dict) -> None:
    """Insert or update a user profile."""
    if not user_id or user_id == "anonymous":
        return

    try:
        async with async_session() as db:
            result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()

            if profile is None:
                profile = UserProfile(user_id=user_id)
                db.add(profile)

            for key, value in data.items():
                if hasattr(profile, key):
                    setattr(profile, key, value)

            await db.commit()
            logger.info(f"Profile updated for {user_id}")
    except Exception as e:
        logger.error(f"Failed to upsert profile for {user_id}: {e}")


async def update_from_trip(
    user_id: str,
    travel_request: dict,
    itinerary: dict | None = None,
    feedback_score: float = 0.0,
) -> None:
    """Learn user preferences from a completed trip using EMA smoothing."""
    if not user_id or user_id == "anonymous":
        return

    req = travel_request or {}
    prefs: list[str] = req.get("preferences", [])
    pace: str = req.get("pace", "moderate")
    budget_total = float(req.get("budget", {}).get("total_cny", 0) or 0)
    days = max(req.get("days", 1), 1)

    try:
        async with async_session() as db:
            result = await db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                profile = UserProfile(user_id=user_id)
                db.add(profile)

            # Interest tags: merge and dedup (top 10)
            existing_tags = list(profile.interest_tags or [])
            for tag in prefs:
                if tag not in existing_tags:
                    existing_tags.append(tag)
            profile.interest_tags = existing_tags[:10]

            # Pace: EMA smooth
            old_pace_score = PACE_WEIGHT.get(profile.pace_preference, 0.6)
            new_pace_score = PACE_WEIGHT.get(pace, 0.6)
            smoothed = old_pace_score * 0.7 + new_pace_score * 0.3
            profile.pace_preference = _closest_pace(smoothed)

            # Budget: rolling average
            old_avg = profile.avg_budget_per_day_cny or 0
            count = profile.travel_count or 0
            new_daily = budget_total / days if budget_total > 0 else 0
            if new_daily > 0:
                profile.avg_budget_per_day_cny = (
                    (old_avg * count + new_daily) / (count + 1)
                ) if count > 0 else new_daily

            # Destinations
            dests: list[dict] = list(profile.frequent_destinations or [])
            dest_name = req.get("destination", "")
            if dest_name:
                found = False
                for d in dests:
                    if d.get("city") == dest_name:
                        d["count"] = d.get("count", 0) + 1
                        found = True
                        break
                if not found:
                    dests.append({"city": dest_name, "count": 1})
                dests.sort(key=lambda x: x.get("count", 0), reverse=True)
                profile.frequent_destinations = dests[:10]

            # Feedback
            scores = list(profile.feedback_scores or [])
            if feedback_score > 0:
                scores.append(feedback_score)
                profile.feedback_scores = scores[-20:]  # keep last 20

            # Cuisine preferences from itinerary restaurants
            if itinerary:
                cuisines: list[str] = list(profile.cuisine_preferences or [])
                for dp in (itinerary.get("day_plans") or []):
                    for meal_key in ("lunch", "dinner"):
                        meal = dp.get(meal_key)
                        if meal and meal.get("cuisine"):
                            c = meal["cuisine"]
                            if c not in cuisines:
                                cuisines.append(c)
                profile.cuisine_preferences = cuisines[:10]

            profile.travel_count = (profile.travel_count or 0) + 1

            await db.commit()
            logger.info(
                f"Profile learned from trip: {user_id}, "
                f"pace={profile.pace_preference}, trips={profile.travel_count}"
            )
    except Exception as e:
        logger.error(f"Failed to update profile from trip: {e}")
