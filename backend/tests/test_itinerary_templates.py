import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from secrets import token_hex
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api import deps
from app.config import settings
from app.db import database
from app.db.models import Trip, TripVersion, User
from app.db.resource_models import PriceOffer, Product, Supplier
from app.db.template_models import ItineraryTemplate, ItineraryTemplateVersion
from app.main import app
from app.services.auth_service import create_access_token

READER = "/api/v1/itinerary-templates"
ADMIN = "/api/v1/admin/itinerary-templates"
RESOURCE = "/api/v1/admin"


def auth(account="operator-one"):
    return {"Authorization": f"Bearer {create_access_token(account)}"}


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    engine = database.create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'templates.db'}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", sessions)
    monkeypatch.setattr(deps, "async_session", sessions)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
    try:
        yield engine
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def api(isolated_db):
    async def initialize():
        await database.init_db()
        async with database.async_session.begin() as db:
            db.add_all([
                User(id=account, username=account, password_hash="unused", email=f"{account}@example.com", role=role)
                for account, role in (("operator-one", "operator"), ("operator-two", "operator"), ("guest", "tourist"))
            ])

    asyncio.run(initialize())
    with_client = TestClient(app, raise_server_exceptions=False)
    with_client.headers.update(auth())
    try:
        yield with_client
    finally:
        with_client.close()


def sample(name="成都亲子三日游", destination="成都"):
    def activity(name, category="sightseeing"):
        return {"time": "上午", "name": name, "category": category, "description": "自由参观"}

    return {
        "title": name, "destination": destination, "tags": ["亲子"],
        "description": "慢节奏主题游", "tips": "请携带水和雨具。",
        "days": [
            {"theme": "抵达", "activities": [activity("接站", "transport"), activity("老街散步")]},
            {"theme": "户外", "activities": [activity("公园")]},
            {"theme": "返程", "activities": [activity("送站", "transport")]},
        ],
    }


def create(api, draft):
    response = api.post(ADMIN, json=draft)
    assert response.status_code == 201, response.text
    return response.json()


def save(api, state, draft, account="operator-one"):
    response = api.put(f"{ADMIN}/{state['id']}/draft", headers=auth(account), json={
        "expected_revision": state["revision"], "draft": draft,
    })
    assert response.status_code == 200, response.text
    return response.json()


def action(api, state, name="publish"):
    return api.post(f"{ADMIN}/{state['id']}/{name}", json={"expected_revision": state["revision"]})


def reader(api, template, **kwargs):
    return api.get(f"{READER}/{template['id']}", headers=auth("guest"), **kwargs)


def resource(api):
    supplier = api.post(f"{RESOURCE}/suppliers", json={"name": "测试旅行社", "settlement_name": "非读者结算主体"})
    assert supplier.status_code == 201
    product = api.post(f"{RESOURCE}/products", json={
        "name": "接机商务车", "supplier_id": supplier.json()["id"], "type": "vehicle", "city": "成都",
        "status": "on_shelf", "attributes": {"vehicle_name": "七座车", "passenger_capacity": 6},
    })
    assert product.status_code == 201
    return supplier.json()["id"], product.json()["id"]


