import asyncio
from datetime import datetime, timedelta, timezone
from secrets import token_hex

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api import deps
from app.config import settings
from app.db import database
from app.db.models import Trip, TripVersion, User
from app.db.recommendation_models import Recommendation, RecommendationImage, RecommendationVersion
from app.db.support_models import Message, NotificationEvent, Ticket
from app.db.template_models import ItineraryTemplate, ItineraryTemplateVersion
from app.main import app
from app.services import dashboard
from app.services.auth_service import create_access_token

ADMIN = "/api/v1/admin"
OPERATOR_A = "editor-a"
OPERATOR_B = "editor-b"
TOURIST = "tourist-start"
START = datetime(2026, 11, 25, 16, tzinfo=timezone.utc)
END = START + timedelta(days=1)
AS_OF = START + timedelta(hours=12)


def account(account_id, role, created=START):
    return User(
        id=account_id, username=account_id, email=f"{account_id}@example.test",
        password_hash="unused", role=role, created_at=created.replace(tzinfo=None),
    )


def auth(account_id=OPERATOR_A):
    return {"Authorization": f"Bearer {create_access_token(account_id)}"}


def checked(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = database.create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'dashboard.db'}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", sessions)
    monkeypatch.setattr(deps, "async_session", sessions)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))

    async def initialize():
        await database.init_db()
        async with sessions.begin() as db:
            db.add_all([account(OPERATOR_A, "operator"), account(OPERATOR_B, "operator")])

    asyncio.run(initialize())
    with_client = TestClient(app, raise_server_exceptions=False)
    try:
        yield with_client, sessions
    finally:
        with_client.close()
        asyncio.run(engine.dispose())


def snapshot(api, operator=OPERATOR_A, **options):
    client, _ = api
    return checked(client.get(f"{ADMIN}/dashboard", headers=auth(operator), **options))


def seeded_ticket(ticket_id, time, priority="normal", *, status="new", assignee=None):
    return Ticket(
        id=ticket_id, number=f"T-{ticket_id}", submitter_id=TOURIST, category="inquiry",
        subject="synthetic ticket subject", content="synthetic private description", status=status,
        priority=priority, assignee_id=assignee, created_at=time, updated_at=END,
    )


def test_operator_authentication_and_empty_dashboard(api):
    client, sessions = api
    assert client.get(f"{ADMIN}/dashboard").status_code == 401
    response = client.get(f"{ADMIN}/dashboard", headers=auth())
    assert response.headers["cache-control"] == "private, no-store"
    data = checked(response)
    assert set(data) == {"as_of", "overview", "work", "high_priority_items"}
    assert datetime.fromisoformat(data["as_of"]).utcoffset() == timedelta(0)
    assert set(data["overview"].values()) == set(data["work"].values()) == {0}
    assert data["high_priority_items"] == []

    async def add_tourist():
        async with sessions.begin() as db:
            db.add(account(TOURIST, "tourist"))

    asyncio.run(add_tourist())
    assert client.get(f"{ADMIN}/dashboard", headers=auth(TOURIST)).status_code == 403


def test_dashboard_matches_source_list_totals_and_uses_one_beijing_business_day(api, monkeypatch):
    client, sessions = api
    ticks = []

    def clock():
        ticks.append(AS_OF)
        return AS_OF

    monkeypatch.setattr(dashboard, "utc_now", clock)

    async def seed():
        async with sessions.begin() as db:
            db.add_all([
                account("tourist-before", "tourist", START - timedelta(seconds=1)),
                account(TOURIST, "tourist", START),
                account("tourist-last-second", "tourist", END - timedelta(seconds=1)),
                account("tourist-end", "tourist", END),
            ])
            db.add_all([
                Trip(id="confirmed", user_id=TOURIST, thread_id="confirmed-thread",
                     title="有多个版本的行程", version=3, status="completed", confirmed_version=1),
                Trip(id="draft", user_id=TOURIST, thread_id="draft-thread", status="draft"),
                Trip(id="orphan", user_id="removed-user", thread_id="orphan-thread", status="completed"),
            ])
            db.add_all([TripVersion(trip_id="confirmed", version=version) for version in (1, 2, 3)])
            db.add(RecommendationImage(id="cover", content=b"test", mime="image/png", width=1, height=1, size_bytes=4))
            for visibility in ("draft", "published", "unpublished"):
                db.add(ItineraryTemplate(
                    id=f"template-{visibility}", title=visibility, draft={"title": "编辑中的新稿"},
                    draft_hash="changed", destination="成都", days_count=1, visibility=visibility,
                    published_version=2 if visibility == "published" else 0,
                    created_by=OPERATOR_A, updated_by=OPERATOR_A,
                ))
                db.add(Recommendation(
                    id=f"recommendation-{visibility}", title="编辑中的新稿", visibility=visibility,
                    published_version=2 if visibility == "published" else 0, created_by=OPERATOR_A, updated_by=OPERATOR_A,
                ))
            await db.flush()
            for version in (1, 2):
                db.add(ItineraryTemplateVersion(
                    template_id="template-published", version=version, snapshot={"title": "线上模板"},
                    draft_hash="current", title="线上模板", destination="成都", days_count=1,
                    published_at=START, published_by=OPERATOR_A,
                ))
                db.add(RecommendationVersion(
                    recommendation_id="recommendation-published", version=version, title="线上推荐",
                    place="成都", short_text="已发布的内容", display_order=100, cover_id="cover",
                    published_at=START, published_by=OPERATOR_A,
                ))
            db.add_all([
                seeded_ticket("before", START - timedelta(seconds=1)),
                seeded_ticket("begin", START),
                seeded_ticket("closed-today", END - timedelta(seconds=1), status="closed", assignee=OPERATOR_A),
                seeded_ticket("end", END),
            ])

    asyncio.run(seed())
    data = snapshot(api)
    assert ticks == [AS_OF] and datetime.fromisoformat(data["as_of"]) == AS_OF
    assert data["overview"] == {
        "confirmed_trips": 1, "tourist_members": 4, "new_members_today": 2,
        "templates_total": 3, "templates_published": 1,
        "recommendations_total": 3, "recommendations_published": 1,
    }
    assert data["work"]["new_tickets_today"] == 2
    for key, path in {
        "confirmed_trips": "trips", "tourist_members": "members",
        "templates_total": "itinerary-templates", "recommendations_total": "recommendations",
    }.items():
        assert data["overview"][key] == checked(client.get(f"{ADMIN}/{path}", headers=auth()))["total"]


