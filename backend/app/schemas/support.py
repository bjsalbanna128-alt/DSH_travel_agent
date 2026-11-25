"""Public and operator contracts for tickets and personal messages."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StrictBool

from app.schemas.admin_resources import ResourceBody, ResourcePage

MessageCode = Literal["trip.confirmed", "ticket.created", "ticket.closed"]
MessageTarget = Literal["trip_confirmation", "admin_ticket", "tourist_ticket"]
TicketCategory = Literal["inquiry", "complaint", "suggestion"]
TicketStatus = Literal["new", "processing", "closed"]
TicketPriority = Literal["low", "normal", "high"]


def _utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


UtcTimestamp = Annotated[datetime, AfterValidator(_utc_timestamp)]


class ExpectedRevision(ResourceBody):
    expected_revision: int = Field(strict=True, ge=1)


class ChangeMessageSetting(ExpectedRevision):
    enabled: StrictBool


class MessageSettingView(BaseModel):
    code: MessageCode
    name: str
    trigger: str
    audience: str
    channel: Literal["in_app"] = "in_app"
    enabled: bool
    revision: int
    updated_by: str | None
    updated_by_name: str | None
    updated_at: UtcTimestamp | None


class ConfirmationSummary(BaseModel):
    trip_id: str
    title: str
    version: int
    confirmed_at: UtcTimestamp
    member_id: str = ""
    username: str = ""
    destination: str = ""
    duration_days: int = 0
    total_budget_cny: float = 0.0
    travelers: dict | None = None
    current_version: int | None = None
    modified_after_confirm: bool = False


class InboxMessage(BaseModel):
    id: str
    code: MessageCode
    title: str
    body: str
    target_type: MessageTarget
    target_id: str
    target_version: int | None
    sent_at: UtcTimestamp
    read_at: UtcTimestamp | None


class InboxMessageDetail(InboxMessage):
    confirmation: ConfirmationSummary | None = None


class UnreadCount(BaseModel):
    unread_count: int


class ReadMessage(UnreadCount):
    message: InboxMessageDetail


class SubmitTicket(ResourceBody):
    category: TicketCategory
    subject: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=4000)


class CloseTicket(ExpectedRevision):
    result: str = Field(min_length=1, max_length=4000)


class ChangePriority(ExpectedRevision):
    priority: TicketPriority


class TicketSummary(BaseModel, from_attributes=True):
    id: str
    number: str
    category: TicketCategory
    subject: str
    status: TicketStatus
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class TicketHandlingView(BaseModel, from_attributes=True):
    round: int
    result: str | None
    completed_at: UtcTimestamp | None


class TicketDetail(TicketSummary):
    content: str
    handlings: list[TicketHandlingView]


class AccountLabel(BaseModel):
    id: str
    username: str


class AdminTicketSummary(TicketSummary):
    priority: TicketPriority
    revision: int
    submitter: AccountLabel
    assignee: AccountLabel | None


class AdminTicketHandling(TicketHandlingView):
    handler_id: str
    handler_name: str
    claimed_at: UtcTimestamp
    completed_by: str | None


class AdminTicketDetail(AdminTicketSummary):
    content: str
    order_id: str | None
    handlings: list[AdminTicketHandling]


class AdminTicketPage(ResourcePage[AdminTicketSummary]):
    assignees: list[AccountLabel]
