"""Response contracts for the read-only operator trip query."""

from datetime import datetime

from pydantic import BaseModel, Field


class TripVersionSummary(BaseModel):
    version: int
    description: str = ""
    created_at: datetime | None = None
    is_current: bool = False
    is_confirmed: bool = False


class TripSummary(BaseModel):
    id: str
    username: str
    title: str
    destination: str
    duration_days: int
    budget_total: float
    version: int
    confirmed_version: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TripDetail(TripSummary):
    status: str = ""
    travel_request: dict = Field(default_factory=dict)
    itinerary: dict = Field(default_factory=dict)
    versions: list[TripVersionSummary] = Field(default_factory=list)


class TripVersionDetail(BaseModel):
    trip_id: str
    version: int
    description: str = ""
    created_at: datetime | None = None
    is_current: bool = False
    is_confirmed: bool = False
    itinerary: dict = Field(default_factory=dict)
