from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Purpose = Literal["charter", "airport_transfer"]
ModelCode = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
Identifier = Annotated[str, Field(min_length=1, max_length=36)]
LocalTime = Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]


class FleetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FleetModelInput(FleetInput):
    code: ModelCode
    name: Annotated[str, Field(min_length=1, max_length=80)]


class FleetModelName(FleetInput):
    name: Annotated[str, Field(min_length=1, max_length=80)]


class RosterInput(FleetInput):
    supplier_id: Identifier
    status: Literal["active", "inactive"] = "active"
    notes: str = Field("", max_length=1000)


class VehicleInput(RosterInput):
    plate_no: Annotated[str, Field(min_length=1, max_length=16)]
    model_code: ModelCode
    seats: int = Field(strict=True, ge=1, le=100)
    luggage: int = Field(strict=True, ge=0, le=100)


class DriverInput(RosterInput):
    name: Annotated[str, Field(min_length=1, max_length=50)]
    phone: Annotated[str, Field(min_length=1, max_length=32)]
    license_type: str = Field("", max_length=16)
    service_cities: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(min_length=1, max_length=20)
    model_codes: list[ModelCode] = Field(min_length=1, max_length=30)


class VehicleSelection(FleetInput):
    service_key: Annotated[str, Field(pattern=r"^vehicle:[1-9][0-9]{0,4}:(charter|airport_transfer)$")]
    start_time: LocalTime | None = None
    pickup: str = Field("", max_length=160)
    dropoff: str = Field("", max_length=160)
    passengers: int = Field(strict=True, ge=1, le=500)
    luggage: int = Field(0, strict=True, ge=0, le=500)


class FleetQuoteRequest(VehicleSelection):
    trip_id: Identifier
    departure_date: date | None = None
    product_id: Identifier | None = None


class VehicleLeg(BaseModel):
    origin: str
    destination: str
    distance_km: float | None = None
    duration_minutes: int | None = None


class VehicleOffer(BaseModel):
    service_key: str
    purpose: Purpose
    day: int
    service_date: date | None = None
    pickup: str = ""
    dropoff: str = ""
    suggested_start: str | None = None
    duration_minutes: int
    legs: list[VehicleLeg] = Field(default_factory=list)
    recommended: bool = False
    reason: str
    models: list[dict] = Field(default_factory=list)
