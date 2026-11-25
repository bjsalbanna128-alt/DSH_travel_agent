import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from secrets import token_hex
from threading import Barrier
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api import deps, routes, sse, ws
from app.config import settings
from app.db import database
from app.db.models import Trip, User
from app.db.recommendation_models import Recommendation
from app.db.support_models import Message, MessageSetting, NotificationEvent, Ticket, TicketHandling, utc_now
from app.db.template_models import ItineraryTemplate
from app.main import app
from app.services import notifications, planning_review
from app.services.auth_service import create_access_token
from app.services.trip_store import save_trip

ADMIN = "/api/v1/admin"
TOURIST = "/api/v1"
EDITOR_A, EDITOR_B, GUEST, OTHER = "editor-a", "editor-b", "guest", "other"


def auth(account):
    return {"Authorization": f"Bearer {create_access_token(account)}"}


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = database.create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'support.db'}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    for module in (database, deps, routes, sse, ws):
        monkeypatch.setattr(module, "async_session", sessions)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
    for module in (routes, sse, ws):
        monkeypatch.setattr(module, "remember_confirmed_trip", AsyncMock())
    try:
        yield sessions
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def api(sessions):
    async def initialize():
        await database.init_db()
        async with sessions.begin() as db:
            db.add_all([
                User(id=name, username=name, role=role, email=f"{name}@example.test", password_hash="unused")
                for name, role in ((EDITOR_A, "operator"), (EDITOR_B, "operator"), (GUEST, "tourist"), (OTHER, "tourist"))
            ])

    asyncio.run(initialize())
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def count(api, account):
    prefix = ADMIN if account in {EDITOR_A, EDITOR_B} else TOURIST
    return checked(api.get(f"{prefix}/messages/unread-count", headers=auth(account)))["unread_count"]


def messages(api, account, **params):
    prefix = ADMIN if account in {EDITOR_A, EDITOR_B} else TOURIST
    return checked(api.get(f"{prefix}/messages", headers=auth(account), params=params))


def drain(sessions):
    return asyncio.run(notifications.deliver_pending(sessions))


def create(api, *, subject="接驳车在哪里上车？", account=GUEST):
    return checked(api.post(f"{TOURIST}/tickets", headers=auth(account), json={
        "category": "inquiry", "subject": subject, "content": "请告诉我集合地点。",
    }), 201)


def act(api, ticket, action, account=EDITOR_A, **data):
    method = "PATCH" if action == "priority" else "POST"
    return api.request(method, f"{ADMIN}/tickets/{ticket['id']}/{action}", headers=auth(account), json={
        "expected_revision": ticket.get("revision", 1), **data,
    })


def get_settings(api, account=EDITOR_A):
    return {row["code"]: row for row in checked(api.get(f"{ADMIN}/message-settings", headers=auth(account)))}


def set_enabled(api, row, enabled, account=EDITOR_A):
    return api.patch(f"{ADMIN}/message-settings/{row['code']}", headers=auth(account),
                     json={"enabled": enabled, "expected_revision": row["revision"]})


def draft(sessions):
    async def seed():
        async with sessions.begin() as db:
            trip = await save_trip(db, "support-thread", {
                "travel_request": {"destination": "成都", "days": 1},
                "itinerary": {"title": "成都一日游", "destination": "成都", "duration_days": 1,
                              "total_budget_estimate_cny": 100, "day_plans": [{"day": 1}]},
            }, GUEST, status="draft")
            return trip.id, trip.thread_id

    return asyncio.run(seed())


@pytest.mark.parametrize("transport", ["rest", "sse", "websocket"])
def test_first_tourist_confirmation_enqueues_once_for_both_operators(api, sessions, monkeypatch, transport):
    trip_id, thread = draft(sessions)
    assert drain(sessions) == 0
    trip_url = f"{TOURIST}/trips/{trip_id}"

    async def revise(trip, _feedback):
        return {**trip["itinerary"], "overall_tips": "已调整"}

    monkeypatch.setattr(planning_review, "_revise_itinerary", revise)
    adjusted = checked(api.post(f"{trip_url}/decision", headers=auth(GUEST), json={
        "action": "adjust", "version": 1, "feedback": "调整提示",
    }))
    assert adjusted["status"] == "draft" and adjusted["version"] == 2 and drain(sessions) == 0
    payload = {"version": 2, "action": "approve"}
    for _ in range(2):
        if transport == "rest":
            response = checked(api.post(f"{trip_url}/decision", headers=auth(GUEST), json=payload))
            assert response["status"] == "completed"
        elif transport == "sse":
            response = api.post(f"{TOURIST}/trips/resume", headers=auth(GUEST), json={**payload, "thread_id": thread})
            assert response.status_code == 200 and "event: done" in response.text
        else:
            with api.websocket_connect(f"/ws/chat/{thread}") as socket:
                socket.send_json({"type": "auth", "token": create_access_token(GUEST)})
                assert socket.receive_json()["type"] == "authenticated"
                socket.send_json({"type": "resume", **payload})
                assert socket.receive_json()["type"] == "done"
        drain(sessions)

    assert [count(api, account) for account in (EDITOR_A, EDITOR_B, GUEST)] == [1, 1, 0]
    assert api.get(trip_url, headers=auth(EDITOR_A)).status_code == 404
    row, = messages(api, EDITOR_A)["items"]
    assert row["code"] == "trip.confirmed" and row["target_type"] == "trip_confirmation"
    summary = checked(api.get(f"{ADMIN}/messages/{row['id']}", headers=auth(EDITOR_A)))["confirmation"]
    assert summary["trip_id"] == trip_id and summary["title"] == "成都一日游"
    assert summary["version"] == 2 and summary["confirmed_at"]
    assert api.get(f"{ADMIN}/messages/{row['id']}", headers=auth(EDITOR_B)).status_code == 404


