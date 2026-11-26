import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from secrets import token_hex
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api import deps
from app.config import settings
from app.db import database
from app.db.models import Trip, TripVersion, User, UserProfile
from app.db.resource_models import PriceOffer
from app.main import app
from app.services import admin_pois, amap
from app.services.auth_service import create_access_token
from app.services.chroma_store import ChromaStore

ADMIN = "/api/v1/admin"
FIRST = "2026-12-02"
SECOND = "2026-12-03"
THIRD = "2026-12-04"
HOTEL = {"source": "amap", "id": "hotel-a", "name": "验收酒店", "city": "成都", "type": "hotel"}
TICKET = {"source": "chroma", "id": "scenic-a", "name": "验收景区", "city": "成都", "type": "attraction"}
ATTRIBUTES = {
    "hotel_room": {"room_name": "标准间", "occupancy": 2, "breakfast": "含双早"},
    "attraction_ticket": {"ticket_name": "成人票", "audience": "成人"},
    "vehicle": {"vehicle_name": "商务车", "passenger_capacity": 6},
}


def bearer(account="ops-one"):
    return {"Authorization": f"Bearer {create_access_token(account)}"}


@pytest.fixture
def resource_db(tmp_path, monkeypatch):
    engine = database.create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'resources.db'}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", sessions)
    monkeypatch.setattr(deps, "async_session", sessions)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
    yield engine
    asyncio.run(engine.dispose())


@pytest.fixture
def api(resource_db):
    async def initialize():
        await database.init_db()
        async with database.async_session.begin() as db:
            db.add_all([
                User(id=account, username=account, email=f"{account}@example.com", password_hash="unused", role=role)
                for account, role in (("ops-one", "operator"), ("ops-two", "operator"), ("guest", "tourist"))
            ])

    asyncio.run(initialize())
    client = TestClient(app)
    client.headers.update(bearer())
    try:
        yield client
    finally:
        client.close()


