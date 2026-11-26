"""Validation and response contracts for the content layer."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ContentKind = Literal["attraction", "hotel"]
ContentStatus = Literal["draft", "published", "unpublished"]

Name = Annotated[str, Field(min_length=1, max_length=160)]
City = Annotated[str, Field(min_length=1, max_length=100)]
Rating = Annotated[float, Field(ge=0, le=5)]
ShortText = Annotated[str, Field(max_length=2000)]


class ContentBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContentCreate(ContentBody):
    kind: ContentKind
    city: City
    name: Name
    category: Annotated[str, Field(max_length=32)] = ""
    rating: Rating | None = None
    visit_duration_hours: Annotated[float, Field(gt=0, le=48)] | None = None
    opening_hours: Annotated[str, Field(max_length=64)] = ""
    ticket_price_hint_cny: Annotated[float, Field(ge=0, le=1_000_000)] | None = None
    star_rating: Annotated[int, Field(ge=1, le=5)] | None = None
    landmark_hint: Annotated[str, Field(max_length=160)] = ""
    lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    lng: Annotated[float, Field(ge=-180, le=180)] | None = None
    tags: Annotated[list[str], Field(max_length=12)] = Field(default_factory=list)
    suitable_for: Annotated[list[str], Field(max_length=12)] = Field(default_factory=list)
    description: ShortText = ""
    highlights: Annotated[list[str], Field(max_length=10)] = Field(default_factory=list)
    cover_image_url: Annotated[str, Field(max_length=500)] = ""


class ContentPatch(ContentBody):
    city: City | None = None
    name: Name | None = None
    category: Annotated[str, Field(max_length=32)] | None = None
    rating: Rating | None = None
    visit_duration_hours: Annotated[float, Field(gt=0, le=48)] | None = None
    opening_hours: Annotated[str, Field(max_length=64)] | None = None
    ticket_price_hint_cny: Annotated[float, Field(ge=0, le=1_000_000)] | None = None
    star_rating: Annotated[int, Field(ge=1, le=5)] | None = None
    landmark_hint: Annotated[str, Field(max_length=160)] | None = None
    lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    lng: Annotated[float, Field(ge=-180, le=180)] | None = None
    tags: Annotated[list[str], Field(max_length=12)] | None = None
    suitable_for: Annotated[list[str], Field(max_length=12)] | None = None
    description: ShortText | None = None
    highlights: Annotated[list[str], Field(max_length=10)] | None = None
    cover_image_url: Annotated[str, Field(max_length=500)] | None = None


class BoundProduct(BaseModel):
    id: str
    name: str
    type: str
    status: str


class ContentResponse(ContentBody):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: ContentKind
    city: str
    name: str
    category: str
    rating: float | None
    visit_duration_hours: float | None
    opening_hours: str
    ticket_price_hint_cny: float | None
    star_rating: int | None
    landmark_hint: str
    lat: float | None
    lng: float | None
    tags: list[str]
    suitable_for: list[str]
    description: str
    highlights: list[str]
    cover_image_url: str
    source: str
    status: ContentStatus
    created_at: datetime
    updated_at: datetime
    products: list[BoundProduct] = Field(default_factory=list)


class ContentListPage(BaseModel):
    items: list[ContentResponse]
    total: int


class BindProducts(ContentBody):
    product_ids: Annotated[list[str], Field(max_length=50)] = Field(default_factory=list)


class SyncResult(BaseModel):
    added: int = 0
    updated: int = 0
    removed: int = 0
