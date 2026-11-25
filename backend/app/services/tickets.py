"""Tourist-owned tickets, operator assignment, and per-round history."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db.models import User, UserRole
from app.db.support_models import Ticket, TicketHandling, new_id, utc_now
from app.schemas.admin_resources import ResourcePage
from app.schemas.support import (
    AccountLabel, AdminTicketDetail, AdminTicketHandling, AdminTicketPage, AdminTicketSummary,
    SubmitTicket, TicketCategory, TicketDetail, TicketHandlingView, TicketPriority, TicketStatus, TicketSummary,
)
from app.services.notifications import enqueue


async def _ticket_row(db: AsyncSession, ticket_id: str, *, submitter_id: str | None = None, lock: bool = False) -> Ticket:
    query = select(Ticket).where(Ticket.id == ticket_id)
    if submitter_id is not None:
        query = query.where(Ticket.submitter_id == submitter_id)
    if lock:
        query = query.with_for_update()
    ticket = await db.scalar(query)
    if ticket is None:
        raise HTTPException(404, "工单不存在")
    return ticket


async def _history(db: AsyncSession, ticket_id: str) -> list[TicketHandling]:
    return list(await db.scalars(select(TicketHandling).where(
        TicketHandling.ticket_id == ticket_id,
    ).order_by(TicketHandling.round)))


async def tourist_detail(db: AsyncSession, ticket_id: str, submitter_id: str) -> TicketDetail:
    ticket = await _ticket_row(db, ticket_id, submitter_id=submitter_id)
    return TicketDetail(
        **TicketSummary.model_validate(ticket).model_dump(),
        content=ticket.content, handlings=[TicketHandlingView.model_validate(row) for row in await _history(db, ticket.id)],
    )


async def _page(db: AsyncSession, filters: list, offset: int, limit: int) -> tuple[list[Ticket], int]:
    total = await db.scalar(select(func.count()).select_from(Ticket).where(*filters))
    tickets = await db.scalars(select(Ticket).where(*filters).order_by(
        Ticket.updated_at.desc(), Ticket.id.desc(),
    ).offset(offset).limit(limit))
    return list(tickets), total


async def tourist_list(db: AsyncSession, submitter_id: str, offset: int, limit: int) -> ResourcePage[TicketSummary]:
    tickets, total = await _page(db, [Ticket.submitter_id == submitter_id], offset, limit)
    return ResourcePage[TicketSummary](items=[TicketSummary.model_validate(row) for row in tickets], total=total)


async def create_ticket(db: AsyncSession, submitter_id: str, form: SubmitTicket) -> TicketDetail:
    ticket_id = new_id()
    now = utc_now()
    ticket = Ticket(
        id=ticket_id, number="T-" + ticket_id.replace("-", "").upper(), submitter_id=submitter_id,
        created_at=now, updated_at=now, **form.model_dump(),
    )
    db.add(ticket)
    await db.flush()
    await enqueue(db, "ticket.created", ticket.id, {"subject": ticket.subject, "number": ticket.number}, occurred_at=now)
    return TicketDetail(**TicketSummary.model_validate(ticket).model_dump(), content=ticket.content, handlings=[])


async def _names(db: AsyncSession, tickets: list[Ticket]) -> dict[str, str]:
    ids = {row.submitter_id for row in tickets} | {row.assignee_id for row in tickets if row.assignee_id}
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.username).where(User.id.in_(ids)))).all())


def _admin_summary(ticket: Ticket, names: dict[str, str]) -> AdminTicketSummary:
    def label(account_id: str) -> AccountLabel:
        return AccountLabel(id=account_id, username=names.get(account_id, "账号已移除"))

    return AdminTicketSummary(
        **TicketSummary.model_validate(ticket).model_dump(),
        priority=ticket.priority, revision=ticket.revision,
        submitter=label(ticket.submitter_id), assignee=label(ticket.assignee_id) if ticket.assignee_id else None,
    )


async def admin_list(
    db: AsyncSession, *, status: TicketStatus | None, category: TicketCategory | None,
    assignee_id: str | None, offset: int, limit: int,
) -> AdminTicketPage:
    filters = []
    if status:
        filters.append(Ticket.status == status)
    if category:
        filters.append(Ticket.category == category)
    if assignee_id:
        filters.append(Ticket.assignee_id.is_(None) if assignee_id == "unassigned" else Ticket.assignee_id == assignee_id)
    tickets, total = await _page(db, filters, offset, limit)
    names = await _names(db, tickets)
    # Include previously assigned operators so older tickets remain filterable after a change of role.
    assignees = await db.execute(select(User.id, User.username).where(
        (User.role == UserRole.OPERATOR) | User.id.in_(select(Ticket.assignee_id).where(Ticket.assignee_id.is_not(None))),
    ).order_by(User.username, User.id))
    return AdminTicketPage(
        items=[_admin_summary(row, names) for row in tickets], total=total,
        assignees=[AccountLabel(id=account_id, username=name) for account_id, name in assignees],
    )


async def admin_detail(db: AsyncSession, ticket_id: str) -> AdminTicketDetail:
    ticket = await _ticket_row(db, ticket_id)
    summary = _admin_summary(ticket, await _names(db, [ticket]))
    return AdminTicketDetail(
        **summary.model_dump(), content=ticket.content, order_id=ticket.order_id,
        handlings=[AdminTicketHandling.model_validate(row, from_attributes=True) for row in await _history(db, ticket.id)],
    )


def _conflict() -> HTTPException:
    return HTTPException(409, "工单状态或修订已变化，请核对最新工单后重试。")


def _require_owner(ticket: Ticket, operator: User) -> None:
    if ticket.assignee_id is not None and ticket.assignee_id != operator.id:
        raise HTTPException(403, "只有本轮负责人可以修改这张工单。")


async def _change(db: AsyncSession, ticket: Ticket, revision: int, now, **values) -> None:
    changed = await db.execute(update(Ticket).where(
        Ticket.id == ticket.id, Ticket.revision == revision,
        Ticket.status == ticket.status, Ticket.assignee_id == ticket.assignee_id,
    ).values(**values, revision=revision + 1, updated_at=now).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise _conflict()
    await db.refresh(ticket)


async def start_handling(
    db: AsyncSession, ticket_id: str, operator: User, revision: int, *, reopen: bool,
) -> AdminTicketDetail:
    ticket = await _ticket_row(db, ticket_id, lock=True)
    if ticket.status != ("closed" if reopen else "new") or (not reopen and ticket.assignee_id is not None):
        raise _conflict()
    now = utc_now()
    await _change(db, ticket, revision, now, status="processing", assignee_id=operator.id)
    previous_round = await db.scalar(select(func.max(TicketHandling.round)).where(TicketHandling.ticket_id == ticket.id))
    db.add(TicketHandling(
        ticket_id=ticket.id, round=(previous_round or 0) + 1, handler_id=operator.id,
        handler_name=operator.username, claimed_at=now,
    ))
    await db.flush()
    return await admin_detail(db, ticket.id)


async def close_ticket(
    db: AsyncSession, ticket_id: str, operator: User, revision: int, result: str,
) -> AdminTicketDetail:
    ticket = await _ticket_row(db, ticket_id, lock=True)
    if ticket.status != "processing":
        raise _conflict()
    _require_owner(ticket, operator)
    now = utc_now()
    await _change(db, ticket, revision, now, status="closed")
    handling = await db.scalar(select(TicketHandling).where(
        TicketHandling.ticket_id == ticket_id, TicketHandling.handler_id == operator.id,
        TicketHandling.completed_at.is_(None),
    ))
    if handling is None:
        raise _conflict()
    handling.result, handling.completed_at, handling.completed_by = result, now, operator.id
    await enqueue(db, "ticket.closed", ticket.id, {
        "subject": ticket.subject, "number": ticket.number, "round": handling.round,
    }, target_version=handling.round, recipient_id=ticket.submitter_id, occurred_at=now)
    await db.flush()
    return await admin_detail(db, ticket.id)


async def change_priority(
    db: AsyncSession, ticket_id: str, operator: User, revision: int, priority: TicketPriority,
) -> AdminTicketDetail:
    ticket = await _ticket_row(db, ticket_id, lock=True)
    _require_owner(ticket, operator)
    await _change(db, ticket, revision, utc_now(), priority=priority)
    return await admin_detail(db, ticket.id)
