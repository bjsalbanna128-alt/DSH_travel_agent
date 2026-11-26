"""Read the business and personal counters for the operator workspace."""

from datetime import date as DateType, datetime, time, timedelta, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.fulfillment_models import FulfillmentTask
from app.db.fleet_models import FleetAllocation
from app.db.models import User, UserRole
from app.db.order_models import OrderItem, OrderPayment, OrderRefund
from app.db.recommendation_models import Recommendation
from app.db.resource_models import Vehicle
from app.db.support_models import Ticket, utc_now
from app.db.template_models import ItineraryTemplate
from app.schemas.dashboard import (
    CategoryAmount, DashboardOverview, DashboardResponse, DashboardTicket, DashboardTrends,
    DashboardWork, TrendPoint, TrendTotals,
)
from app.services.admin_trips import count_confirmed_trips
from app.services.fleet_capacity import HELD
from app.services.member_points import BEIJING
from app.services.notifications import count_unread
from app.services.tickets import unassigned_tickets

TREND_DAYS = (7, 30)
READY_STATUSES = ("ready", "in_progress", "completed")


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


def _naive_utc(value: datetime) -> datetime:
    """SQLite stores naive UTC; compare in the same shape."""
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _beijing_day(value: datetime) -> DateType:
    return _as_utc(value).astimezone(BEIJING).date()


async def load_trends(db: AsyncSession, days: int) -> DashboardTrends:
    """Daily business counters for the last N Beijing days, today included."""
    if days not in TREND_DAYS:
        raise ValueError(days)
    as_of = utc_now()
    today = as_of.astimezone(BEIJING).date()
    first = today - timedelta(days=days - 1)
    start = _naive_utc(datetime.combine(first, time.min, tzinfo=BEIJING))
    end = _naive_utc(datetime.combine(today + timedelta(days=1), time.min, tzinfo=BEIJING))

    paid_per_day: dict[DateType, int] = {}
    orders_per_day: dict[DateType, int] = {}
    payments = (await db.execute(select(OrderPayment.paid_at, OrderPayment.amount_fen,
                                        OrderPayment.order_id).where(
        OrderPayment.paid_at >= start, OrderPayment.paid_at < end,
    ))).all()
    for paid_at, amount_fen, order_id in payments:
        day = _beijing_day(paid_at)
        paid_per_day[day] = paid_per_day.get(day, 0) + int(amount_fen)
        orders_per_day.setdefault(day, 0)
        orders_per_day[day] += 1

    refund_per_day: dict[DateType, int] = {}
    refunds = (await db.execute(select(OrderRefund.processed_at, OrderRefund.amount_fen).where(
        OrderRefund.status == "succeeded",
        OrderRefund.processed_at >= start, OrderRefund.processed_at < end,
    ))).all()
    for processed_at, amount_fen in refunds:
        day = _beijing_day(processed_at)
        refund_per_day[day] = refund_per_day.get(day, 0) + int(amount_fen)

    category: dict[str, int] = {}
    paid_orders = {order_id for *_, order_id in payments}
    if paid_orders:
        items = (await db.execute(select(OrderItem.order_id, OrderItem.product_type,
                                         OrderItem.subtotal_sale_fen).where(
            OrderItem.order_id.in_(paid_orders),
        ))).all()
        day_of_order = {}
        for paid_at, _amount, order_id in payments:
            day_of_order[order_id] = _beijing_day(paid_at)
        for order_id, product_type, subtotal in items:
            if day_of_order.get(order_id) is None:
                continue
            category[product_type] = category.get(product_type, 0) + int(subtotal)

    tasks = (await db.execute(select(FulfillmentTask.service_date, FulfillmentTask.status).where(
        FulfillmentTask.service_date >= first.isoformat(),
        FulfillmentTask.service_date <= today.isoformat(),
        FulfillmentTask.status != "cancelled",
    ))).all()
    task_total: dict[str, int] = {}
    task_ready: dict[str, int] = {}
    for service_date, status in tasks:
        task_total[service_date] = task_total.get(service_date, 0) + 1
        if status in READY_STATUSES:
            task_ready[service_date] = task_ready.get(service_date, 0) + 1

    allocations = (await db.execute(select(FleetAllocation.starts_at, FleetAllocation.vehicle_id).where(
        FleetAllocation.state.in_(HELD),
        FleetAllocation.starts_at >= start, FleetAllocation.starts_at < end,
    ))).all()
    fleet_per_day: dict[DateType, int] = {}
    for starts_at, vehicle_id in allocations:
        if not vehicle_id:
            continue
        day = _beijing_day(starts_at)
        fleet_per_day[day] = fleet_per_day.get(day, 0) + 1
    fleet_capacity = int(await db.scalar(select(func.count()).select_from(Vehicle).where(
        Vehicle.status == "active")) or 0)

    series: list[TrendPoint] = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        paid_fen = paid_per_day.get(day, 0)
        refund_fen = refund_per_day.get(day, 0)
        orders = orders_per_day.get(day, 0)
        series.append(TrendPoint(
            date=day, paid_fen=paid_fen, refund_fen=refund_fen, net_fen=paid_fen - refund_fen,
            orders=orders, avg_order_fen=(paid_fen // orders) if orders else 0,
            fulfillment_total=task_total.get(day.isoformat(), 0),
            fulfillment_ready=task_ready.get(day.isoformat(), 0),
            fleet_used=fleet_per_day.get(day, 0), fleet_capacity=fleet_capacity,
        ))

    total_paid = sum(point.paid_fen for point in series)
    total_refund = sum(point.refund_fen for point in series)
    total_orders = sum(point.orders for point in series)
    return DashboardTrends(
        days=days, start=first, end=today, today=today, as_of=as_of, series=series,
        totals=TrendTotals(
            paid_fen=total_paid, refund_fen=total_refund, net_fen=total_paid - total_refund,
            orders=total_orders,
            avg_order_fen=(total_paid // total_orders) if total_orders else 0,
            fulfillment_total=sum(point.fulfillment_total for point in series),
            fleet_used=sum(point.fleet_used for point in series),
        ),
        by_category=[CategoryAmount(product_type=key, amount_fen=value)
                     for key, value in sorted(category.items())],
    )
