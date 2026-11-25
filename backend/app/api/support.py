"""Personal inboxes, notification settings, and tourist/operator ticket APIs."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.deps import CurrentAccount, CurrentOperator, DbSession, WriteDbSession
from app.db.models import UserRole
from app.schemas.admin_resources import ResourcePage
from app.schemas.support import (
    AdminTicketDetail, AdminTicketPage, ChangeMessageSetting, ChangePriority, CloseTicket, ExpectedRevision,
    InboxMessage, InboxMessageDetail, MessageCode, MessageSettingView, ReadMessage, SubmitTicket, TicketCategory,
    TicketDetail, TicketStatus, TicketSummary, UnreadCount,
)
from app.services import notifications, tickets


async def require_tourist(account: CurrentAccount):
    if account.role != UserRole.TOURIST:
        raise HTTPException(403, "此入口仅供游客使用")
    return account


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


class Pagination:
    def __init__(
        self, page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        self.offset = (page - 1) * page_size
        self.limit = page_size


Page = Annotated[Pagination, Depends()]
api_options = {"dependencies": [Depends(no_store)]}
inbox = APIRouter(prefix="/messages", **api_options)
admin_router = APIRouter(**api_options)
tourist_router = APIRouter(prefix="/v1", dependencies=[Depends(require_tourist), Depends(no_store)])


@inbox.get("", response_model=ResourcePage[InboxMessage])
async def inbox_list(account: CurrentAccount, db: DbSession, page: Page, unread_only: bool = False):
    return await notifications.list_messages(
        db, account, unread_only=unread_only, offset=page.offset, limit=page.limit,
    )


@inbox.get("/unread-count", response_model=UnreadCount)
async def inbox_count(account: CurrentAccount, db: DbSession):
    return UnreadCount(unread_count=await notifications.count_unread(db, account))


@inbox.get("/{message_id}", response_model=InboxMessageDetail)
async def inbox_detail(message_id: str, account: CurrentAccount, db: DbSession):
    return await notifications.message_detail(db, account, message_id)


@inbox.post("/{message_id}/read", response_model=ReadMessage)
async def inbox_read(message_id: str, account: CurrentAccount, db: WriteDbSession):
    result = await notifications.mark_read(db, account, message_id)
    await db.commit()
    return result


@admin_router.get("/message-settings", response_model=list[MessageSettingView])
async def message_settings(db: DbSession):
    return await notifications.list_settings(db)


@admin_router.patch("/message-settings/{code}", response_model=MessageSettingView)
async def update_message_setting(code: MessageCode, body: ChangeMessageSetting, actor: CurrentOperator, db: WriteDbSession):
    result = await notifications.change_setting(db, code, body, actor)
    await db.commit()
    return result


@tourist_router.get("/tickets", response_model=ResourcePage[TicketSummary])
async def my_tickets(account: CurrentAccount, db: DbSession, page: Page):
    return await tickets.tourist_list(db, account.id, page.offset, page.limit)


@tourist_router.post("/tickets", response_model=TicketDetail, status_code=201)
async def submit_ticket(body: SubmitTicket, account: CurrentAccount, db: WriteDbSession):
    result = await tickets.create_ticket(db, account.id, body)
    await db.commit()
    notifications.wake_delivery()
    return result


@tourist_router.get("/tickets/{ticket_id}", response_model=TicketDetail)
async def my_ticket(ticket_id: str, account: CurrentAccount, db: DbSession):
    return await tickets.tourist_detail(db, ticket_id, account.id)


@admin_router.get("/tickets", response_model=AdminTicketPage)
async def admin_tickets(
    db: DbSession, page: Page, status: TicketStatus | None = None, category: TicketCategory | None = None,
    assignee_id: Annotated[str | None, Query(max_length=36)] = None,
):
    return await tickets.admin_list(
        db, status=status, category=category, assignee_id=assignee_id, offset=page.offset, limit=page.limit,
    )


@admin_router.get("/tickets/{ticket_id}", response_model=AdminTicketDetail)
async def admin_ticket(ticket_id: str, db: DbSession):
    return await tickets.admin_detail(db, ticket_id)


@admin_router.post("/tickets/{ticket_id}/claim", response_model=AdminTicketDetail)
async def claim_ticket(ticket_id: str, body: ExpectedRevision, actor: CurrentOperator, db: WriteDbSession):
    result = await tickets.start_handling(db, ticket_id, actor, body.expected_revision, reopen=False)
    await db.commit()
    return result


@admin_router.post("/tickets/{ticket_id}/reopen", response_model=AdminTicketDetail)
async def reopen_ticket(ticket_id: str, body: ExpectedRevision, actor: CurrentOperator, db: WriteDbSession):
    result = await tickets.start_handling(db, ticket_id, actor, body.expected_revision, reopen=True)
    await db.commit()
    return result


@admin_router.post("/tickets/{ticket_id}/close", response_model=AdminTicketDetail)
async def complete_ticket(ticket_id: str, body: CloseTicket, actor: CurrentOperator, db: WriteDbSession):
    result = await tickets.close_ticket(db, ticket_id, actor, body.expected_revision, body.result)
    await db.commit()
    notifications.wake_delivery()
    return result


@admin_router.patch("/tickets/{ticket_id}/priority", response_model=AdminTicketDetail)
async def ticket_priority(ticket_id: str, body: ChangePriority, actor: CurrentOperator, db: WriteDbSession):
    result = await tickets.change_priority(db, ticket_id, actor, body.expected_revision, body.priority)
    await db.commit()
    return result


tourist_router.include_router(inbox)
admin_router.include_router(inbox)