def test_initial_draft_validation_reordering_and_first_publication(api):
    template = create(api, {"title": "成都亲子三日游"})
    assert (template["visibility"], template["revision"], template["published_version"]) == ("draft", 1, 0)
    assert reader(api, template).status_code == 404
    assert api.get(READER, headers=auth("guest")).json() == {"items": [], "total": 0}

    blank_day = save(api, template, {"title": template["title"], "destination": "成都", "days": [{}]})
    rejected = action(api, blank_day)
    assert rejected.status_code == 422
    assert {tuple(issue["path"]) for issue in rejected.json()["detail"]["errors"]} == {
        ("days", 0, "theme"), ("days", 0, "activities"),
    }
    assert reader(api, template).status_code == 404

    draft = sample()
    draft["days"][0]["activities"].reverse()
    removed = draft["days"].pop(0)
    draft["days"].insert(1, removed)
    draft["days"][0]["notes"] = "确认的是第一天的备注。"
    saved = save(api, blank_day, draft, "operator-two")
    assert saved["created_by"] == "operator-one" and saved["updated_by"] == "operator-two"
    reloaded = api.get(f"{ADMIN}/{template['id']}").json()
    assert reloaded["draft"] == saved["draft"] and reloaded["days_count"] == 3

    published = action(api, saved)
    assert published.status_code == 200, published.text
    assert published.json()["published_version"] == 1
    response = reader(api, template)
    assert response.headers["cache-control"] == "no-store"
    visible = response.json()
    assert [day["day"] for day in visible["days"]] == [1, 2, 3]
    assert [day["theme"] for day in visible["days"]] == ["户外", "抵达", "返程"]
    assert [activity["name"] for activity in visible["days"][1]["activities"]] == ["老街散步", "接站"]
    assert visible["days"][0]["notes"] == "确认的是第一天的备注。"
    assert set(visible) == {"id", "version", "title", "destination", "days_count", "tags", "description", "published_at", "tips", "days"}


def test_reader_list_and_detail_follow_published_snapshot_only(api):
    template = create(api, sample())
    first = action(api, template).json()
    other = create(api, sample("北京城市三日游", "北京"))
    assert action(api, other).status_code == 200
    pending = sample("川西自然三日游", "川西")
    pending["days"][1]["activities"][0]["name"] = "博物馆"
    saved = save(api, first, pending)
    assert saved["has_unpublished_changes"]
    admin = api.get(ADMIN, params={"title": "川西", "destination": "川西", "visibility": "published"}).json()
    assert admin["items"][0]["title"] == pending["title"]

    guest = auth("guest")
    assert api.get(READER, headers=guest, params={"title": "川西"}).json()["total"] == 0
    unchanged = api.get(READER, headers=guest, params={"title": "成都", "destination": "成都", "days": 3}).json()
    assert unchanged["items"][0]["version"] == 1
    assert api.get(READER, headers=guest, params={"page_size": 1}).json()["items"][0]["id"] == other["id"]
    assert api.get(READER, headers=guest, params={"page": 3, "page_size": 1}).json() == {"items": [], "total": 2}
    assert reader(api, template).json()["days"][1]["activities"][0]["name"] == "公园"

    republished = action(api, saved).json()
    assert (republished["published_version"], republished["has_unpublished_changes"]) == (2, False)
    assert reader(api, template).json()["days"][1]["activities"][0]["name"] == "博物馆"
    assert api.get(READER, headers=guest, params={"title": "成都"}).json()["total"] == 0
    latest = api.get(READER, headers=guest, params={"title": "川西", "destination": "川西", "days": 3}).json()
    assert latest["items"][0]["version"] == 2
    assert api.get(READER, headers=guest, params={"page_size": 1}).json()["items"][0]["id"] == template["id"]
    same = action(api, republished).json()
    assert same["revision"] == republished["revision"] and same["message"] == "已是最新发布版本。"
    assert action(api, saved).status_code == 409


