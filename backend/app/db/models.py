"""SQLAlchemy ORM models for trip persistence."""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Float, DateTime, Index, JSON, Text
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON

from app.db.database import Base


def _gen_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_gen_id)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Trip(Base):
    __tablename__ = "trips"

    id = Column(String(36), primary_key=True, default=_gen_id)
    user_id = Column(String(36), default="anonymous")
    thread_id = Column(String(100), unique=True, nullable=False)
    title = Column(String(200), default="")
    destination = Column(String(100), default="")
    duration_days = Column(Integer, default=0)
    budget_total = Column(Float, default=0.0)
    status = Column(String(20), default="draft")  # draft | completed
    travel_request = Column(JSON, default=dict)
    itinerary = Column(JSON, default=dict)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TripVersion(Base):
    __tablename__ = "trip_versions"
    __table_args__ = (Index("uq_trip_versions_trip_id_version", "trip_id", "version", unique=True),)

    id = Column(String(36), primary_key=True, default=_gen_id)
    trip_id = Column(String(36), nullable=False)
    version = Column(Integer, nullable=False)
    itinerary = Column(JSON, default=dict)
    description = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id = Column(String(36), primary_key=True, default=lambda: "anonymous")
    interest_tags = Column(JSON, default=list)          # ["自然风光", "美食"]
    pace_preference = Column(String(20), default="moderate")
    preferred_hotel_stars = Column(Integer, default=4)
    cuisine_preferences = Column(JSON, default=list)    # ["川菜", "粤菜"]
    dietary_restrictions = Column(JSON, default=list)   # ["素食"]
    avg_budget_per_day_cny = Column(Float, default=0.0)
    frequent_destinations = Column(JSON, default=list)  # [{"city": "成都", "count": 3}]
    feedback_scores = Column(JSON, default=list)        # [4.0, 5.0, ...]
    travel_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
