import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from secrets import token_hex
from struct import pack
from threading import Barrier
from zlib import crc32

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api import deps
from app.config import settings
from app.db import database
from app.db.models import User
from app.db.recommendation_models import Recommendation, RecommendationImage, RecommendationVersion
from app.db.resource_models import Supplier
from app.db.template_models import ItineraryTemplate
from app.main import app
from app.services.auth_service import create_access_token
from app.services.recommendation_images import MAX_IMAGE_BYTES

ADMIN = "/api/v1/admin/recommendations"
READER = "/api/v1/recommendations"


def auth(account="editor-one"):
    return {"Authorization": f"Bearer {create_access_token(account)}"}


@pytest.fixture
def engine(tmp_path, monkeypatch):
    engine = database.create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'recommendations.db'}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", sessions)
    monkeypatch.setattr(deps, "async_session", sessions)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
    yield engine
    asyncio.run(engine.dispose())


@pytest.fixture
def api(engine):
    async def setup():
        await database.init_db()
        async with database.async_session.begin() as db:
            db.add_all([
                User(id=account, username=account, email=f"{account}@example.test", password_hash="unused", role=role)
                for account, role in (("editor-one", "operator"), ("editor-two", "operator"), ("guest", "tourist"))
            ])

    asyncio.run(setup())
    # The real lifespan warms external providers. The routes use isolated storage here.
    client = TestClient(app, raise_server_exceptions=False)
    client.headers.update(auth())
    try:
        yield client
    finally:
        client.close()


def picture(fmt="PNG", color="green", size=(32, 18), animate=False):
    buffer = BytesIO()
    image = Image.new("RGB", size, color)
    options = {"save_all": True, "append_images": [Image.new("RGB", size, "blue")], "duration": 300} if animate else {}
    image.save(buffer, format=fmt, **options)
    return buffer.getvalue()


def maximum_png():
    png = picture()
    text = b"tEXtComment\x00".ljust(MAX_IMAGE_BYTES - len(png) - 8, b"x")
    return png[:-12] + pack(">I", len(text) - 4) + text + pack(">I", crc32(text)) + png[-12:]


def fields(title="湖畔散步", order=100):
    return {"title": title, "place": "杭州西湖", "short_text": "沿湖慢慢走。", "display_order": order}


