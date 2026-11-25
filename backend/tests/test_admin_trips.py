"""Read-only operator trip query: visibility, filters, confirmed version, permissions."""

import asyncio
import base64
from secrets import token_bytes, token_hex

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api import deps, routes
from app.config import settings
from app.db import database
from app.db.models import Trip, User
from app.main import app
from app.services.auth_service import create_access_token
from app.services.trip_store import apply_draft_decision, rollback_trip, save_trip, update_trip

ADMIN = "/api/v1/admin/trips"
OPERATOR = "trip-operator"


def auth(user: str = OPERATOR):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def itinerary(title: str, budget: float = 1000.0) -> dict:
    return {
        "title": title, "destination": "成都", "duration_days": 3,
        "total_budget_estimate_cny": budget, "day_plans": [],
    }


async def seed_users(sessions, *accounts: tuple[str, str]) -> None:
    async with sessions.begin() as db:
        db.add_all([
            User(id=name, username=name, email=f"{name}@example.com",
                 password_hash="unused", role=role)
            for name, role in accounts
        ])


async def seed_trip(sessions, thread: str, user: str, *, status: str = "completed",
                    title: str = "成都3日", destination: str = "成都") -> str:
    async with sessions.begin() as db:
        trip = await save_trip(
            db, thread,
            {"itinerary": itinerary(title), "travel_request": {"destination": destination, "days": 3}},
            user, status=status,
        )
        if destination != trip.destination:
            trip.destination = destination
            await db.flush()
        return trip.id


async def ensure_operator(sessions) -> None:
    await seed_users(sessions, (OPERATOR, "operator"))


async def confirm(sessions, trip_id: str, user: str, version: int = 1):
    async with sessions.begin() as db:
        return await apply_draft_decision(db, trip_id, user, version, None)


async def check_draft_hidden(sessions, client):
    await ensure_operator(sessions)
    await seed_users(sessions, ("draft-owner", "tourist"))
    draft = await seed_trip(sessions, "t-draft", "draft-owner", status="draft")

    listing = client.get(ADMIN, params={"username": "draft-owner"}, headers=auth())
    assert listing.status_code == 200, listing.text
    assert draft not in [item["id"] for item in listing.json()["items"]]
    assert client.get(f"{ADMIN}/{draft}", headers=auth()).status_code == 404
    assert client.get(f"{ADMIN}/{draft}/versions/1", headers=auth()).status_code == 404


async def check_list_filters(sessions, client):
    await ensure_operator(sessions)
    await seed_users(sessions, ("alpha", "tourist"), ("beta", "tourist"))
    alpha = await seed_trip(sessions, "t-alpha", "alpha", title="成都3日")
    beta = await seed_trip(sessions, "t-beta", "beta", title="上海4日", destination="上海")

    by_user = client.get(ADMIN, params={"username": "alph"}, headers=auth()).json()
    assert [item["id"] for item in by_user["items"]] == [alpha]
    assert by_user["items"][0]["username"] == "alpha"

    by_missing = client.get(ADMIN, params={"username": "nobody-here"}, headers=auth()).json()
    assert by_missing["total"] == 0

    everything = client.get(ADMIN, headers=auth()).json()
    ids = {item["id"] for item in everything["items"]}
    assert {alpha, beta} <= ids

    by_destination = client.get(ADMIN, params={"destination": "上海"}, headers=auth()).json()
    assert [item["id"] for item in by_destination["items"]] == [beta]

    empty_page = client.get(ADMIN, params={"page": 9, "page_size": 2}, headers=auth()).json()
    assert empty_page["items"] == []


async def check_confirm_records_version(sessions, client):
    await ensure_operator(sessions)
    await seed_users(sessions, ("gamma", "tourist"))
    trip = await seed_trip(sessions, "t-gamma", "gamma", status="draft")

    _, newly_confirmed = await confirm(sessions, trip, "gamma")
    assert newly_confirmed is True

    detail = client.get(f"{ADMIN}/{trip}", headers=auth()).json()
    assert detail["status"] == "completed"
    assert detail["version"] == 1
    assert detail["confirmed_version"] == 1
    assert [item["version"] for item in detail["versions"] if item["is_confirmed"]] == [1]
    assert [item["version"] for item in detail["versions"] if item["is_current"]] == [1]
    assert detail["itinerary"]["title"] == "成都3日"


async def check_edit_after_confirm(sessions, client):
    await ensure_operator(sessions)
    await seed_users(sessions, ("delta", "tourist"))
    trip = await seed_trip(sessions, "t-delta", "delta", status="draft")
    await confirm(sessions, trip, "delta")

    async with sessions.begin() as db:
        await update_trip(db, trip, itinerary("成都3日改"), user_id="delta")

    detail = client.get(f"{ADMIN}/{trip}", headers=auth()).json()
    assert detail["version"] == 2
    assert detail["confirmed_version"] == 1
    assert [item["version"] for item in detail["versions"] if item["is_current"]] == [2]
    assert [item["version"] for item in detail["versions"] if item["is_confirmed"]] == [1]

    version = client.get(f"{ADMIN}/{trip}/versions/2", headers=auth()).json()
    assert version["is_current"] is True and version["is_confirmed"] is False
    assert version["itinerary"]["title"] == "成都3日改"