def test_shared_queue_personal_counts_read_scope_and_priority_pagination(api):
    client, sessions = api

    async def seed():
        async with sessions.begin() as db:
            db.add(account(TOURIST, "tourist"))
            db.add_all([
                seeded_ticket(f"high-{index}", START + timedelta(seconds=index // 2), "high")
                for index in reversed(range(6))
            ])
            db.add(seeded_ticket("ordinary", START))
            for which in ("unread", "already-read", "failed", "tourist-role"):
                db.add(NotificationEvent(
                    key=which, code="ticket.created", target_type="admin_ticket", target_id="high-0",
                    occurred_at=START, data={}, recipients=[], next_attempt_at=START, delivered_at=START,
                ))
            await db.flush()
            for who in (OPERATOR_A, OPERATOR_B):
                db.add(Message(
                    id=f"unread-{who}", event_key="unread", code="ticket.created", target_type="admin_ticket",
                    target_id="high-0", recipient_id=who, recipient_role="operator", title="待接工单",
                    status="sent", sent_at=START,
                ))
            for which, role, status, read in (
                ("already-read", "operator", "sent", START),
                ("failed", "operator", "failed", None),
                ("tourist-role", "tourist", "sent", None),
            ):
                db.add(Message(
                    event_key=which, code="ticket.created", target_type="admin_ticket", target_id="high-0",
                    recipient_id=OPERATOR_A, recipient_role=role, status=status, sent_at=START, read_at=read,
                ))

    asyncio.run(seed())
    data = snapshot(api, params={"assignee_id": OPERATOR_B, "recipient_id": OPERATOR_B})
    assert data["work"]["unassigned_tickets"] == 7
    assert data["work"]["high_unassigned_tickets"] == 6
    assert data["work"]["my_processing_tickets"] == 0
    assert data["work"]["my_unread_messages"] == 1
    summaries = data["high_priority_items"]
    assert [row["id"] for row in summaries] == [f"high-{index}" for index in range(5)]
    assert all(set(row) == {"id", "number", "category", "created_at"} for row in summaries)
    assert all(datetime.fromisoformat(row["created_at"]).utcoffset() == timedelta(0) for row in summaries)
    filter_query = {"status": "new", "assignee_id": "unassigned", "priority": "high", "category": "inquiry", "page_size": 4}
    first = checked(client.get(f"{ADMIN}/tickets", params=filter_query, headers=auth()))
    second = checked(client.get(f"{ADMIN}/tickets", params={**filter_query, "page": 2}, headers=auth()))
    assert first["total"] == second["total"] == 6
    assert len(first["items"]) == 4 and len(second["items"]) == 2
    assert all(row["status"] == "new" and row["assignee"] is None and row["priority"] == "high"
               for row in first["items"] + second["items"])
    assert client.get(f"{ADMIN}/tickets?priority=unknown", headers=auth()).status_code == 422

    claimed = client.post(f"{ADMIN}/tickets/high-0/claim", json={"expected_revision": 1}, headers=auth())
    assert claimed.status_code == 200
    blocked = client.post(f"{ADMIN}/tickets/high-0/claim", json={"expected_revision": 1}, headers=auth(OPERATOR_B))
    assert blocked.status_code == 409
    read = checked(client.post(f"{ADMIN}/messages/unread-{OPERATOR_A}/read", headers=auth()))
    assert read["unread_count"] == 0
    after_a, after_b = snapshot(api), snapshot(api, OPERATOR_B)
    for after in (after_a, after_b):
        assert after["work"]["unassigned_tickets"] == 6
        assert after["work"]["high_unassigned_tickets"] == 5
        assert [row["id"] for row in after["high_priority_items"]] == [f"high-{index}" for index in range(1, 6)]
    assert (after_a["work"]["my_processing_tickets"], after_b["work"]["my_processing_tickets"]) == (1, 0)
    assert (after_a["work"]["my_unread_messages"], after_b["work"]["my_unread_messages"]) == (0, 1)
    assert checked(client.get("/api/v1/tickets", headers=auth(TOURIST)))["total"] == 7
    assert checked(client.get("/api/v1/messages?unread_only=true", headers=auth(TOURIST)))["total"] == 0


def test_query_failure_does_not_return_misleading_zeros(api, monkeypatch):
    client, _ = api

    async def inaccessible(*_):
        raise RuntimeError("synthetic database error")

    monkeypatch.setattr(dashboard, "count_confirmed_trips", inaccessible)
    assert client.get(f"{ADMIN}/dashboard", headers=auth()).status_code == 500
