"""Separate contracts for editable drafts and reader-safe published templates."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.admin_resources import ProductType, ResourceId

Visibility = Literal["draft", "published", "unpublished"]
ActivityCategory = Literal["sightseeing", "dining", "accommodation", "transport", "other"]

MAX_DAYS = 30
MAX_ACTIVITIES = 30
MAX_TAGS = 12


class TemplateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TemplateBasics(TemplateBody):
    title: str = Field(min_length=1, max_length=160)
    destination: str = Field("", max_length=100)
    tags: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(default_factory=list, max_length=MAX_TAGS)
    description: str = Field("", max_length=2000)
    tips: str = Field("", max_length=3000)


class ActivityDraft(TemplateBody):
    time: str = Field("", max_length=60)
    name: str = Field("", max_length=160)
    category: ActivityCategory | None = None
    description: str = Field("", max_length=1000)
    product_id: ResourceId | None = None


class DayDraft(TemplateBody):
    theme: str = Field("", max_length=120)
    activities: list[ActivityDraft] = Field(default_factory=list, max_length=MAX_ACTIVITIES)
    notes: str = Field("", max_length=1500)


class TemplateDraft(TemplateBasics):
    days: list[DayDraft] = Field(default_factory=list, max_length=MAX_DAYS)


class RevisionRequest(TemplateBody):
    expected_revision: int = Field(strict=True, ge=1)


class SaveDraft(RevisionRequest):
    draft: TemplateDraft


class ProductSnapshot(BaseModel):
    id: str
    name: str
    type: ProductType


class PublishedActivity(BaseModel):
    time: str
    name: str
    category: ActivityCategory
    description: str
    product: ProductSnapshot | None


class PublishedDay(BaseModel):
    day: int
    theme: str
    activities: list[PublishedActivity]
    notes: str


class PublishedContent(TemplateBasics):
    days: list[PublishedDay]


class TemplateSummary(BaseModel):
    id: str
    title: str
    destination: str
    days_count: int
    visibility: Visibility
    published_version: int
    has_unpublished_changes: bool
    updated_at: datetime
    revision: int


class TemplateDetail(TemplateSummary):
    draft: TemplateDraft
    linked_products: list[ProductSnapshot]
    created_by: str
    updated_by: str
    created_at: datetime
    published_at: datetime | None
    message: str | None = None


class ReaderTemplateSummary(BaseModel):
    id: str
    version: int
    title: str
    destination: str
    days_count: int
    tags: list[str]
    description: str
    published_at: datetime


class ReaderTemplateDetail(ReaderTemplateSummary):
    tips: str
    days: list[PublishedDay]


class TemplateFieldIssue(BaseModel):
    path: list[str | int]
    message: str
