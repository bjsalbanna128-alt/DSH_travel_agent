"""Read the business and personal counters for the operator workspace."""

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserRole
from app.db.recommendation_models import Recommendation
from app.db.support_models import Ticket, utc_now
from app.db.template_models import ItineraryTemplate
from app.schemas.dashboard import DashboardOverview, DashboardResponse, DashboardTicket, DashboardWork
from app.services.admin_trips import count_confirmed_trips
from app.services.member_points import BEIJING
from app.services.notifications import count_unread
from app.services.tickets import unassigned_tickets


def _today_utc(now: datetime) -> tuple[datetime, datetime]:
    day = now.astimezone(BEIJING).date()
    start = datetime.combine(day, time.min, tzinfo=BEIJING)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=BEIJING)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _count_when(condition):
    return func.count(case((condition, 1)))


async def _content_counts(db: AsyncSession, model) -> tuple[int, int]:
    total, published = (await db.execute(
        select(func.count(), _count_when(model.visibility == "published")).select_from(model)
    )).one()
    return total, published


async def load_dashboard(db: AsyncSession, operator: User) -> DashboardResponse:
    as_of = utc_now()
    start, end = _today_utc(as_of)
    # Users use naive UTC; tickets declare timezone-aware UTC.
    registered_today = and_(
        User.created_at >= start.replace(tzinfo=None), User.created_at < end.replace(tzinfo=None),
    )
    tourists, new_members = (await db.execute(select(
        func.count(), _count_when(registered_today),
    ).select_from(User).where(User.role == UserRole.TOURIST))).one()
    templates_total, templates_published = await _content_counts(db, ItineraryTemplate)
    recs_total, recs_published = await _content_counts(db, Recommendation)
    unassigned = unassigned_tickets()
    high_unassigned = and_(unassigned, Ticket.priority == "high")
    pending, processing, high, new_tickets = (await db.execute(select(
        _count_when(unassigned),
        _count_when(and_(Ticket.status == "processing", Ticket.assignee_id == operator.id)),
        _count_when(high_unassigned),
        _count_when(and_(Ticket.created_at >= start, Ticket.created_at < end)),
    ).select_from(Ticket))).one()
    items = (await db.execute(select(Ticket.id, Ticket.number, Ticket.category, Ticket.created_at)
        .where(high_unassigned).order_by(Ticket.created_at, Ticket.id).limit(5))).all()
    return DashboardResponse(
        as_of=as_of,
        overview=DashboardOverview(
            confirmed_trips=await count_confirmed_trips(db), tourist_members=tourists,
            new_members_today=new_members, templates_total=templates_total,
            templates_published=templates_published, recommendations_total=recs_total,
            recommendations_published=recs_published,
        ),
        work=DashboardWork(
            unassigned_tickets=pending, my_processing_tickets=processing, high_unassigned_tickets=high,
            my_unread_messages=await count_unread(db, operator), new_tickets_today=new_tickets,
        ),
        high_priority_items=[DashboardTicket.model_validate(item) for item in items],
    )
