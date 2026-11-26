"""Operator dashboard aggregates and limited ticket summaries."""

from pydantic import BaseModel, NonNegativeInt

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
