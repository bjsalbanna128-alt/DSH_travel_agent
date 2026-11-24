import asyncio
from datetime import datetime, timedelta, timezone
from secrets import token_hex
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.websockets import WebSocketDisconnect

from app.api import chat, deps, routes, sse, ws
from app.config import settings
from app.db.database import Base, get_db
from app.db.models import User, UserProfile
from app.main import app
from app.services import chroma_store, user_profile_store
from app.services.auth_service import create_access_token
from app.services.trip_store import save_trip


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
    monkeypatch.setattr(deps, "async_session", sessions)
    monkeypatch.setattr(routes, "async_session", sessions)
    monkeypatch.setattr(sse, "async_session", sessions)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions.begin() as db:
            db.add_all([
                User(id="alice", username="alice", email="alice@example.com", password_hash="unused"),
                User(id="bob", username="bob", email="bob@example.com", password_hash="unused"),
                UserProfile(user_id="alice", interest_tags=["甲的偏好"]),
                UserProfile(user_id="bob", interest_tags=["乙的偏好"]),
            ])
            await save_trip(
                db, "owned-thread", {"itinerary": {"title": "原行程", "version": 1}}, "alice"
            )
            await save_trip(
                db, "old-thread", {"itinerary": {"title": "历史匿名行程"}}, "anonymous"
            )

    async def use_test_session():
        async with sessions.begin() as db:
            yield db

    asyncio.run(setup())
    monkeypatch.setitem(app.dependency_overrides, get_db, use_test_session)
    with_client = TestClient(app)
    try:
        yield with_client
    finally:
        with_client.close()
        asyncio.run(engine.dispose())


