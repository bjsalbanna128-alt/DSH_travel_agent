from datetime import timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.support import UtcTimestamp


class SaveDelivery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0, strict=True)
    enabled: bool = Field(strict=True)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def check_window(self):
        if self.starts_at:
            self.starts_at = self.starts_at.astimezone(timezone.utc)
        if self.ends_at:
            self.ends_at = self.ends_at.astimezone(timezone.utc)
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValueError("开始时间必须早于结束时间")
        return self


class DeliveryEntry(BaseModel):
    id: str
    title: str
    display_order: int
    enabled: bool
    starts_at: UtcTimestamp | None
    ends_at: UtcTimestamp | None
    revision: int
    updated_by: str | None
    operator_name: str | None
    updated_at: UtcTimestamp
    status: Literal["content_unpublished", "paused", "scheduled", "ended", "active"]


class SelectableRecommendation(BaseModel):
    id: str
    title: str
    display_order: int