def supplier(client, name="验收供应商", **fields):
    response = client.post(f"{ADMIN}/suppliers", json={"name": name, "settlement_name": name, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def product_data(supplier_id, kind="hotel_room", **fields):
    return {
        "name": "验收商品", "type": kind, "city": "成都", "supplier_id": supplier_id,
        "attributes": ATTRIBUTES[kind], **fields,
    }


def product(client, supplier_id, kind="hotel_room", **fields):
    response = client.post(f"{ADMIN}/products", json=product_data(supplier_id, kind, **fields))
    assert response.status_code == 201, response.text
    return response.json()


def quote(service_date=FIRST, cost=30000, sale=36000, status="available", total=3):
    payload = {"service_date": service_date, "cost_fen": cost, "sale_fen": sale, "status": status}
    if total is not None:
        payload["total_quantity"] = total
    return payload


def product_url(product_id):
    return f"{ADMIN}/products/{product_id}"


def test_two_operators_share_resources_and_can_filter_and_edit(api):
    one = supplier(api, "成都供应商", contact_name="运营同事", contact_info="工作电话")
    two = supplier(api, "西安供应商", status="inactive")
    assert one["status"] == "active"
    assert one["contract_attachment_ref"] is None and one["settlement_workflow_ref"] is None
    two_url = f"{ADMIN}/suppliers/{two['id']}"
    second_account = bearer("ops-two")
    assert api.get(two_url, headers=second_account).json()["name"] == "西安供应商"
    assert api.patch(two_url, headers=second_account, json={"notes": "资料已复核"}).json()["notes"] == "资料已复核"
    listed = api.get(f"{ADMIN}/suppliers", params={"status": "inactive", "name": "西安"}).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == two["id"]
    listed = api.get(f"{ADMIN}/suppliers", params={"page": 2, "page_size": 1}).json()
    assert listed["total"] == 2 and len(listed["items"]) == 1
    assert api.patch(two_url, json={"contract_attachment_ref": "reserved"}).status_code == 422
    assert api.delete(two_url, headers=second_account).status_code == 204
    assert api.get(two_url).status_code == 404


def test_product_types_bindings_filters_and_delete_rules(api):
    seller = supplier(api)["id"]
    other = supplier(api, "第二家供应商")["id"]
    draft = product(api, seller)
    draft_url = product_url(draft["id"])
    assert draft["status"] == "off_shelf" and draft["offer_count"] == 0
    assert api.patch(draft_url, json={"status": "on_shelf"}).status_code == 409
    assert api.patch(draft_url, json={"poi": TICKET}).status_code == 422
    assert api.patch(draft_url, json={"poi": HOTEL, "status": "on_shelf"}).json()["price_unit"] == "间夜"
    room = product(api, other, name="验收双床房", poi=HOTEL, status="on_shelf")
    assert room["poi"] == HOTEL and room["supplier_id"] != draft["supplier_id"]
    same_supplier_room = product(api, seller, name="验收大床房", poi=HOTEL)
    assert same_supplier_room["poi"] == HOTEL

    ticket = product(api, seller, "attraction_ticket", name="票种")
    ticket_url = product_url(ticket["id"])
    assert api.patch(ticket_url, json={"status": "on_shelf"}).status_code == 409
    assert api.patch(ticket_url, json={"poi": TICKET, "status": "on_shelf"}).json()["price_unit"] == "张"
    vehicle = product(api, seller, "vehicle", name="车型", status="on_shelf")
    assert vehicle["poi"] is None and vehicle["price_unit"] == "车天"
    assert api.patch(product_url(vehicle["id"]), json={"attributes": {"vehicle_name": "七座车", "passenger_capacity": 7}}).json()[
        "attributes"
    ]["passenger_capacity"] == 7
    for kind, attributes in (("hotel_room", ATTRIBUTES["vehicle"]), ("vehicle", {"vehicle_name": "车", "passenger_capacity": 1.5})):
        assert api.post(f"{ADMIN}/products", json=product_data(seller, kind, attributes=attributes)).status_code == 422

    listed = api.get(f"{ADMIN}/products", params={
        "name": "验收", "supplier_id": seller, "type": "hotel_room", "status": "on_shelf",
    }).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == draft["id"]
    conflict = api.delete(f"{ADMIN}/suppliers/{seller}")
    assert conflict.status_code == 409 and "关联商品" in conflict.json()["detail"]
    assert api.delete(product_url(vehicle["id"])).status_code == 204
    assert api.get(product_url(vehicle["id"])).status_code == 404


def test_poi_lookup_preserves_source_filters_missing_ids_and_retains_existing(api, monkeypatch):
    def find_local(city, keyword, kind):
        assert (city, keyword, kind) == ("成都", "验收", "hotel")
        return [{"id": "hotel-a", "name": "验收种子酒店", "city": "成都市"}, {"name": "无 ID"}]

    async def find_amap(keyword, city, **options):
        assert (keyword, city) == ("验收", "成都")
        assert options == {"poi_type": "hotel", "city_only": True}
        return amap.PoiSearchResult(items=[HOTEL, {"id": "", "name": "无地图 ID"}])

    monkeypatch.setattr(admin_pois, "_lookup_seed", find_local)
    monkeypatch.setattr(amap, "search_poi", find_amap)
    params = {"city": " 成都 ", "keyword": " 验收 ", "type": "hotel"}
    items = api.get(f"{ADMIN}/pois", params=params).json()["items"]
    assert [(item["source"], item["id"]) for item in items] == [("chroma", "hotel-a"), ("amap", "hotel-a")]
    assert items[0]["city"] == "成都市"

    row = product(api, supplier(api)["id"], poi=items[1])

    async def provider_down(*args, **kwargs):
        return amap.PoiSearchResult(reason="api_error")

    monkeypatch.setattr(amap, "search_poi", provider_down)
    assert api.get(f"{ADMIN}/pois", params=params).json()["warning"]
    monkeypatch.setattr(admin_pois, "_lookup_seed", lambda *args: [])
    assert api.get(f"{ADMIN}/pois", params=params).status_code == 503
    assert api.get(product_url(row["id"])).json()["poi"] == items[1]


def test_local_poi_lookup_reuses_seed_ids_and_matches_city_and_name(tmp_path):
    store = ChromaStore(str(tmp_path / "poi-seeds"))
    store._hotels.add(
        ids=["chengdu-hotel", "chongqing-hotel", "different-hotel"],
        embeddings=[[1.0, 0.0]] * 3,
        metadatas=[
            {"city": "成都市", "name": "春熙路酒店"},
            {"city": "重庆", "name": "春熙路酒店"},
            {"city": "成都", "name": "天府酒店"},
        ],
    )

    assert store.find_poi_names("成都", "春熙路", "hotel") == [
        {"id": "chengdu-hotel", "name": "春熙路酒店", "city": "成都市"},
    ]


def test_quotes_units_count_zero_and_stay_availability(api):
    row = product(api, supplier(api)["id"], poi=HOTEL, status="on_shelf")
    url = product_url(row["id"])
    offers = f"{url}/offers"
    stay = {"check_in": FIRST, "check_out": THIRD}
    assert api.post(offers, json=quote()).status_code == 201
    before_second = api.get(offers, params=stay).json()
    assert not before_second["stay"]["can_sell"] and before_second["stay"]["sale_fen"] is None
    assert before_second["items"][1]["reasons"] == ["unquoted"]
    assert api.post(offers, json=quote(SECOND, sale=42000)).status_code == 201
    assert api.get(offers, params=stay).json()["stay"]["sale_fen"] == 78000
    assert api.get(offers, params=stay).json()["stay"]["can_sell"]
    assert api.get(url).json()["offer_count"] == 2
    assert api.patch(f"{offers}/{SECOND}", json={"sale_fen": 0, "status": "stopped"}).json()["quote"] == {
        "cost_fen": 30000, "sale_fen": 0, "status": "stopped", "below_cost": True,
        "total_quantity": 3, "reserved_quantity": 0, "confirmed_quantity": 0,
        "remaining": 3, "stock_verified": True,
    }
    stopped = api.get(offers, params={**stay, "status": "stopped"}).json()
    assert stopped["total"] == 1 and stopped["items"][0]["service_date"] == SECOND
    assert stopped["stay"]["unavailable"][0]["reasons"] == ["offer_stopped"]
    assert api.get(url).json()["offer_count"] == 2
    assert api.delete(url).status_code == 409
    assert api.delete(f"{offers}/{SECOND}").status_code == 204
    assert api.get(url).json()["offer_count"] == 1
    assert api.get(offers, params=stay).json()["items"][1]["quote"] is None
    assert api.post(offers, json=quote("2020-02-29", cost=0, sale=0)).status_code == 201
    assert api.get(f"{ADMIN}/products").json()["items"][0]["offer_count"] == 2
    asyncio.run(database.init_db())
    assert api.get(url).json()["offer_count"] == 2
    assert api.get(offers).json()["items"][0]["quote"]["sale_fen"] == 0


@pytest.mark.parametrize("overrides", [
    {"cost_fen": -1}, {"cost_fen": True}, {"sale_fen": 20.5}, {"sale_fen": 20.0},
    {"sale_fen": "20"}, {"sale_fen": None}, {"service_date": "2026-02-30"},
    {"service_date": "2026-12-02T00:00:00"}, {"service_date": "2026-2-1"},
    {"status": "other"},
])
def test_quote_rejects_invalid_amounts_dates_and_status(api, overrides):
    row = product(api, supplier(api)["id"], "vehicle")
    response = api.post(f"{product_url(row['id'])}/offers", json={**quote(), **overrides})
    assert response.status_code == 422, response.text


def test_all_sale_layers_change_independently_and_lock_quoted_identity(api):
    seller = supplier(api)["id"]
    other = supplier(api, "其它供应商")["id"]
    s_url = f"{ADMIN}/suppliers/{seller}"
    row = product(api, seller, poi=HOTEL, status="on_shelf")
    url = product_url(row["id"])
    offers = f"{url}/offers"
    assert api.post(offers, json=quote()).json()["can_sell"]
    assert api.post(offers, json=quote(SECOND, status="stopped")).status_code == 201
    assert api.patch(s_url, json={"status": "inactive"}).status_code == 200
    assert api.get(offers).json()["items"][0]["reasons"] == ["supplier_inactive"]
    assert api.patch(url, json={"name": "资料已纠正"}).status_code == 200
    assert api.patch(url, json={"supplier_id": other}).status_code == 409
    assert api.patch(url, json={"type": "vehicle", "attributes": ATTRIBUTES["vehicle"]}).status_code == 409
    other_hotel = {**HOTEL, "id": "hotel-b"}
    assert api.patch(url, json={"poi": other_hotel}).status_code == 409
    assert api.patch(url, json={"status": "off_shelf"}).status_code == 200
    assert api.get(offers).json()["items"][0]["reasons"] == ["supplier_inactive", "product_off_shelf"]
    assert api.patch(url, json={"status": "on_shelf"}).status_code == 409
    assert api.patch(url, json={"poi": other_hotel}).status_code == 200
    assert api.patch(s_url, json={"status": "active"}).status_code == 200
    assert api.patch(url, json={"status": "on_shelf"}).status_code == 200
    entries = api.get(offers).json()["items"]
    assert entries[0]["can_sell"] and entries[1]["reasons"] == ["offer_stopped"]
    assert api.patch(f"{offers}/{SECOND}", json={"status": "available"}).json()["can_sell"]


def test_batch_conflict_rolls_back_all_and_explicit_overwrite_preserves_count(api):
    row = product(api, supplier(api)["id"], "vehicle")
    url = product_url(row["id"])
    offers = f"{url}/offers"
    assert api.post(offers, json=quote(SECOND)).status_code == 201
    data = {"start_date": FIRST, "end_date": THIRD, "cost_fen": 500, "sale_fen": 0, "status": "stopped"}
    conflict = api.post(f"{offers}/batch", json=data)
    assert conflict.status_code == 409 and conflict.json()["detail"]["dates"] == [SECOND]
    assert api.get(url).json()["offer_count"] == 1
    assert api.get(offers).json()["items"][0]["quote"]["sale_fen"] == 36000
    assert api.post(f"{offers}/batch", json={**data, "overwrite": False}).status_code == 409
    assert api.post(f"{offers}/batch", json={**data, "overwrite": True}).json() == {"created": 2, "updated": 1}
    assert api.post(f"{offers}/batch", json={**data, "overwrite": True}).json() == {"created": 0, "updated": 3}
    assert api.get(url).json()["offer_count"] == 3
    assert api.get(offers, params={"start_date": THIRD, "end_date": FIRST}).status_code == 422
    assert api.patch(f"{offers}/{FIRST}", json={"service_date": SECOND}).status_code == 422
    other = product(api, row["supplier_id"], "vehicle")
    assert api.patch(f"{product_url(other['id'])}/offers/{FIRST}", json={"status": "available"}).status_code == 404


def test_resource_routes_require_operator_for_reads_and_writes(api):
    expired = jwt.encode(
        {"sub": "ops-one", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )
    anonymous = TestClient(app)
    try:
        for method, path, params in (
            ("GET", "/suppliers", {}), ("POST", "/suppliers", {"json": {"name": "甲", "settlement_name": "甲"}}),
            ("GET", "/products", {}), ("GET", "/pois", {"params": {"city": "成都", "keyword": "酒店", "type": "hotel"}}),
            ("GET", "/products/no-id/offers", {}), ("POST", "/products/no-id/offers", {"json": quote()}),
            ("DELETE", "/suppliers/no-id", {}),
        ):
            assert anonymous.request(method, ADMIN + path, **params).status_code == 401
            assert api.request(method, ADMIN + path, headers=bearer("guest"), **params).status_code == 403
            assert api.request(method, ADMIN + path, headers={"Authorization": f"Bearer {expired}"}, **params).status_code == 401
    finally:
        anonymous.close()


def concurrent_requests(*operations):
    start = Barrier(len(operations))

    def send(operation):
        method, path, body = operation
        client = TestClient(app)
        try:
            start.wait(timeout=5)
            return client.request(method, path, json=body, headers=bearer()).status_code
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        return sorted(pool.map(send, operations))


def test_concurrent_quotes_and_delete_create_keep_integrity(api):
    seller = supplier(api)["id"]
    row = product(api, seller, "vehicle")
    offers = f"{product_url(row['id'])}/offers"
    assert concurrent_requests(("POST", offers, quote()), ("POST", offers, quote())) == [201, 409]
    assert api.get(offers).json()["total"] == 1

    standalone = supplier(api, "待验证供应商")["id"]
    result = concurrent_requests(
        ("DELETE", f"{ADMIN}/suppliers/{standalone}", None),
        ("POST", f"{ADMIN}/products", product_data(standalone, "vehicle")),
    )
    assert result in ([201, 409], [204, 404])
    if result == [204, 404]:
        assert api.get(f"{ADMIN}/products", params={"supplier_id": standalone}).json()["total"] == 0

    empty = product(api, seller, "vehicle")["id"]
    url = product_url(empty)
    assert concurrent_requests(("DELETE", url, None), ("POST", f"{url}/offers", quote())) in ([201, 409], [204, 404])


def test_startup_upgrades_existing_database_without_changing_accounts_and_routes(resource_db):
    async def check():
        async with resource_db.begin() as conn:
            tables = [User.__table__, UserProfile.__table__, Trip.__table__, TripVersion.__table__]
            await conn.run_sync(lambda sync: database.Base.metadata.create_all(sync, tables=tables))
            await conn.execute(User.__table__.insert().values(
                id="old-user", username="operator", email="op@example.com", role="operator", password_hash="unchanged",
            ))
            await conn.execute(Trip.__table__.insert().values(
                id="old-trip", user_id="old-user", thread_id="old-thread", budget_total=365.98,
                itinerary={"total_budget_estimate_cny": 365.98},
            ))
        await database.init_db()
        await database.init_db()
        async with resource_db.begin() as conn:
            names = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
            assert {"suppliers", "products", "price_offers"} <= set(names)
            assert (await conn.execute(text("SELECT role, password_hash FROM users"))).one() == ("operator", "unchanged")
            assert (await conn.execute(text("SELECT user_id, budget_total FROM trips"))).one() == ("old-user", 365.98)
            assert await conn.scalar(text("PRAGMA foreign_keys")) == 1
            assert not (await conn.execute(text("SELECT * FROM price_offers"))).all()
        with pytest.raises(IntegrityError):
            async with resource_db.begin() as conn:
                await conn.execute(PriceOffer.__table__.insert().values(
                    product_id="missing", service_date=date.fromisoformat(FIRST),
                    cost_fen=0, sale_fen=0, status="available",
                ))

    asyncio.run(check())


def test_startup_stops_on_unmapped_legacy_price_table(resource_db):
    async def check():
        async with resource_db.begin() as conn:
            await conn.execute(text("CREATE TABLE price_offers (name TEXT, amount NUMERIC)"))
            await conn.execute(text("INSERT INTO price_offers VALUES ('旧价格', 23.5)"))
        with pytest.raises(RuntimeError, match="旧 price_offers"):
            await database.init_db()
        async with resource_db.connect() as conn:
            assert (await conn.execute(text("SELECT * FROM price_offers"))).one() == ("旧价格", 23.5)

    asyncio.run(check())