@pytest.mark.parametrize("change", ["off_shelf", "supplier_inactive", "deleted"])
def test_product_snapshot_is_reader_safe_and_publish_rechecks_live_product(api, change):
    supplier, product = resource(api)
    draft = sample()
    draft["days"][1]["activities"][0]["product_id"] = product
    first = create(api, draft)
    response = action(api, first)
    assert response.status_code == 200
    first = response.json()
    link = reader(api, first).json()["days"][1]["activities"][0]["product"]
    assert link == {"id": product, "name": "接机商务车", "type": "vehicle"}
    product_url = f"{RESOURCE}/products/{product}"
    assert api.patch(product_url, json={"name": "更名的接机车"}).status_code == 200
    assert reader(api, first).json()["days"][1]["activities"][0]["product"] == link
    saved = save(api, first, {**draft, "title": "有改动的模板"})
    if change == "off_shelf":
        assert api.patch(product_url, json={"status": "off_shelf"}).status_code == 200
        reason = "已下架"
    elif change == "supplier_inactive":
        assert api.patch(f"{RESOURCE}/suppliers/{supplier}", json={"status": "inactive"}).status_code == 200
        reason = "供应商已停用"
    else:
        assert api.delete(product_url).status_code == 204
        reason = "已不存在"

    failed = action(api, saved)
    assert failed.status_code == 422
    issue, = failed.json()["detail"]["errors"]
    assert issue["path"] == ["days", 1, "activities", 0, "product_id"]
    assert reason in issue["message"]
    assert reader(api, first).json()["version"] == 1
    if change == "deleted":
        bad_save = api.put(f"{ADMIN}/{saved['id']}/draft", json={"expected_revision": saved["revision"], "draft": draft})
        assert bad_save.status_code == 422
    no_product = deepcopy(draft)
    no_product["days"][1]["activities"][0].pop("product_id")
    repaired = save(api, saved, no_product)
    assert action(api, repaired).json()["published_version"] == 2


def test_unpublish_republish_keeps_versions_and_personal_trip(api, isolated_db):
    async def seed_trip():
        async with database.async_session.begin() as db:
            db.add(Trip(id="personal-trip", user_id="guest", thread_id="historic-thread", itinerary={"plan": "公园"}))
            db.add(TripVersion(trip_id="personal-trip", version=1, itinerary={"plan": "公园"}))

    asyncio.run(seed_trip())
    first = action(api, create(api, sample())).json()
    pending = sample()
    pending["days"][1]["activities"][0]["name"] = "博物馆"
    second = action(api, save(api, first, pending)).json()
    hidden = action(api, second, "unpublish").json()
    assert (hidden["visibility"], hidden["published_version"]) == ("unpublished", 2)
    assert reader(api, first).status_code == 404
    assert api.get(READER, headers=auth("guest")).json()["total"] == 0
    admin = api.get(f"{ADMIN}/{first['id']}").json()
    assert admin["draft"]["days"][1]["activities"][0]["name"] == "博物馆"
    third = action(api, hidden).json()
    assert third["published_version"] == 3
    assert reader(api, third).json()["version"] == 3
    asyncio.run(database.init_db())

    async def check():
        async with database.async_session() as db:
            versions = (await db.scalars(select(ItineraryTemplateVersion).order_by(ItineraryTemplateVersion.version))).all()
            assert [row.version for row in versions] == [1, 2, 3]
            assert [row.snapshot["days"][1]["activities"][0]["name"] for row in versions] == ["公园", "博物馆", "博物馆"]
            assert (await db.get(Trip, "personal-trip")).itinerary == {"plan": "公园"}
            assert (await db.scalar(select(TripVersion))).itinerary == {"plan": "公园"}

    asyncio.run(check())


def test_concurrent_edits_and_duplicate_publication(api):
    row = create(api, sample())

    def race(method, endpoint, data):
        barrier = Barrier(2)

        def request(account):
            client = TestClient(app)
            try:
                barrier.wait(timeout=5)
                return client.request(
                    method, f"{ADMIN}/{row['id']}/{endpoint}", headers=auth(account), json=data(account),
                ).status_code
            finally:
                client.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return sorted(pool.map(request, ["operator-one", "operator-two"]))

    assert race("PUT", "draft", lambda account: {
        "expected_revision": row["revision"], "draft": sample(account),
    }) == [200, 409]
    saved = api.get(f"{ADMIN}/{row['id']}").json()
    assert saved["revision"] == 2
    assert race("POST", "publish", lambda _: {"expected_revision": saved["revision"]}) == [200, 409]
    assert action(api, saved).status_code == 409
    assert reader(api, row).json()["version"] == 1
    assert action(api, saved, "unpublish").status_code == 409


