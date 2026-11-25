"""Explicit member write fields and privacy-safe read projections."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, StrictBool, model_validator

from app.schemas.admin_resources import ResourceBody
from app.schemas.support import UtcTimestamp

DocumentType = Literal["id_card", "passport", "hong_kong_macau", "taiwan", "other"]
Gender = Literal["female", "male", "other", "undisclosed"]
PointKind = Literal["payment", "refund", "expiry"]


class ContactPatch(ResourceBody):
    phone: SecretStr | None = Field(default=None, max_length=48)
    document_type: DocumentType | None = None
    document_number: SecretStr | None = Field(default=None, max_length=80)
    clear_document: StrictBool = False

    @model_validator(mode="after")
    def check_document_pair(self):
        document_fields = {"document_type", "document_number"} & self.model_fields_set
        if document_fields and (self.clear_document or not self.document_type or not self.document_number):
            raise ValueError("Invalid document update")
        return self


class ProfilePatch(ContactPatch):
    nickname: str | None = Field(default=None, min_length=1, max_length=60)
    avatar_url: str | None = Field(default=None, max_length=500)
    birthday: date | None = None
    gender: Gender | None = None
    real_name: str | None = Field(default=None, min_length=1, max_length=100)


class TravelerPatch(ContactPatch):
    real_name: str | None = Field(default=None, min_length=1, max_length=100)
    relationship: str | None = Field(default=None, min_length=1, max_length=30)
    is_default: StrictBool | None = None

    @model_validator(mode="after")
    def check_required_fields(self):
        for field in self.model_fields_set & {"real_name", "relationship", "is_default"}:
            if getattr(self, field) is None:
                raise ValueError("Traveler fields cannot be null")
        return self


class TravelerCreate(TravelerPatch):
    real_name: str = Field(min_length=1, max_length=100)
    relationship: str = Field(min_length=1, max_length=30)
    is_default: StrictBool = False


class ContactView(BaseModel):
    real_name: str | None = None
    phone_mask: str | None = None
    document_type: DocumentType | None = None
    document_mask: str | None = None
    document_filled: bool = False


class ProfileView(ContactView):
    exists: bool = False
    nickname: str | None = None
    avatar_url: str | None = None
    birthday: date | None = None
    gender: Gender | None = None


class TravelerView(ContactView):
    id: str
    relationship: str
    is_default: bool


class MemberSummary(BaseModel):
    id: str
    username: str
    registered_at: UtcTimestamp | None
    profile_complete: bool
    effective_balance: int


class ExpiringLot(BaseModel, from_attributes=True):
    order_id: str
    remaining_points: int
    expires_at: UtcTimestamp


class PointOverview(BaseModel):
    effective_balance: int
    as_of: UtcTimestamp
    expiring: list[ExpiringLot]


class PointEntry(BaseModel, from_attributes=True):
    id: str
    kind: PointKind
    order_id: str
    refund_id: str | None
    delta: int
    amount_fen: int | None
    occurred_at: UtcTimestamp
    recorded_at: UtcTimestamp
    book_balance_after: int


class MemberDetail(MemberSummary):
    profile: ProfileView
    travelers: list[TravelerView]
    preferences: dict | None
    points: PointOverview
