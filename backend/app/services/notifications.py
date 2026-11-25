"""Snapshot notification events in business transactions and deliver them after commit."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.db.database import reserve_write
from app.db.models import User, UserRole
from app.db.support_models import Message, MessageSetting, NotificationEvent, utc_now
from app.schemas.admin_resources import ResourcePage
from app.schemas.support import (
    ChangeMessageSetting, ConfirmationSummary, InboxMessage, InboxMessageDetail, MessageCode,
    MessageSettingView, MessageTarget, ReadMessage,
)

logger = logging.getLogger(__name__)
SCAN_SECONDS = 5
BATCH_SIZE = 50


@dataclass(frozen=True)
class NotificationTemplate:
    name: str
    trigger: str
    audience: str
    target: MessageTarget
    title: str
    body: str


TEMPLATES: dict[MessageCode, NotificationTemplate] = {
    "trip.confirmed": NotificationTemplate(
        "行程确认提醒运营", "游客首次确认行程", "事发时的所有运营", "trip_confirmation",
        "行程已确认 · {trip_title}", "游客确认了第 {version} 版行程，可查看确认摘要。",
    ),
    "ticket.created": NotificationTemplate(
        "新工单提醒运营", "游客成功提交工单", "事发时的所有运营", "admin_ticket",
        "收到新工单 · {subject}", "工单 {number} 已提交，可查看工单并接手。",
    ),
    "ticket.closed": NotificationTemplate(
        "工单处理完成提醒游客", "工单负责人提交结果并关闭本轮", "工单提交人", "tourist_ticket",
        "工单处理完成 · {subject}", "工单 {number} 第 {round} 轮已完成，可查看答复。",
    ),
}


async def seed_message_settings(db: AsyncConnection | AsyncSession) -> None:
    dialect = db.dialect if isinstance(db, AsyncConnection) else db.get_bind().dialect
    insert = postgres_insert if dialect.name == "postgresql" else sqlite_insert
    stmt = insert(MessageSetting).values([{"code": code, "enabled": True, "revision": 1} for code in TEMPLATES])
    await db.execute(stmt.on_conflict_do_nothing(index_elements=[MessageSetting.code]))


def _setting_view(row: MessageSetting) -> MessageSettingView:
    template = TEMPLATES[row.code]
    return MessageSettingView(
        code=row.code, name=template.name, trigger=template.trigger, audience=template.audience,
        enabled=row.enabled, revision=row.revision, updated_by=row.updated_by,
        updated_by_name=row.updated_by_name, updated_at=row.updated_at,
    )


async def list_settings(db: AsyncSession) -> list[MessageSettingView]:
    rows = {row.code: row for row in await db.scalars(select(MessageSetting))}
    return [_setting_view(rows[code]) for code in TEMPLATES]


async def change_setting(db: AsyncSession, code: MessageCode, body: ChangeMessageSetting, actor: User) -> MessageSettingView:
    row = await db.get(MessageSetting, code, with_for_update=True)
    if row is None:
        raise HTTPException(404, "通知项不存在")
    if row.revision != body.expected_revision:
        raise HTTPException(409, {
            "message": "这项配置已被其他运营修改，已显示最新配置。",
            "current": _setting_view(row).model_dump(mode="json"),
        })
    if row.enabled != body.enabled:
        row.enabled = body.enabled
        row.revision += 1
        row.updated_by = actor.id
        row.updated_by_name = actor.username
        row.updated_at = utc_now()
        await db.flush()
    return _setting_view(row)


async def enqueue(
    db: AsyncSession, code: MessageCode, target_id: str, data: dict, *,
    target_version: int | None = None, recipient_id: str | None = None,
    occurred_at: datetime,
) -> bool:
    setting = await db.get(MessageSetting, code, with_for_update=True)
    if setting is None:
        await seed_message_settings(db)
        setting = await db.get(MessageSetting, code, with_for_update=True)
    if not setting.enabled:
        return False

    if recipient_id is None:
        operators = await db.scalars(select(User.id).where(User.role == UserRole.OPERATOR).order_by(User.id))
        recipients = [{"id": operator_id, "role": UserRole.OPERATOR.value} for operator_id in operators]
    else:
        recipients = [{"id": recipient_id, "role": UserRole.TOURIST.value}]

    version_key = f":{target_version}" if target_version is not None else ""
    db.add(NotificationEvent(
        key=f"{code}:{target_id}{version_key}", code=code,
        target_type=TEMPLATES[code].target, target_id=target_id, target_version=target_version,
        occurred_at=occurred_at, data=data, recipients=recipients, next_attempt_at=occurred_at,
    ))
    await db.flush()
    return True


async def enqueue_trip_confirmation(db: AsyncSession, account_id: str, trip: dict) -> bool:
    role = await db.scalar(select(User.role).where(User.id == account_id))
    if role != UserRole.TOURIST:
        return False
    confirmed_at = datetime.fromisoformat(trip["updated_at"])
    if confirmed_at.tzinfo is None:
        confirmed_at = confirmed_at.replace(tzinfo=timezone.utc)
    return await enqueue(
        db, "trip.confirmed", trip["id"], {"trip_title": trip["title"] or "未命名行程", "version": trip["version"]},
        target_version=trip["version"], occurred_at=confirmed_at,
    )


def _render(event: NotificationEvent) -> tuple[str, str]:
    template = TEMPLATES[event.code]
    return template.title.format_map(event.data), template.body.format_map(event.data)


async def _deliver_recipient(db: AsyncSession, event: NotificationEvent, recipient: dict, now: datetime) -> bool:
    clauses = (Message.event_key == event.key, Message.code == event.code, Message.recipient_id == recipient["id"])
    existing = await db.scalar(select(Message).where(*clauses))
    if existing is not None and existing.status == "sent":
        return True

    def pending_message():
        if existing is not None:
            return existing
        row = Message(
            event_key=event.key, code=event.code, recipient_id=recipient["id"], recipient_role=recipient["role"],
            target_type=event.target_type, target_id=event.target_id, target_version=event.target_version,
            status="failed",
        )
        db.add(row)
        return row

    try:
        async with db.begin_nested():
            title, body = _render(event)
            message = pending_message()
            message.title, message.body = title, body
            message.status, message.error_summary, message.sent_at = "sent", None, now
        return True
    except KeyError as exc:
        reason = f"模板缺少变量 {exc.args[0]}"[:180]
    except (ValueError, IndexError, AttributeError):
        reason = "通知模板格式无效"
    except SQLAlchemyError:
        reason = "消息写入失败，等待重试"
    except Exception:
        reason = "通知模板暂时无法渲染，等待重试"

    async with db.begin_nested():
        message = pending_message()
        message.status = "failed"
        message.error_summary = reason
    return False


async def _deliver_event(sessions: async_sessionmaker, key: str) -> bool:
    async with sessions.begin() as db:
        await reserve_write(db)
        now = utc_now()
        event = await db.scalar(
            select(NotificationEvent)
            .where(NotificationEvent.key == key, NotificationEvent.delivered_at.is_(None),
                   NotificationEvent.next_attempt_at <= now)
            .with_for_update(skip_locked=True)
        )
        if event is None:
            return False

        succeeded = True
        for recipient in event.recipients:
            try:
                delivered = await _deliver_recipient(db, event, recipient, now)
            except SQLAlchemyError:
                logger.warning("Notification recipient write failed for %s", event.key)
                delivered = False
            succeeded = succeeded and delivered
        event.attempts += 1
        if succeeded:
            event.delivered_at = now
        else:
            event.next_attempt_at = now + timedelta(seconds=min(2 ** min(event.attempts, 6), 60))
    return True


async def deliver_pending(sessions: async_sessionmaker) -> int:
    async with sessions() as db:
        keys = list(await db.scalars(
            select(NotificationEvent.key)
            .where(NotificationEvent.delivered_at.is_(None), NotificationEvent.next_attempt_at <= utc_now())
            .order_by(NotificationEvent.next_attempt_at, NotificationEvent.key).limit(BATCH_SIZE)
        ))
    processed = 0
    for key in keys:
        try:
            processed += await _deliver_event(sessions, key)
        except Exception:
            logger.warning("Notification event %s could not be delivered and will retry", key)
    return processed


_delivery_signals: set[asyncio.Event] = set()


def wake_delivery() -> None:
    for signal in _delivery_signals:
        signal.set()


async def _run_delivery(sessions: async_sessionmaker, signal: asyncio.Event) -> None:
    while True:
        signal.clear()
        try:
            if await deliver_pending(sessions) == BATCH_SIZE:
                await asyncio.sleep(0)
                continue
        except SQLAlchemyError:
            logger.warning("Notification outbox unavailable; retrying after the scan interval")
        try:
            await asyncio.wait_for(signal.wait(), timeout=SCAN_SECONDS)
        except TimeoutError:
            pass


@asynccontextmanager
async def notification_worker(sessions: async_sessionmaker):
    signal = asyncio.Event()
    _delivery_signals.add(signal)
    task = asyncio.create_task(_run_delivery(sessions, signal))
    try:
        yield
    finally:
        _delivery_signals.discard(signal)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def _inbox_scope(account: User):
    return (Message.recipient_id == account.id, Message.recipient_role == account.role, Message.status == "sent")


async def count_unread(db: AsyncSession, account: User) -> int:
    return await db.scalar(select(func.count()).select_from(Message).where(
        *_inbox_scope(account), Message.read_at.is_(None),
    ))


async def list_messages(
    db: AsyncSession, account: User, *, unread_only: bool, offset: int, limit: int,
) -> ResourcePage[InboxMessage]:
    filters = _inbox_scope(account)
    if unread_only:
        filters += (Message.read_at.is_(None),)
    total = await db.scalar(select(func.count()).select_from(Message).where(*filters))
    rows = await db.scalars(select(Message).where(*filters).order_by(
        Message.sent_at.desc(), Message.id.desc(),
    ).offset(offset).limit(limit))
    return ResourcePage[InboxMessage](items=[InboxMessage.model_validate(row, from_attributes=True) for row in rows], total=total)


async def message_detail(db: AsyncSession, account: User, message_id: str) -> InboxMessageDetail:
    row = await db.scalar(select(Message).where(*_inbox_scope(account), Message.id == message_id))
    if row is None:
        raise HTTPException(404, "该消息不存在")
    response = InboxMessageDetail.model_validate(row, from_attributes=True)
    if row.target_type == "trip_confirmation":
        event = await db.get(NotificationEvent, row.event_key)
        response.confirmation = ConfirmationSummary(
            trip_id=event.target_id, title=event.data["trip_title"],
            version=event.target_version, confirmed_at=event.occurred_at,
        )
    return response


async def mark_read(db: AsyncSession, account: User, message_id: str) -> ReadMessage:
    await db.execute(update(Message).where(
        *_inbox_scope(account), Message.id == message_id, Message.read_at.is_(None),
    ).values(read_at=utc_now()))
    message = await message_detail(db, account, message_id)
    return ReadMessage(message=message, unread_count=await count_unread(db, account))
