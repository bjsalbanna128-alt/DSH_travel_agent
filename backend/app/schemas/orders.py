"""Request and response contracts for tourist orders and operator review."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

OrderStatus = Literal[
    "pending_payment", "paid_pending_review", "confirmed", "cancel_requested", "cancelled", "completed",
]
FundStatus = Literal["unpaid", "processing", "paid", "refunding", "refunded", "refund_failed"]
SelectedKind = Literal["hotel", "ticket"]


class OrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SelectedItem(OrderBody):
    kind: SelectedKind = "ticket"
    product_id: Annotated[str, Field(min_length=1, max_length=36)]
    service_date: date | None = None
    check_in: date | None = None
    check_out: date | None = None
    quantity: Annotated[int, Field(ge=1, le=30)] = 1


class TravelerInput(OrderBody):
    name: Annotated[str, Field(min_length=1, max_length=50)]
    document_type: Annotated[str, Field(max_length=16)] = ""
    document_number: Annotated[str, Field(max_length=64)] = ""
    phone: Annotated[str, Field(max_length=32)] = ""
    is_lead: bool = False


class CreateOrder(OrderBody):
    contact_name: Annotated[str, Field(min_length=1, max_length=50)]
    contact_phone: Annotated[str, Field(min_length=1, max_length=32)]
    trip_id: Annotated[str, Field(max_length=36)] | None = None
    travelers: Annotated[list[TravelerInput], Field(min_length=1, max_length=20)]
    selected: Annotated[list[SelectedItem], Field(min_length=1, max_length=20)]


class PayOrder(OrderBody):
    idempotency_key: Annotated[str, Field(min_length=1, max_length=80)]


class CancelOrder(OrderBody):
    reason: Annotated[str, Field(max_length=500)] = ""


class ReviewDecision(OrderBody):
    note: Annotated[str, Field(max_length=500)] = ""


class RejectDecision(OrderBody):
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class ResolveCancelRequest(OrderBody):
    approve: bool
    note: Annotated[str, Field(max_length=500)] = ""


class ItemView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    product_name: str
    product_type: str
    attributes: dict
    service_date: date
    quantity: int
    unit_sale_fen: int
    unit_cost_fen: int
    subtotal_sale_fen: int


class TravelerView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    document_type: str
    document_mask: str
    phone_mask: str
    is_lead: bool


class EventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    from_status: str | None
    to_status: str | None
    actor_name: str | None
    reason: str
    created_at: datetime


class PaymentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    amount_fen: int
    event_id: str
    paid_at: datetime


class RefundView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    refund_no: str
    amount_fen: int
    status: str
    attempts: int
    last_error: str
    processed_at: datetime | None


class OrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_no: str
    status: OrderStatus
    fund_status: FundStatus
    total_sale_fen: int
    expires_at: datetime
    created_at: datetime
    waiting_minutes: int = 0


class OrderDetail(OrderSummary):
    user_id: str
    trip_id: str | None
    contact_name: str
    contact_phone: str
    total_cost_fen: int
    review_note: str
    cancel_reason: str
    cancelled_at: datetime | None
    items: list[ItemView]
    travelers: list[TravelerView]
    events: list[EventView]
    payments: list[PaymentView]
    refunds: list[RefundView]


class OrderPage(BaseModel):
    items: list[OrderSummary]
    total: int


class SweepResult(BaseModel):
    expired: int = 0
    refunds: int = 0
