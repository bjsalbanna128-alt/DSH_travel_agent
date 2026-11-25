"""Operator and reader contracts for homepage recommendations."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.itinerary_templates import Visibility

ImageMime = Literal["image/jpeg", "image/png", "image/webp"]


class RecommendationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=40)
    place: str = Field("", max_length=100)
    short_text: str = Field("", max_length=200)
    display_order: int = Field(100, strict=True, ge=0, le=2_147_483_647)


class SaveRecommendationDraft(RecommendationDraft):
    expected_revision: int = Field(strict=True, ge=1)


class CoverInfo(BaseModel):
    id: str
    url: str
    mime: ImageMime
    width: int
    height: int
    size_bytes: int


class RecommendationDetail(RecommendationDraft):
    id: str
    cover: CoverInfo | None
    visibility: Visibility
    revision: int
    published_version: int
    has_unpublished_changes: bool
    updated_at: datetime
    message: str | None = None


class ReaderRecommendation(BaseModel):
    id: str
    version: int
    title: str
    place: str
    short_text: str
    cover_url: str
