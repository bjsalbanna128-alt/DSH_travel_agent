import asyncio
from datetime import datetime, timedelta, timezone
from secrets import token_hex

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api import deps
from app.config import settings
from app.db import database
from app.db.models import Trip
from app.main import app
from app.services.auth_service import create_access_token, hash_password
from scripts import set_user_role

PASSWORD = "role-test-password"
ADMIN = "/api/v1/admin/session"
AUTH = "/api/v1/auth"


@pytest.fixture
def role_environment(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'roles.db'}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", sessions)
    monkeypatch.setattr(deps, "async_session", sessions)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))

    client = TestClient(app)
    try:
        yield client, engine
    finally:
        client.close()
        asyncio.run(engine.dispose())


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def register(client, username):
    response = client.post(f"{AUTH}/register", json={
        "username": username, "email": f"{username}@example.com", "password": PASSWORD,
    })
    assert response.status_code == 200
    return response.json()


def login(client, username):
    response = client.post(f"{AUTH}/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()


def run_role_command(username, role):
    return set_user_role.main(["--username", username, "--role", role])


def test_new_database_defaults_to_tourist_and_rejects_self_assigned_roles(role_environment):
    client, engine = role_environment
    asyncio.run(database.init_db())
    for role in ("operator", "tourist", None):
        response = client.post(f"{AUTH}/register", json={
            "username": "visitor", "email": "visitor@example.com", "password": PASSWORD,
            "role": role,
        })
        assert response.status_code == 422

    data = register(client, "visitor")
    assert set(data) == {"user_id", "username", "role", "access_token", "token_type"}
    assert data["role"] == "tourist"
    assert client.get(f"{AUTH}/me", headers=bearer(data["access_token"])).json() == {
        "user_id": data["user_id"], "username": "visitor", "role": "tourist",
    }

    async def check_database_default():
        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO users (id, username, email, password_hash) "
                "VALUES ('direct', 'direct', 'direct@example.com', 'unused')"
            ))
            assert await conn.scalar(text("SELECT role FROM users WHERE id = 'direct'")) == "tourist"
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(text("UPDATE users SET role = 'other' WHERE id = 'direct'"))

    asyncio.run(check_database_default())


def test_legacy_startup_preserves_login_trip_and_role_on_repeat(role_environment):
    client, engine = role_environment
    old_hash = hash_password(PASSWORD)

    async def seed_legacy_schema():
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE users (
                    id VARCHAR(36) PRIMARY KEY, username VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL,
                    created_at DATETIME, updated_at DATETIME
                )
            """))
            await conn.execute(text(
                "INSERT INTO users (id, username, email, password_hash) "
                "VALUES ('old-id', 'legacy', 'legacy@example.com', :password_hash)"
            ), {"password_hash": old_hash})
            await conn.run_sync(Trip.__table__.create)
            await conn.execute(Trip.__table__.insert().values(
                id="old-trip", thread_id="old-thread", user_id="old-id", title="已有行程",
            ))

    asyncio.run(seed_legacy_schema())
    old_token = create_access_token("old-id")
    asyncio.run(database.init_db())

    data = login(client, "legacy")
    assert data["role"] == "tourist"
    assert data["user_id"] == "old-id"
    headers = bearer(old_token)
    trips = client.get("/api/v1/trips", headers=headers).json()["trips"]
    assert [trip["id"] for trip in trips] == ["old-trip"]

    assert run_role_command("legacy", "operator") == 0
    asyncio.run(database.init_db())
    assert client.get(ADMIN, headers=headers).json() == {
        "user_id": "old-id", "username": "legacy", "role": "operator",
    }
    assert login(client, "legacy")["role"] == "operator"


def test_operator_authorization_and_revocation_apply_to_existing_tokens(role_environment, capsys):
    client, _ = role_environment
    asyncio.run(database.init_db())
    alice = register(client, "alice")
    bob = register(client, "bob")
    tourist = register(client, "tourist")

    assert run_role_command("alice", "operator") == 0
    assert run_role_command("bob", "operator") == 0
    assert run_role_command("bob", "operator") == 0
    assert run_role_command("missing", "operator") != 0
    with pytest.raises(SystemExit) as error:
        run_role_command("tourist", "administrator")
    assert error.value.code != 0
    command_output = capsys.readouterr()
    assert "alice: tourist -> operator" in command_output.out
    assert "bob: tourist -> operator" in command_output.out
    assert "bob: operator -> operator" in command_output.out
    assert "账号不存在：missing" in command_output.err
    assert client.post(f"{AUTH}/login", json={
        "username": "missing", "password": PASSWORD,
    }).status_code == 401

    expired = jwt.encode(
        {"sub": alice["user_id"], "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )
    for headers in ({}, bearer(expired), bearer("invalid"), bearer(create_access_token("missing"))):
        for path in (f"{AUTH}/me", ADMIN):
            response = client.get(path, headers=headers)
            assert response.status_code == 401
            assert response.headers["WWW-Authenticate"] == "Bearer"
    assert client.get(f"{ADMIN}?role=operator", headers={
        **bearer(tourist["access_token"]), "X-Role": "operator",
    }).status_code == 403

    for data in (alice, bob):
        expected = {"user_id": data["user_id"], "username": data["username"], "role": "operator"}
        session = client.get(ADMIN, headers=bearer(data["access_token"]))
        assert session.status_code == 200
        assert session.json() == expected
        logged_in = login(client, data["username"])
        assert logged_in["role"] == "operator"
        assert client.get(ADMIN, headers=bearer(logged_in["access_token"])).json() == expected

    assert run_role_command("alice", "tourist") == 0
    assert "alice: operator -> tourist" in capsys.readouterr().out
    assert client.get(ADMIN, headers=bearer(alice["access_token"])).status_code == 403
    assert client.get(f"{AUTH}/me", headers=bearer(alice["access_token"])).json()["role"] == "tourist"
    assert client.get(ADMIN, headers=bearer(bob["access_token"])).status_code == 200


def test_operator_does_not_gain_access_to_other_users_trips(role_environment):
    client, engine = role_environment
    asyncio.run(database.init_db())
    visitor = register(client, "visitor")
    operator = register(client, "operator")
    assert run_role_command("operator", "operator") == 0

    async def seed_trips():
        async with engine.begin() as conn:
            await conn.execute(Trip.__table__.insert(), [
                {"id": "visitor-trip", "thread_id": "visitor-thread", "user_id": visitor["user_id"]},
                {"id": "operator-trip", "thread_id": "operator-thread", "user_id": operator["user_id"]},
            ])

    asyncio.run(seed_trips())
    for data, own, other in (
        (visitor, "visitor-trip", "operator-trip"), (operator, "operator-trip", "visitor-trip"),
    ):
        headers = bearer(data["access_token"])
        assert client.get(f"/api/v1/trips/{own}", headers=headers).status_code == 200
        assert client.get(f"/api/v1/trips/{other}", headers=headers).status_code == 404
        trips = client.get("/api/v1/trips", headers=headers).json()["trips"]
        assert [trip["id"] for trip in trips] == [own]