def test_settings_take_effect_at_event_time_and_keep_existing_messages(api, sessions):
    initial = get_settings(api)
    assert len(initial) == 3 and all(row["enabled"] and row["revision"] == 1 for row in initial.values())
    first = create(api, subject="关闭配置前的工单")
    turned_off = checked(set_enabled(api, initial["ticket.created"], False))
    assert not turned_off["enabled"] and turned_off["updated_by_name"] == EDITOR_A
    conflict = checked(set_enabled(api, initial["ticket.created"], True, EDITOR_B), 409)
    assert conflict["detail"]["current"] == turned_off
    second = create(api, subject="关闭配置后的工单")
    assert drain(sessions) == 1
    assert [row["target_id"] for row in messages(api, EDITOR_A)["items"]] == [first["id"]]
    assert count(api, EDITOR_B) == 1
    assert checked(api.get(f"{ADMIN}/tickets?status=new&assignee_id=unassigned", headers=auth(EDITOR_A)))["total"] == 2
    asyncio.run(database.init_db())
    assert get_settings(api)["ticket.created"] == turned_off
    checked(set_enabled(api, turned_off, True, EDITOR_B))
    third = create(api, subject="重开配置后的工单")
    assert drain(sessions) == 1
    assert [row["target_id"] for row in messages(api, EDITOR_A)["items"]] == [third["id"], first["id"]]

    checked(set_enabled(api, initial["ticket.closed"], False))
    assigned = checked(act(api, second, "claim"))
    checked(act(api, assigned, "close", result="请在酒店门口集合。"))
    assert drain(sessions) == 0 and count(api, GUEST) == 0
    result, = checked(api.get(f"{TOURIST}/tickets/{second['id']}", headers=auth(GUEST)))["handlings"]
    assert result["result"] == "请在酒店门口集合。"


