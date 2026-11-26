"""Request and response contracts for tourist orders and operator review."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.fleet import VehicleSelection
from app.schemas.support import UtcTimestamp

OrderStatus = Literal[
    "pending_payment", "paid_pending_review", "confirmed", "cancel_requested", "cancelled", "completed",
]
FundStatus = Literal["unpaid", "processing", "paid", "refunding", "refunded", "refund_failed"]
SelectedKind = Literal["hotel", "ticket", "vehicle"]


class OrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DayQuote(OrderBody):
    service_date: date
    token: Annotated[str, Field(pattern="^[a-f0-9]{64}$")]


class SelectedItem(OrderBody):
    kind: SelectedKind
    product_id: Annotated[str, Field(min_length=1, max_length=36)]
    service_date: date | None = None
    check_in: date | None = None
    check_out: date | None = None
    quantity: Annotated[int, Field(ge=1, le=20, strict=True)]
    quotes: Annotated[list[DayQuote], Field(min_length=1, max_length=30)]
    vehicle: VehicleSelection | None = None

    @model_validator(mode="after")
    def validate_dates_and_quantity(self):
        if self.kind == "vehicle":
            if (self.vehicle is None or not self.vehicle.start_time or self.quantity != 1 or not self.service_date
                    or self.check_in is not None or self.check_out is not None or len(self.quotes) != 1
                    or self.quotes[0].service_date != self.service_date):
                raise ValueError("用车须选择服务日期、开始时间及一趟的报价")
            return self
        if self.vehicle is not None:
            raise ValueError("房型和门票不能携带用车内容")
        if self.kind == "hotel":
            if (self.service_date is not None or self.check_in is None or self.check_out is None
                    or not 1 <= (self.check_out - self.check_in).days <= 30):
                raise ValueError("酒店需要入住日和退房日，入住 1 至 30 晚")
            if self.quantity > 5:
                raise ValueError("酒店最多可购买 5 间")
        elif self.service_date is None or self.check_in is not None or self.check_out is not None:
            raise ValueError("门票需要入园日期")
        return self


class TravelerInput(OrderBody):
    name: Annotated[str, Field(min_length=1, max_length=50)]
    document_type: Annotated[str, Field(max_length=16)] = ""
    document_number: Annotated[str, Field(max_length=64)] = ""
    phone: Annotated[str, Field(max_length=32)] = ""
    is_lead: bool = False


class CreateOrder(OrderBody):
    contact_name: Annotated[str, Field(min_length=1, max_length=50)]
    contact_phone: Annotated[str, Field(min_length=1, max_length=32)]
    trip_id: Annotated[str, Field(min_length=1, max_length=36)]
    departure_date: date | None = None
    travelers: Annotated[list[TravelerInput], Field(min_length=1, max_length=20)]
    selected: Annotated[list[SelectedItem], Field(min_length=1, max_length=20)]


class PayOrder(OrderBody):
    idempotency_key: Annotated[str, Field(min_length=1, max_length=80)]


class CancelOrder(OrderBody):
    reason: Annotated[str, Field(max_length=500)] = ""


class ReviewDecision(OrderBody):
    note: Annotated[str, Field(max_length=500)] = ""


class StockoutItem(OrderBody):
    product_id: Annotated[str, Field(min_length=1, max_length=36)]
    service_date: date


class RejectDecision(OrderBody):
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    category: Literal["other", "stockout"]
    items: Annotated[list[StockoutItem], Field(max_length=600)] = Field(default_factory=list)

    @model_validator(mode="after")
    def required_stockout_items(self):
        if (self.category == "stockout") != bool(self.items):
            raise ValueError("缺货拒单必须明确标记缺货日报价")
        return self


class ResolveCancelRequest(OrderBody):
    approve: bool
    note: Annotated[str, Field(min_length=1, max_length=500)]
    usage: Literal["unused", "unknown", "used"]


class TouristItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    product_name: str
    product_type: str
    attributes: dict
    service_date: date
    quantity: int
    unit_sale_fen: int
    subtotal_sale_fen: int


class ItemView(TouristItem):
    unit_cost_fen: int


class TravelerView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    document_type: str
    document_mask: str
    phone_mask: str
    is_lead: bool


class TouristEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    from_status: str | None
    to_status: str | None
    created_at: datetime


class EventView(TouristEvent):
    actor_name: str | None
    reason: str
    after: dict | None


class PaymentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    amount_fen: int
    event_id: str
    paid_at: datetime


class TouristRefund(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    refund_no: str
    amount_fen: int
    status: str
    processed_at: datetime | None


class RefundView(TouristRefund):
    attempts: int
    last_error: str


class OrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_no: str
    status: OrderStatus
    fund_status: FundStatus
    total_sale_fen: int
    expires_at: UtcTimestamp
    created_at: UtcTimestamp
    waiting_minutes: int = 0


class AdminOrderSummary(OrderSummary):
    waiting_minutes: int = 0
    review_alert_minutes: int
    review_overdue: bool


class TouristOrderDetail(OrderSummary):
    trip_id: str | None
    departure_date: date | None
    contact_name: str
    contact_phone: str
    cancelled_at: UtcTimestamp | None
    server_time: UtcTimestamp
    after_sales_ticket_id: str | None
    items: list[TouristItem]
    travelers: list[TravelerView]
    events: list[TouristEvent]
    payments: list[PaymentView]
    refunds: list[TouristRefund]


class OrderDetail(TouristOrderDetail, AdminOrderSummary):
    user_id: str
    total_cost_fen: int
    review_note: str
    cancel_reason: str
    items: list[ItemView]
    events: list[EventView]
    refunds: list[RefundView]


class OrderPage(BaseModel):
    items: list[OrderSummary]
    total: int


class AdminOrderPage(BaseModel):
    items: list[AdminOrderSummary]
    total: int


class SweepResult(BaseModel):
    expired: int = 0
    refunds: int = 0