async def check_rollback_keeps_confirmed_version(sessions, client):
    await ensure_operator(sessions)
    await seed_users(sessions, ("epsilon", "tourist"))
    trip = await seed_trip(sessions, "t-epsilon", "epsilon", status="draft")
    await confirm(sessions, trip, "epsilon")
    async with sessions.begin() as db:
        await update_trip(db, trip, itinerary("成都3日改"), user_id="epsilon")
    async with sessions.begin() as db:
        await rollback_trip(db, trip, 1, user_id="epsilon")

    # A rollback appends a new version holding the target content; it never rewinds
    # the version counter, so v1 (first), v2 (edit), v3 (rollback) all stay readable.
    detail = client.get(f"{ADMIN}/{trip}", headers=auth()).json()
    assert detail["version"] == 3
    assert detail["confirmed_version"] == 1
    assert [item["version"] for item in detail["versions"] if item["is_current"]] == [3]
    assert [item["version"] for item in detail["versions"] if item["is_confirmed"]] == [1]

    rolled_back = client.get(f"{ADMIN}/{trip}/versions/3", headers=auth()).json()
    assert rolled_back["itinerary"]["title"] == "成都3日"
    assert rolled_back["description"].startswith("回滚到版本 1")


async def check_repeat_confirm_is_idempotent(sessions, client):
    await ensure_operator(sessions)
    await seed_users(sessions, ("zeta", "tourist"))
    trip = await seed_trip(sessions, "t-zeta", "zeta", status="draft")

    _, first = await confirm(sessions, trip, "zeta")
    _, second = await confirm(sessions, trip, "zeta")
    assert first is True and second is False

    detail = client.get(f"{ADMIN}/{trip}", headers=auth()).json()
    assert detail["confirmed_version"] == 1


async def check_legacy_trip_without_confirmed_version(sessions, client):
    await ensure_operator(sessions)
    await seed_users(sessions, ("legacy", "tourist"))
    trip = await seed_trip(sessions, "t-legacy", "legacy", status="completed")
    async with sessions.begin() as db:
        await db.execute(update(Trip).where(Trip.id == trip).values(confirmed_version=None))

    detail = client.get(f"{ADMIN}/{trip}", headers=auth())
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["confirmed_version"] is None
    assert [item["version"] for item in body["versions"] if item["is_confirmed"]] == []


async def check_permissions_and_read_only(sessions, client):
    await ensure_operator(sessions)
    await seed_users(sessions, ("tourist-user", "tourist"))
    trip = await seed_trip(sessions, "t-perm", "tourist-user")

    assert client.get(ADMIN).status_code == 401
    assert client.get(ADMIN, headers=auth("tourist-user")).status_code == 403
    assert client.get(f"{ADMIN}/{trip}", headers=auth("tourist-user")).status_code == 403
    assert client.get(ADMIN, headers=auth()).status_code == 200

    assert client.post(ADMIN, headers=auth()).status_code == 405
    assert client.patch(f"{ADMIN}/{trip}", headers=auth(), json={}).status_code == 405
    assert client.delete(f"{ADMIN}/{trip}", headers=auth()).status_code == 405


async def check_migration_adds_missing_column(sessions, client):
    from app.db.trip_operator_migration import ensure_trip_operator_support

    engine = sessions.kw["bind"]

    def schema(connection):
        return (
            [column["name"] for column in inspect(connection).get_columns("trips")],
            [index["name"] for index in inspect(connection).get_indexes("trips")],
        )

    async with engine.begin() as conn:
        await conn.exec_driver_sql("ALTER TABLE trips DROP COLUMN confirmed_version")
        columns, _ = await conn.run_sync(schema)
    assert "confirmed_version" not in columns

    async with engine.begin() as conn:
        await conn.run_sync(ensure_trip_operator_support)
        columns, indexes = await conn.run_sync(schema)
        # Running twice must stay a no-op.
        await conn.run_sync(ensure_trip_operator_support)

    assert "confirmed_version" in columns
    assert "ix_trips_user_status_updated" in indexes


SCENARIOS = [
    check_draft_hidden,
    check_list_filters,
    check_confirm_records_version,
    check_edit_after_confirm,
    check_rollback_keeps_confirmed_version,
    check_repeat_confirm_is_idempotent,
    check_legacy_trip_without_confirmed_version,
    check_permissions_and_read_only,
    check_migration_adds_missing_column,
]


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = database.create_db_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'admin_trips.db'}", poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    for module in (database, deps, routes):
        monkeypatch.setattr(module, "async_session", factory)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
    monkeypatch.setattr(settings, "pii_encryption_key", "unused-in-this-suite")
    asyncio.run(database.init_db())
    yield factory
    asyncio.run(engine.dispose())


@pytest.fixture
def api(sessions):
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.__name__.removeprefix("check_"))
def test_operator_trip_query(api, sessions, scenario):
    asyncio.run(scenario(sessions, api))