def ok(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()


def draft_url(row):
    return f"{ADMIN}/{row['id']}"


def cover_url(row):
    return f"{draft_url(row)}/draft/cover"


def upload(api, row, image, **kwargs):
    return api.put(cover_url(row), params={"expected_revision": row["revision"]}, content=image, **kwargs)


def action(api, row, name="publish"):
    return api.post(f"{draft_url(row)}/{name}", json={"expected_revision": row["revision"]})


def save(api, row, data, **kwargs):
    return api.put(f"{draft_url(row)}/draft", json={**data, "expected_revision": row["revision"]}, **kwargs)


def create(api, data):
    return ok(api.post(ADMIN, json=data), 201)


def feed(api):
    response = api.get(READER, headers=auth("guest"))
    assert response.headers["cache-control"] == "private, no-store"
    return ok(response)


def test_initial_draft_permissions_and_publication_requirements(api):
    anonymous = {"Authorization": ""}
    guest = auth("guest")
    row = create(api, {"title": "  湖畔散步  "})
    assert (row["title"], row["display_order"], row["visibility"], row["revision"]) == ("湖畔散步", 100, "draft", 1)
    for method, url in (
        ("GET", ADMIN), ("POST", ADMIN), ("GET", draft_url(row)),
        ("PUT", f"{draft_url(row)}/draft"), ("GET", cover_url(row)), ("PUT", cover_url(row)),
        ("POST", f"{draft_url(row)}/publish"), ("POST", f"{draft_url(row)}/unpublish"),
    ):
        assert api.request(method, url, headers=anonymous).status_code == 401
        assert api.request(method, url, headers=guest).status_code == 403
    assert api.get(READER, headers=anonymous).status_code == 401
    published_cover = f"{READER}/{row['id']}/versions/1/cover"
    assert api.get(published_cover, headers=anonymous).status_code == 401
    assert api.get(published_cover, headers=guest).status_code == 404
    assert feed(api) == []
    denied = ok(action(api, row), 422)
    assert {issue["path"][0] for issue in denied["detail"]["errors"]} == {"place", "short_text", "cover"}
    for data in ({"title": " "}, {"title": "字" * 41}, {**fields(), "display_order": -1},
                 {**fields(), "display_order": 1.5}, {**fields(), "place": "字" * 101}, {**fields(), "short_text": "字" * 201}):
        assert api.post(ADMIN, json=data).status_code == 422
    assert ok(api.get(draft_url(row)))["revision"] == 1


def test_snapshot_replaces_copy_cover_and_position_together(api):
    blue, green = picture(color="blue"), picture()
    first = create(api, fields("水边", 10))
    first = ok(action(api, ok(upload(api, first, blue))))
    second = create(api, fields("街区", 20))
    second = ok(action(api, ok(upload(api, second, blue))))
    old, _ = feed(api)
    assert set(old) == {"id", "version", "title", "place", "short_text", "cover_url"}
    old_bytes = api.get(old["cover_url"])
    assert old_bytes.content == blue and old_bytes.headers["content-type"] == "image/png"
    assert old_bytes.headers["cache-control"] == "private, no-store" and old_bytes.headers["x-content-type-options"] == "nosniff"
    pending = ok(save(api, first, {**fields("新的水边", 30), "short_text": "<b>按纯文本阅读</b>"}, headers=auth("editor-two")))
    pending = ok(upload(api, pending, green))
    assert pending["has_unpublished_changes"] and pending["cover"]["id"] != first["cover"]["id"]
    assert api.get(cover_url(pending)).content == green
    assert api.get(old["cover_url"]).content == blue
    assert feed(api)[0] == old
    filtered = ok(api.get(ADMIN, params={"title": "新的", "place": "杭州", "visibility": "published", "page_size": 1}))
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == first["id"]

    current = ok(action(api, pending))
    assert current["published_version"] == 2 and not current["has_unpublished_changes"]
    assert [item["id"] for item in feed(api)] == [second["id"], first["id"]]
    latest = feed(api)[-1]
    assert latest["short_text"] == "<b>按纯文本阅读</b>"
    assert api.get(latest["cover_url"]).content == green
    assert api.get(old["cover_url"]).status_code == 404
    no_change = ok(action(api, current))
    assert (no_change["revision"], no_change["published_version"]) == (current["revision"], 2)
    assert action(api, pending).status_code == 409

    hidden = ok(action(api, current, "unpublish"))
    assert [item["id"] for item in feed(api)] == [second["id"]]
    assert api.get(latest["cover_url"]).status_code == 404
    assert api.get(cover_url(hidden)).content == green
    assert ok(action(api, hidden))["published_version"] == 3

    async def check_history():
        async with database.async_session() as db:
            versions = await db.scalars(select(RecommendationVersion).where(RecommendationVersion.recommendation_id == first["id"])
                .order_by(RecommendationVersion.version))
            assert [(v.version, v.cover_id) for v in versions] == [
                (1, first["cover"]["id"]), (2, pending["cover"]["id"]), (3, pending["cover"]["id"]),
            ]
            image = await db.get(RecommendationImage, first["cover"]["id"])
            await db.refresh(image, ["content"])
            assert image.content == blue

    asyncio.run(check_history())


@pytest.mark.parametrize(("fmt", "mime"), [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
def test_upload_uses_real_format(api, fmt, mime):
    row = create(api, fields())
    raw = picture(fmt)
    attached = ok(upload(api, row, raw, headers={"Content-Type": "application/octet-stream"}))
    assert attached["cover"]["mime"] == mime and attached["cover"]["size_bytes"] == len(raw)
    assert api.get(cover_url(row)).content == raw


def test_invalid_and_exact_upload_limits_preserve_previous_cover(api):
    row = create(api, fields())
    raw = maximum_png()
    assert len(raw) == MAX_IMAGE_BYTES
    with_cover = ok(upload(api, row, raw))
    for bad, code in (
        (b"<svg></svg>", 415), (picture("GIF"), 415), (b"", 422),
        (picture()[:30], 422), (picture("JPEG")[:-15], 422),
        (picture("PNG", animate=True), 422), (picture("WEBP", animate=True), 422),
        (picture(size=(4001, 4000)), 422), (raw + b"x", 413),
        (iter((raw[:3], raw[3:], b"x")), 413),
    ):
        response = upload(api, with_cover, bad, headers={"Content-Type": "image/png"})
        assert response.status_code == code, response.text
    assert api.get(cover_url(row)).content == raw
    assert upload(api, row, picture()).status_code == 409
    replacement = ok(upload(api, with_cover, picture()))

    async def check_cleanup():
        async with database.async_session() as db:
            assert list(await db.scalars(select(RecommendationImage.id))) == [replacement["cover"]["id"]]

    asyncio.run(check_cleanup())


def test_equal_order_concurrency_and_publish_rollback(api):
    raw = picture()
    row = ok(upload(api, create(api, fields()), raw))
    other = ok(action(api, ok(upload(api, create(api, fields("老街")), raw))))

    def race(method, endpoint, payload):
        barrier = Barrier(2)

        def request(account):
            client = TestClient(app, raise_server_exceptions=False)
            try:
                barrier.wait(timeout=5)
                return client.request(method, f"{draft_url(row)}/{endpoint}", headers=auth(account), json=payload).status_code
            finally:
                client.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return sorted(pool.map(request, ("editor-one", "editor-two")))

    assert race("PUT", "draft", {**fields("改过标题"), "expected_revision": row["revision"]}) == [200, 409]
    saved = ok(api.get(draft_url(row)))
    assert race("POST", "publish", {"expected_revision": saved["revision"]}) == [200, 409]
    assert [item["id"] for item in feed(api)] == sorted([row["id"], other["id"]])
    published = ok(api.get(draft_url(row)))
    invalid = ok(save(api, published, {**fields(), "place": ""}))
    assert action(api, invalid).status_code == 422
    pending = ok(save(api, invalid, fields("待发布标题")))

    def fail_insert(*args):
        raise RuntimeError("simulated version insert failure")

    event.listen(RecommendationVersion, "after_insert", fail_insert)
    try:
        assert action(api, pending).status_code == 500
    finally:
        event.remove(RecommendationVersion, "after_insert", fail_insert)
    current = next(item for item in feed(api) if item["id"] == row["id"])
    assert (current["title"], current["version"], api.get(current["cover_url"]).content) == ("改过标题", 1, raw)
    assert ok(api.get(draft_url(row)))["revision"] == pending["revision"]
    assert ok(action(api, pending))["published_version"] == 2


def test_initialize_existing_database_twice_and_reopen_published_cover(engine):
    async def check():
        new_tables = {Recommendation.__table__, RecommendationImage.__table__, RecommendationVersion.__table__}
        async with engine.begin() as conn:
            existing = [table for table in database.Base.metadata.sorted_tables if table not in new_tables]
            await conn.run_sync(lambda sync: database.Base.metadata.create_all(sync, tables=existing))
            await conn.execute(User.__table__.insert().values(
                id="editor-one", username="old-editor", email="old@example.test", password_hash="unused", role="operator",
            ))
            await conn.execute(Supplier.__table__.insert().values(
                id="existing-supplier", name="旧供应商", settlement_name="旧结算主体",
            ))
            await conn.execute(ItineraryTemplate.__table__.insert().values(
                id="existing-template", title="旧模板", destination="杭州", days_count=1,
                draft={"title": "旧模板"}, draft_hash="old",
                created_by="editor-one", updated_by="editor-one",
            ))
        await database.init_db()
        async with engine.begin() as conn:
            names = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
            assert {table.name for table in new_tables} <= names
            assert await conn.scalar(select(Supplier.name)) == "旧供应商"
            assert await conn.scalar(select(ItineraryTemplate.title)) == "旧模板"
            assert await conn.scalar(select(User.username)) == "old-editor"

    asyncio.run(check())
    client = TestClient(app, raise_server_exceptions=False)
    try:
        client.headers.update(auth())
        raw = picture()
        ok(action(client, ok(upload(client, create(client, fields()), raw))))
        cover, = ok(client.get(READER))
        asyncio.run(engine.dispose())
        asyncio.run(database.init_db())
        assert client.get(cover["cover_url"]).content == raw
    finally:
        client.close()