def test_personal_inboxes_concurrent_claim_two_rounds_and_permissions(api, sessions):
    ticket = create(api)
    assert ticket["number"].startswith("T-")
    assert ticket["status"] == "new" and ticket["handlings"] == []
    assert drain(sessions) == 1
    row_a, = messages(api, EDITOR_A)["items"]
    row_b, = messages(api, EDITOR_B)["items"]
    assert row_a["id"] != row_b["id"] and row_a["target_id"] == row_b["target_id"] == ticket["id"]
    assert api.get(f"{ADMIN}/messages/{row_a['id']}", headers=auth(EDITOR_B)).status_code == 404
    assert api.post(f"{ADMIN}/messages/{row_a['id']}/read", headers=auth(EDITOR_B)).status_code == 404
    assert api.get(f"{ADMIN}/messages", headers=auth(GUEST)).status_code == 403
    assert api.get(f"{ADMIN}/tickets", headers=auth(GUEST)).status_code == 403
    assert api.get(f"{TOURIST}/tickets/{ticket['id']}", headers=auth(OTHER)).status_code == 404
    assert api.get(f"{TOURIST}/tickets", headers=auth(OTHER)).json()["total"] == 0
    assert api.get(f"{TOURIST}/tickets").status_code == 401
    assert api.get(f"{TOURIST}/messages/unread-count").status_code == 401
    assert api.post(f"{TOURIST}/tickets", headers=auth(GUEST), json={
        "category": "invalid", "subject": "题目", "content": "内容",
    }).status_code == 422

    read_at = None
    for _ in range(2):
        marked = checked(api.post(f"{ADMIN}/messages/{row_a['id']}/read", headers=auth(EDITOR_A)))
        assert marked["unread_count"] == 0 and marked["message"]["read_at"]
        if read_at is not None:
            assert marked["message"]["read_at"] == read_at
        read_at = marked["message"]["read_at"]
        assert messages(api, EDITOR_A, unread_only="true")["total"] == 0
    assert count(api, EDITOR_B) == 1
    assert checked(api.get(f"{ADMIN}/tickets/{ticket['id']}", headers=auth(EDITOR_A)))["status"] == "new"

    latch = Barrier(2)

    def claim(account):
        latch.wait(timeout=5)
        return account, act(api, ticket, "claim", account)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = dict(executor.map(claim, (EDITOR_A, EDITOR_B)))
    assert sorted(response.status_code for response in responses.values()) == [200, 409]
    winner = next(account for account, response in responses.items() if response.status_code == 200)
    other = EDITOR_B if winner == EDITOR_A else EDITOR_A
    claimed = checked(responses[winner])
    assert claimed["assignee"]["id"] == winner and claimed["status"] == "processing"
    assert claimed["handlings"][0]["handler_name"] == winner and claimed["handlings"][0]["claimed_at"]
    assert act(api, claimed, "close", other, result="代填").status_code == 403
    assert act(api, claimed, "priority", other, priority="high").status_code == 403
    assert act(api, claimed, "close", winner, result="  \n ").status_code == 422
    prioritized = checked(act(api, claimed, "priority", winner, priority="high"))
    assert act(api, claimed, "close", winner, result="旧页面操作").status_code == 409
    assert drain(sessions) == 0 and count(api, EDITOR_B) == 1
    first = checked(act(api, prioritized, "close", winner, result="请于 08:30 在酒店东门集合。"))
    assert act(api, prioritized, "close", winner, result="重复关闭").status_code == 409
    reopened = checked(act(api, first, "reopen", other))
    assert reopened["assignee"]["id"] == other
    assert [row["round"] for row in reopened["handlings"]] == [1, 2]
    assert reopened["handlings"][0] == first["handlings"][0]
    assert act(api, first, "reopen", winner).status_code == 409
    second = checked(act(api, reopened, "close", other, result="已为您更新到西门。"))
    assert second["handlings"][0] == reopened["handlings"][0]
    assert second["handlings"][1]["completed_by"] == other
    assert drain(sessions) == 2 and drain(sessions) == 0
    assert count(api, GUEST) == 2 and count(api, EDITOR_B) == 1
    tourist = checked(api.get(f"{TOURIST}/tickets/{ticket['id']}", headers=auth(GUEST)))
    assert not {"submitter", "assignee", "priority", "revision"} & tourist.keys()
    assert all(set(round) == {"round", "result", "completed_at"} for round in tourist["handlings"])
    assert [row["result"] for row in tourist["handlings"]] == ["请于 08:30 在酒店东门集合。", "已为您更新到西门。"]
    page = messages(api, GUEST, page_size=1)
    assert page["total"] == 2 and len(page["items"]) == 1
    two = messages(api, GUEST)["items"]
    assert [row["target_version"] for row in two] == [2, 1]
    assert all(row["target_type"] == "tourist_ticket" for row in two)
    assert api.get(f"{TOURIST}/messages/{two[0]['id']}", headers=auth(OTHER)).status_code == 404
    assert checked(api.get(f"{ADMIN}/tickets", headers=auth(EDITOR_A), params={
        "assignee_id": other, "status": "closed", "category": "inquiry",
    }))["total"] == 1


def test_missing_template_data_and_partial_delivery_retry_uses_same_record(api, sessions, monkeypatch):
    template = notifications.TEMPLATES["ticket.created"]
    ticket = create(api)
    monkeypatch.setitem(notifications.TEMPLATES, "ticket.created", replace(template, body="{missing_field}"))
    assert drain(sessions) == 1
    assert count(api, EDITOR_A) == count(api, EDITOR_B) == 0

    async def prepare_retry():
        async with sessions.begin() as db:
            event_row = await db.scalar(select(NotificationEvent).where(NotificationEvent.target_id == ticket["id"]))
            assert event_row.delivered_at is None
            event_row.next_attempt_at = utc_now()
            return {
                row.recipient_id: (row.id, row.status, row.error_summary)
                for row in await db.scalars(select(Message).where(Message.event_key == event_row.key))
            }

    failed = asyncio.run(prepare_retry())
    assert all(status == "failed" and "missing_field" in reason for _, status, reason in failed.values())
    monkeypatch.setitem(notifications.TEMPLATES, "ticket.created", template)

    def reject_b(_mapper, _connection, message):
        if message.recipient_id == EDITOR_B and message.status == "sent":
            raise SQLAlchemyError("simulated recipient interruption")

    event.listen(Message, "before_update", reject_b)
    try:
        assert drain(sessions) == 1
    finally:
        event.remove(Message, "before_update", reject_b)
    assert count(api, EDITOR_A) == 1 and count(api, EDITOR_B) == 0
    assert messages(api, EDITOR_A)["items"][0]["id"] == failed[EDITOR_A][0]
    partial = asyncio.run(prepare_retry())
    assert partial[EDITOR_A][1] == "sent" and partial[EDITOR_B][1] == "failed"
    marked = checked(api.post(f"{ADMIN}/messages/{partial[EDITOR_A][0]}/read", headers=auth(EDITOR_A)))["message"]

    async def start_worker():
        await database.engine.dispose()
        async with notifications.notification_worker(sessions):
            async with asyncio.timeout(3):
                while True:
                    async with sessions() as db:
                        done = await db.scalar(select(NotificationEvent.delivered_at))
                    if done:
                        return
                    await asyncio.sleep(0.02)

    asyncio.run(start_worker())
    assert count(api, EDITOR_A) == 0 and count(api, EDITOR_B) == 1
    assert messages(api, EDITOR_A)["items"] == [{key: value for key, value in marked.items() if key != "confirmation"}]
    assert messages(api, EDITOR_B)["items"][0]["id"] == failed[EDITOR_B][0]
    assert drain(sessions) == 0


