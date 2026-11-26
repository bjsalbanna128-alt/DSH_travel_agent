"""Operator dashboard aggregates and limited ticket summaries."""

from datetime import date as DateType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt

from app.schemas.support import TicketCategory, UtcTimestamp


class DashboardOverview(BaseModel):
    confirmed_trips: NonNegativeInt
    tourist_members: NonNegativeInt
    new_members_today: NonNegativeInt
    templates_total: NonNegativeInt
    templates_published: NonNegativeInt
    recommendations_total: NonNegativeInt
    recommendations_published: NonNegativeInt


class DashboardWork(BaseModel):
    unassigned_tickets: NonNegativeInt
    my_processing_tickets: NonNegativeInt
    high_unassigned_tickets: NonNegativeInt
    my_unread_messages: NonNegativeInt
    new_tickets_today: NonNegativeInt


class DashboardTicket(BaseModel, from_attributes=True):
    id: str
    number: str
    category: TicketCategory
    created_at: UtcTimestamp


class DashboardResponse(BaseModel):
    as_of: UtcTimestamp
    overview: DashboardOverview
    work: DashboardWork
    high_priority_items: list[DashboardTicket]


class TrendPoint(BaseModel):
    date: DateType
    paid_fen: NonNegativeInt
    refund_fen: NonNegativeInt
    net_fen: int
    orders: NonNegativeInt
    avg_order_fen: NonNegativeInt
    fulfillment_total: NonNegativeInt
    fulfillment_ready: NonNegativeInt
    fleet_used: NonNegativeInt
    fleet_capacity: NonNegativeInt


class TrendTotals(BaseModel):
    paid_fen: NonNegativeInt
    refund_fen: NonNegativeInt
    net_fen: int
    orders: NonNegativeInt
    avg_order_fen: NonNegativeInt
    fulfillment_total: NonNegativeInt
    fleet_used: NonNegativeInt


class CategoryAmount(BaseModel):
    product_type: Literal["hotel_room", "attraction_ticket", "vehicle"]
    amount_fen: NonNegativeInt


class DashboardTrends(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    days: Literal[7, 30]
    start: DateType = Field(serialization_alias="from")
    end: DateType = Field(serialization_alias="to")
    today: DateType
    as_of: UtcTimestamp
    series: list[TrendPoint]
    totals: TrendTotals
    by_category: list[CategoryAmount]