def bearer(user_id):
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/chat/clarify", {"query": "成都 3 天"}),
        ("POST", "/trips/stream", {"query": "成都 3 天"}),
        ("POST", "/trips/resume", {"thread_id": "thread"}),
        ("GET", "/trips", None),
        ("GET", "/trips/trip", None),
        ("GET", "/trips/trip/versions", None),
        ("PUT", "/trips/trip", {"itinerary": {"title": "修改"}}),
        ("POST", "/trips/trip/rollback/1", None),
        ("GET", "/profile", None),
    ],
)
def test_business_routes_require_authentication(client, method, path, body):
    response = client.request(method, f"/api/v1{path}", json=body)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_invalid_expired_and_unknown_account_tokens(client):
    expired = jwt.encode(
        {"sub": "alice", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    missing_expiry = jwt.encode(
        {"sub": "alice"}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    for token in ("invalid", expired, missing_expiry, create_access_token("missing-user")):
        response = client.get("/api/v1/trips", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_public_registration_login_and_health(client):
    assert client.get("/health").status_code == 200
    created = client.post("/api/v1/auth/register", json={
        "username": "new-user", "email": "new@example.com", "password": "test-password"
    })
    assert created.status_code == 200
    login = client.post("/api/v1/auth/login", json={
        "username": "new-user", "password": "test-password"
    })
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/trips", headers=headers).json()["trips"] == []


def test_trips_versions_and_profile_use_authenticated_owner(client):
    alice = bearer("alice")
    bob = bearer("bob")
    trips = client.get("/api/v1/trips?user_id=bob", headers=alice).json()["trips"]
    assert [trip["title"] for trip in trips] == ["原行程"]
    assert client.get("/api/v1/trips?user_id=alice", headers=bob).json()["trips"] == []
    profile = client.get("/api/v1/profile?user_id=alice", headers=bob).json()["profile"]
    assert profile["interest_tags"] == ["乙的偏好"]

    path = f"/api/v1/trips/{trips[0]['id']}"
    assert client.get(path, headers=bob).status_code == 404
    assert client.get(f"{path}/versions", headers=bob).status_code == 404
    assert client.put(path, headers=bob, json={"itinerary": {"title": "别人的修改"}}).status_code == 404
    assert client.post(f"{path}/rollback/1", headers=bob).status_code == 404
    assert client.get(path, headers=alice).json()["itinerary"]["title"] == "原行程"

    edited = client.put(path, headers=alice, json={"itinerary": {"title": "新行程"}})
    assert edited.status_code == 200
    versions = client.get(f"{path}/versions", headers=alice)
    assert [item["version"] for item in versions.json()["versions"]] == [2, 1]
    restored = client.post(f"{path}/rollback/1", headers=alice)
    assert restored.status_code == 200
    assert restored.json()["itinerary"]["title"] == "原行程"


@pytest.fixture
def graph(monkeypatch):
    class Graph:
        def __init__(self):
            self.states = {}
            self.resumed = []

        async def astream(self, state, config):
            key = config["configurable"]["thread_id"]
            if isinstance(state, dict):
                self.states[key] = state
                yield {"itinerary_compiler_node": {"itinerary": {
                    "title": state["messages"][0].content, "version": 1
                }}}
            else:
                self.resumed.append(self.states[key]["user_id"])
                yield {"human_approval_node": {}}

        async def aget_state(self, config):
            key = config["configurable"]["thread_id"]
            return SimpleNamespace(values=self.states.get(key, {}))

    async def no_profile(*args, **kwargs):
        return None

    async def clarify(*args, **kwargs):
        return {"action": "ask", "message": "计划几天？"}

    graph = Graph()
    monkeypatch.setattr(sse, "travel_graph", graph)
    monkeypatch.setattr(ws, "travel_graph", graph)
    monkeypatch.setattr(chat, "clarify_node", clarify)
    monkeypatch.setattr(ws, "clarify_node", clarify)
    monkeypatch.setattr(user_profile_store, "get_profile_context", no_profile)
    monkeypatch.setattr(user_profile_store, "update_from_trip", no_profile)
    monkeypatch.setattr(chroma_store, "get_chroma_store", lambda: SimpleNamespace(
        search_similar_trips=lambda **kwargs: [], add_trip_episode=lambda **kwargs: None
    ))
    return graph


def test_sse_identity_session_resume_and_existing_trip_isolation(client, graph):
    alice = bearer("alice")
    bob = bearer("bob")
    clarify = client.post("/api/v1/chat/clarify", headers=alice, json={"query": "成都"})
    assert clarify.json()["action"] == "ask"
    body = {"query": "Alice 的规划", "thread_id": "new-thread", "user_id": "bob"}
    planned = client.post("/api/v1/trips/stream", headers=alice, json=body)
    assert planned.status_code == 200
    assert "event: done" in planned.text
    trips = client.get("/api/v1/trips", headers=alice).json()["trips"]
    new_trip = next(trip for trip in trips if trip["thread_id"] == "new-thread")
    assert new_trip["user_id"] == "alice"

    resume = {"thread_id": "new-thread"}
    assert client.post("/api/v1/trips/resume", headers=bob, json=resume).status_code == 404
    assert client.post("/api/v1/trips/resume", headers=alice, json=resume).status_code == 200
    assert graph.resumed == ["alice"]

    collision = client.post("/api/v1/trips/stream", headers=bob, json={
        **body, "query": "Bob 的规划"
    })
    assert "event: error" in collision.text
    assert "event: done" not in collision.text
    assert client.get(f"/api/v1/trips/{new_trip['id']}", headers=alice).json()["title"] == "Alice 的规划"
    assert client.get("/api/v1/trips", headers=bob).json()["trips"] == []


@pytest.mark.parametrize("message", [
    {"type": "chat", "query": "成都"},
    {"type": "auth", "token": "invalid"},
])
def test_websocket_rejects_business_messages_before_authentication(client, message):
    with client.websocket_connect("/ws/chat/thread") as socket:
        socket.send_json(message)
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 1008


def test_websocket_authenticates_and_cannot_resume_another_account_session(client, graph):
    body = {"thread_id": "ws-thread", "query": "Alice 的规划"}
    assert client.post("/api/v1/trips/stream", headers=bearer("alice"), json=body).status_code == 200
    with client.websocket_connect("/ws/chat/ws-thread") as socket:
        socket.send_json({"type": "auth", "token": create_access_token("bob")})
        assert socket.receive_json()["type"] == "authenticated"
        socket.send_json({"type": "resume", "user_id": "alice"})
        assert socket.receive_json() == {"type": "error", "message": "规划会话不存在"}
        socket.send_json({"type": "chat", "query": "成都"})
        assert socket.receive_json()["type"] == "clarify"
    assert graph.resumed == []