def test_outbox_registration_failure_rolls_back_business_state(api, sessions):
    ticket = create(api)
    claimed = checked(act(api, ticket, "claim"))
    trip_id, _ = draft(sessions)

    def reject_event(*_):
        raise SQLAlchemyError("simulated outbox write failure")

    event.listen(NotificationEvent, "before_insert", reject_event)
    try:
        assert api.post(f"{TOURIST}/trips/{trip_id}/decision", headers=auth(GUEST), json={
            "action": "approve", "version": 1,
        }).status_code == 503
        assert api.post(f"{TOURIST}/tickets", headers=auth(GUEST), json={
            "category": "suggestion", "subject": "待回滚", "content": "待回滚的内容",
        }).status_code == 500
        assert act(api, claimed, "close", result="待回滚").status_code == 500
    finally:
        event.remove(NotificationEvent, "before_insert", reject_event)
    assert checked(api.get(f"{TOURIST}/trips/{trip_id}", headers=auth(GUEST)))["status"] == "draft"
    assert checked(api.get(f"{TOURIST}/tickets", headers=auth(GUEST)))["total"] == 1
    actual = checked(api.get(f"{ADMIN}/tickets/{ticket['id']}", headers=auth(EDITOR_A)))
    assert actual["revision"] == claimed["revision"] and actual["status"] == "processing"
    assert actual["handlings"][0]["completed_at"] is None
    assert drain(sessions) == 1 and count(api, GUEST) == 0


def test_upgrade_keeps_existing_tables_and_records(sessions):
    async def check():
        support_tables = {model.__table__ for model in (Message, MessageSetting, NotificationEvent, Ticket, TicketHandling)}
        async with database.engine.begin() as conn:
            old_tables = [table for table in database.Base.metadata.sorted_tables if table not in support_tables]
            await conn.run_sync(lambda sync: database.Base.metadata.create_all(sync, tables=old_tables))
        async with sessions.begin() as db:
            db.add(User(id=EDITOR_A, username=EDITOR_A, role="operator", email="preserved@example.test", password_hash="unused"))
            db.add(Trip(id="old-trip", thread_id="old-thread", user_id=EDITOR_A, status="completed"))
            db.add(ItineraryTemplate(id="old-template", title="旧模板", draft={}, draft_hash="old", destination="成都",
                                     days_count=1, created_by=EDITOR_A, updated_by=EDITOR_A))
            db.add(Recommendation(id="old-recommendation", title="旧推荐", created_by=EDITOR_A, updated_by=EDITOR_A))
        await database.init_db()
        async with sessions.begin() as db:
            await db.execute(update(MessageSetting).where(MessageSetting.code == "ticket.created").values(enabled=False))
            await notifications.enqueue(db, "trip.confirmed", "old-trip", {"trip_title": "保存记录", "version": 1},
                                        target_version=1, occurred_at=utc_now())
        assert await notifications.deliver_pending(sessions) == 1
        await database.init_db()
        async with sessions() as db:
            assert (await db.get(User, EDITOR_A)).role == "operator"
            assert (await db.get(Trip, "old-trip")).status == "completed"
            assert (await db.get(ItineraryTemplate, "old-template")).title == "旧模板"
            assert (await db.get(Recommendation, "old-recommendation")).title == "旧推荐"
            assert (await db.get(MessageSetting, "ticket.created")).enabled is False
            assert await db.scalar(select(func.count()).select_from(Message)) == 1

    asyncio.run(check())
