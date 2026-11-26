from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.schemas.admin_resources import PoiReference, ResourceBody
from app.schemas.support import UtcTimestamp

RestrictionKind = Literal["closure", "reservation", "admission"]
RestrictionVisibility = Literal["draft", "published", "inactive"]
QualityResult = Literal["violation", "verify", "notice", "pass", "unchecked"]
QualityRule = Literal["closure", "reservation", "admission", "budget", "duration", "no_attractions", "lookup"]


class ScenicRule(ResourceBody):
    poi: PoiReference
    kind: RestrictionKind
    starts_on: date
    ends_on: date | None = None
    description: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    source_note: Annotated[str, StringConstraints(min_length=1, max_length=300)]

    @model_validator(mode="after")
    def check_rule(self):
        if self.poi.type != "attraction":
            raise ValueError("只能绑定景点 POI")
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("结束日不能早于开始日")
        return self


class SaveScenicRule(ScenicRule):
    expected_revision: int = Field(ge=1, strict=True)


class ScenicEntry(ScenicRule):
    id: str
    revision: int
    published_version: int
    published_revision: int | None
    has_unpublished_changes: bool
    visibility: RestrictionVisibility
    updated_by: str
    updated_at: UtcTimestamp


class QualityFinding(ResourceBody):
    rule: QualityRule
    result: Literal["violation", "verify", "notice"]
    reason: str
    day: int | None = None
    visit_date: date | None = None
    attraction: str | None = None
    restriction_id: str | None = None
    restriction_version: int | None = None
    matched_by: Literal["id", "unique_name", "ambiguous"] | None = None
    source_note: str | None = None
    description: str | None = None


class QualitySummary(ResourceBody):
    trip_id: str
    version: int
    destination: str
    stage: Literal["initial", "adjusted"] | None
    status: QualityResult
    checked_at: UtcTimestamp | None


class QualityDetail(QualitySummary):
    findings: list[QualityFinding]