def test_mid_publish_failure_rolls_back_pointer_and_snapshot(api):
    before = action(api, create(api, sample())).json()
    saved = save(api, before, sample("未发布的新标题"))

    def fail_after_insert(*args):
        raise RuntimeError("simulated failure while publishing")

    event.listen(ItineraryTemplateVersion, "after_insert", fail_after_insert)
    try:
        assert action(api, saved).status_code == 500
    finally:
        event.remove(ItineraryTemplateVersion, "after_insert", fail_after_insert)

    assert reader(api, before).json()["version"] == 1
    current = api.get(f"{ADMIN}/{before['id']}").json()
    assert (current["revision"], current["published_version"]) == (saved["revision"], 1)

    async def check():
        async with database.async_session() as db:
            assert list(await db.scalars(select(ItineraryTemplateVersion.version))) == [1]

    asyncio.run(check())
    assert action(api, saved).json()["published_version"] == 2


def test_template_auth_and_validation_boundaries(api):
    row = create(api, {"title": "测试草稿"})
    anonymous = {"Authorization": ""}
    assert api.get(READER, headers=anonymous).status_code == 401
    assert api.get(f"{READER}/{row['id']}", headers=anonymous).status_code == 401
    assert api.get(ADMIN, headers=auth("guest")).status_code == 403
    for method, url, payload in (
        ("POST", ADMIN, sample()),
        ("PUT", f"{ADMIN}/{row['id']}/draft", {"expected_revision": 1, "draft": sample()}),
        ("POST", f"{ADMIN}/{row['id']}/publish", {"expected_revision": 1}),
        ("POST", f"{ADMIN}/{row['id']}/unpublish", {"expected_revision": 1}),
    ):
        assert api.request(method, url, headers=auth("guest"), json=payload).status_code == 403
        assert api.request(method, url, headers=anonymous, json=payload).status_code == 401
    assert api.post(ADMIN, json={"title": "   "}).status_code == 422
    assert api.post(ADMIN, json={"title": "标题", "days": [{}] * 31}).status_code == 422
    assert api.post(ADMIN, json={"title": "标题", "revision": 9}).status_code == 422
    bad = api.post(ADMIN, json={"title": "标题", "days": [{"activities": [{"product_id": "does-not-exist"}]}]})
    assert bad.status_code == 422
    assert bad.json()["detail"]["errors"][0]["path"] == ["days", 0, "activities", 0, "product_id"]


def test_existing_database_adds_template_tables_and_keeps_resources(isolated_db):
    async def check():
        async with isolated_db.begin() as conn:
            tables = [table for table in database.Base.metadata.sorted_tables if table not in {
                ItineraryTemplate.__table__, ItineraryTemplateVersion.__table__,
            }]
            await conn.run_sync(lambda sync: database.Base.metadata.create_all(sync, tables=tables))
            await conn.execute(Supplier.__table__.insert().values(id="old-supplier", name="已有供应商", settlement_name="原结算主体"))
            await conn.execute(Product.__table__.insert().values(
                id="old-product", supplier_id="old-supplier", name="原有房型", type="hotel_room", city="成都",
                attributes={"room_name": "原有房型", "occupancy": 2, "breakfast": "无早餐"},
            ))
            await conn.execute(PriceOffer.__table__.insert().values(
                product_id="old-product", service_date=date(2026, 12, 2), status="available",
                cost_fen=10000, sale_fen=13000,
            ))
        await database.init_db()
        await database.init_db()
        async with isolated_db.begin() as conn:
            names = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
            assert {"itinerary_templates", "itinerary_template_versions", "price_offers", "products"} <= names
            assert await conn.scalar(select(Product.name)) == "原有房型"
            assert await conn.scalar(select(Supplier.name)) == "已有供应商"
            assert (await conn.execute(select(PriceOffer.cost_fen, PriceOffer.sale_fen))).one() == (10000, 13000)

    asyncio.run(check())
