"""Beijing fleet quotes, shared capacity and the order lifecycle on an isolated database."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import database
from app.db.content_models import PlaceContent, PlaceContentProduct
from app.db.fleet_models import FleetAllocation
from app.db.models import Trip
from app.db.resource_models import Driver, PriceOffer, Product, Supplier
from app.services import fleet_capacity, orders
from app.services.vehicle_routes import build_vehicle_offers, explicit_arrival
from scripts.seed_beijing_fleet import SUPPLIER_ID, seed, seed_id
from test_orders import ADMIN, API, DAY, GUEST, OPERATOR, OTHER, api, auth, body, seed_room, seed_users, sessions

FLEET = "/api/v1/admin/fleet"
CHECKOUT = "/api/v1/checkout"


def at(hour, minute=0, day=DAY):
    return datetime.combine(day, time(hour, minute), tzinfo=orders.BEIJING)


def spot(name, lat, lng):
    return {"name": name, "city": "北京", "location": {"lat": lat, "lng": lng}}


HOTEL = spot("东城测试酒店", 39.91, 116.41)
SIGHTS = [spot("故宫", 39.916, 116.397), spot("颐和园", 39.999, 116.275)]
ARRIVAL = {"mode": "flight", "pickup": "北京首都机场 T3", "start_time": "08:00"}


async def add_trip(sessions, user=GUEST, *, dated=True):
    key = str(uuid4())
    async with sessions.begin() as db:
        db.add(Trip(id=key, thread_id=key, user_id=user, status="completed", destination="北京", duration_days=1,
                    travel_request={"travel_time": DAY.isoformat() if dated else "",
                                    "flight_arrival": ARRIVAL, "travelers": {"adults": 2}},
                    itinerary={"day_plans": [{"day": 1, "hotel": HOTEL, "attractions": SIGHTS}]}))
    return key


def terms(purpose="charter", start="10:00", **changes):
    return {"service_key": f"vehicle:1:{purpose}", "start_time": start,
            "pickup": "" if purpose == "charter" else ARRIVAL["pickup"],
            "dropoff": "" if purpose == "charter" else HOTEL["name"],
            "passengers": 2, "luggage": 0, **changes}


def quote(api, trip, selection, *, user=GUEST, day=DAY):
    response = api.post(f"{CHECKOUT}/vehicle-quote", headers=auth(user), json={
        "trip_id": trip, "departure_date": day.isoformat() if day else None, **selection,
    })
    assert response.status_code == 200, response.text
    return response.json()


def selected(result, selection, model=None):
    choice = next(option for option in result["options"] if (
        option["model_code"] == model if model else option["product_id"] == result["recommended_product_id"]
    ))
    assert choice["sellable"], choice
    day = result["service_date"]
    return {"kind": "vehicle", "product_id": choice["product_id"], "quantity": 1, "service_date": day,
            "quotes": [{"service_date": day, "token": choice["token"]}], "vehicle": selection}


def submit(api, trip, items, *, user=GUEST, key=None, day=DAY):
    return api.post(API, headers={**auth(user), "Idempotency-Key": key or str(uuid4())}, json={
        "trip_id": trip, "departure_date": day.isoformat(), "contact_name": "演示游客",
        "contact_phone": "13800000000", "travelers": [{"name": "演示游客"}], "selected": items,
    })


@pytest.fixture
def clock(monkeypatch):
    timepoint = [at(0, day=DAY - timedelta(days=1)).astimezone(timezone.utc)]
    monkeypatch.setattr(orders, "now_utc", lambda: timepoint[0])
    return timepoint


def test_seed_is_idempotent_and_preserves_operator_updates(sessions):
    async def run():
        totals = await seed(sessions, DAY)
        assert totals == dict(suppliers=1, models=3, vehicles=6, drivers=4, products=6, offers=540)
        product = seed_id("product/sedan/airport_transfer")
        async with sessions.begin() as db:
            row = await db.get(PriceOffer, (product, DAY))
            assert (row.sale_fen, row.cost_fen, row.total_quantity, row.trip_priced) == (30000, 21000, 3, True)
            row.sale_fen, row.status, row.reserved_quantity = 31000, "stopped", 1
            (await db.get(Driver, seed_id("driver/1"))).status = "inactive"
        assert not any((await seed(sessions, DAY)).values())
        assert (await seed(sessions, DAY + timedelta(days=1)))["offers"] == 6
        async with sessions() as db:
            row = await db.get(PriceOffer, (product, DAY))
            assert (row.sale_fen, row.status, row.reserved_quantity) == (31000, "stopped", 1)
            assert (await db.get(Driver, seed_id("driver/1"))).status == "inactive"
            assert await db.scalar(select(func.count()).select_from(PriceOffer)) == 546
    asyncio.run(run())


def test_fleet_migration_keeps_legacy_prices_and_marks_them_unverified(tmp_path, monkeypatch):
    async def run():
        engine = database.create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy-fleet.db'}")
        monkeypatch.setattr(database, "engine", engine)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await database.init_db()
            await seed(factory, DAY)
            async with engine.begin() as conn:
                await conn.execute(text("ALTER TABLE price_offers DROP COLUMN trip_priced"))
                await conn.execute(text("ALTER TABLE vehicles DROP COLUMN model_code"))
                await conn.execute(text("ALTER TABLE drivers DROP COLUMN model_codes"))
                await conn.execute(text("ALTER TABLE suppliers DROP COLUMN fleet_city"))
            await database.init_db()
            await database.init_db()
            async with factory() as db:
                offer = await db.get(PriceOffer, (seed_id("product/sedan/charter"), DAY))
                assert (offer.sale_fen, offer.status, offer.total_quantity, offer.trip_priced) == (60000, "available", 3, False)
                assert (await db.get(Supplier, SUPPLIER_ID)).fleet_city == ""
                assert (await db.get(Driver, seed_id("driver/1"))).model_codes is None
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_roadbook_uses_real_stops_and_explicit_flight_only():
    new_hotel = spot("海淀测试酒店", 39.98, 116.32)
    plans = [{"day": 1, "hotel": HOTEL, "attractions": SIGHTS},
             {"day": 2, "hotel": new_hotel, "attractions": [{"name": "未提供坐标的景点"}]}]
    pickup, charter, tomorrow = build_vehicle_offers(plans, {"flight_arrival": ARRIVAL}, "北京市", DAY)
    assert pickup.recommended and pickup.pickup == "北京首都机场 T3"
    assert charter.recommended and [(leg.origin, leg.destination) for leg in charter.legs] == [
        (HOTEL["name"], "故宫"), ("故宫", "颐和园"), ("颐和园", HOTEL["name"]),
    ]
    assert (tomorrow.pickup, tomorrow.dropoff) == (HOTEL["name"], new_hotel["name"])
    assert all(leg.distance_km is None for leg in tomorrow.legs)
    assert explicit_arrival("我从天津出发") is None
    assert explicit_arrival("坐高铁去北京") == {"mode": "other"}
    assert explicit_arrival("坐飞机，08:00 到北京首都机场 T3") == ARRIVAL
    pickup, short = build_vehicle_offers([{"day": 1, "hotel": HOTEL, "attractions": SIGHTS[:1]}], {}, "北京")
    assert not pickup.recommended and not pickup.pickup and not short.recommended
    assert short.legs and build_vehicle_offers(plans, {}, "天津") == []


def test_quote_checks_date_airport_capacity_changes_and_legacy_price(api, sessions, clock):
    async def start():
        await seed_users(sessions)
        await seed(sessions, DAY)
        return await add_trip(sessions, dated=False)
    trip = asyncio.run(start())
    path = f"{CHECKOUT}/options?trip_id={trip}"
    data = api.get(path, headers=auth(GUEST)).json()
    assert data["departure_date"] is None and data["date_selectable"]
    assert [offer["purpose"] for offer in data["vehicle_offers"]] == ["airport_transfer", "charter"]
    pickup = terms("airport_transfer", "08:00")
    assert quote(api, trip, pickup, day=None)["reason"] == "needs_date"
    assert quote(api, trip, {**pickup, "start_time": None})["reason"] == "needs_time"
    assert quote(api, trip, {**pickup, "pickup": "北京机场"})["reason"] == "invalid_airport"
    assert quote(api, trip, {**pickup, "dropoff": "河北省廊坊市"})["reason"] == "invalid_dropoff"
    assert quote(api, trip, {**pickup, "dropoff": "北京市东城区王府井大街 1 号"})["recommended_product_id"]
    assert {option["reason"] for option in quote(api, trip, {**pickup, "passengers": 21})["options"]} == {"passenger_limit"}
    assert quote(api, trip, {**pickup, "passengers": 6})["recommended_product_id"] == seed_id("product/business/airport_transfer")
    assert quote(api, trip, {**pickup, "luggage": 3})["recommended_product_id"] == seed_id("product/business/airport_transfer")
    result = quote(api, trip, {**pickup, "luggage": 2})
    choice = selected(result, {**pickup, "luggage": 2})
    assert result["recommended_product_id"] == seed_id("product/sedan/airport_transfer")
    assert "运营联系电话" not in str(result) and "000-00000001" not in str(result)
    changed = deepcopy(choice)
    changed["vehicle"]["start_time"] = "09:00"
    assert submit(api, trip, [changed]).json()["detail"]["items"][0]["reason"] == "price_or_terms_changed"
    assert api.get(path, headers=auth(OTHER)).status_code == 404
    assert api.get(f"{FLEET}/drivers", headers=auth(GUEST)).status_code == 403

    async def old_price():
        async with sessions.begin() as db:
            (await db.get(PriceOffer, (choice["product_id"], DAY))).trip_priced = False
    asyncio.run(old_price())
    result = quote(api, trip, pickup)
    assert next(option for option in result["options"] if option["model_code"] == "sedan")["reason"] == "unverified_trip_price"
    assert submit(api, trip, [choice]).status_code == 409


def test_vehicle_with_room_expiry_payment_review_and_cancellation(api, sessions, clock):
    async def start():
        await seed_users(sessions)
        await seed(sessions, DAY)
        room = await seed_room(sessions)
        request = body(room)
        async with sessions.begin() as db:
            trip = await db.get(Trip, request["trip_id"])
            plan = dict(trip.itinerary["day_plans"][0], attractions=SIGHTS)
            trip.itinerary = {"day_plans": [plan]}
            trip.travel_request = {**trip.travel_request, "flight_arrival": ARRIVAL}
            supplier = Supplier(name="门票验收供应商", settlement_name="门票验收供应商", kind="ticket")
            db.add(supplier)
            await db.flush()
            ticket = Product(supplier_id=supplier.id, name="故宫成人票", type="attraction_ticket", city="北京",
                             attributes={"ticket_name": "成人票", "audience": "成人"}, status="on_shelf")
            place = PlaceContent(kind="attraction", city="北京", name="故宫", status="published")
            db.add_all([ticket, place])
            await db.flush()
            db.add(PlaceContentProduct(content_id=place.id, product_id=ticket.id))
            db.add(PriceOffer(product_id=ticket.id, service_date=DAY, cost_fen=5000, sale_fen=6000,
                              status="available", total_quantity=10))
            plan = dict(plan, attractions=[{**SIGHTS[0], "content_id": place.id}, SIGHTS[1]])
            trip.itinerary = {"day_plans": [plan]}
        return room, request, ticket.id
    room, request, ticket = asyncio.run(start())
    trip = request["trip_id"]
    options = api.get(f"{CHECKOUT}/options", params={"trip_id": trip}, headers=auth(GUEST)).json()
    ticket_offer = next(item for item in options["items"] if item["product_id"] == ticket)
    room_and_ticket = [*request["selected"], {"kind": "ticket", "product_id": ticket, "service_date": DAY.isoformat(),
                      "quantity": 1, "quotes": [{"service_date": DAY.isoformat(), "token": ticket_offer["days"][0]["token"]}]}]
    pickup, charter = terms("airport_transfer", "08:00", dropoff="北京市东城区王府井 10 号"), terms()
    collection = [selected(quote(api, trip, option), option) for option in (pickup, charter)]
    assert sum(quote(api, trip, option)["options"][0]["price_fen"] for option in (pickup, charter)) == 90000
    changed = deepcopy(collection)
    changed[1]["quotes"][0]["token"] = "0" * 64
    assert submit(api, trip, room_and_ticket + changed).status_code == 409

    async def slot_states(states, room_quantities):
        async with sessions() as db:
            assert sorted(await db.scalars(select(FleetAllocation.state))) == sorted(states)
            offer = await db.get(PriceOffer, (room, DAY))
            assert (offer.reserved_quantity, offer.confirmed_quantity) == room_quantities
            admission = await db.get(PriceOffer, (ticket, DAY))
            assert (admission.reserved_quantity, admission.confirmed_quantity) == room_quantities

    asyncio.run(slot_states([], (0, 0)))
    first = submit(api, trip, room_and_ticket + collection, key="same")
    assert first.status_code == 201, first.text
    order = first.json()
    assert order["total_sale_fen"] == 146000
    slots = {row["attributes"]["fleet"]["purpose"]: row["attributes"]["fleet"] for row in order["items"]
             if row["product_type"] == "vehicle"}
    assert slots["airport_transfer"]["ends_at"] == slots["charter"]["starts_at"] == at(10).isoformat()
    assert slots["charter"]["price_unit"] == "趟" and slots["charter"]["legs"]
    assert submit(api, trip, room_and_ticket + collection, key="same").json()["id"] == order["id"]
    asyncio.run(slot_states(["reserved"] * 2, (1, 0)))
    clock[0] += timedelta(minutes=15)
    assert api.get(f"{API}/{order['id']}", headers=auth(GUEST)).json()["status"] == "cancelled"
    asyncio.run(slot_states(["released"] * 2, (0, 0)))
    next_order = submit(api, trip, room_and_ticket + collection)
    assert next_order.status_code == 201, next_order.text
    key = next_order.json()["id"]
    assert api.post(f"{API}/{key}/payments", json={"idempotency_key": "mock"}, headers=auth(GUEST)).status_code == 200
    clock[0] += timedelta(minutes=30)
    approved = api.post(f"{ADMIN}/{key}/approve", json={"note": "测试确认"}, headers=auth(OPERATOR))
    assert approved.status_code == 200 and approved.json()["status"] == "confirmed", approved.text
    asyncio.run(slot_states(["released"] * 2 + ["confirmed"] * 2, (0, 1)))
    request_cancel = api.post(f"{API}/{key}/cancel-request", json={"reason": "临时取消"}, headers=auth(GUEST))
    assert request_cancel.status_code == 200, request_cancel.text
    resolved = api.post(f"{ADMIN}/{key}/cancel-request", headers=auth(OPERATOR),
                        json={"approve": True, "usage": "unused", "note": "确认未使用"})
    assert resolved.status_code == 200 and resolved.json()["fund_status"] == "refunded", resolved.text
    asyncio.run(slot_states(["released"] * 4, (0, 0)))


def test_concurrent_cross_product_bookings_share_driver_and_block_roster_gap(api, sessions, clock):
    async def start():
        await seed_users(sessions)
        await seed(sessions, DAY)
        async with sessions.begin() as db:
            await db.execute(update(Driver).where(Driver.id != seed_id("driver/4")).values(status="inactive"))
        return await add_trip(sessions), await add_trip(sessions, OTHER)
    trip_a, trip_b = asyncio.run(start())
    charter, pickup = terms(start="23:00"), terms("airport_transfer", "23:30", passengers=6)
    a = selected(quote(api, trip_a, charter), charter, "sedan")
    b = selected(quote(api, trip_b, pickup, user=OTHER), pickup, "business")
    simultaneous = Barrier(2)

    def book(trip, choice, user):
        simultaneous.wait(timeout=10)
        return submit(api, trip, [choice], user=user)

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(book, trip_a, a, GUEST)
        two = pool.submit(book, trip_b, b, OTHER)
        replies = [one.result(timeout=15), two.result(timeout=15)]
    assert sorted(reply.status_code for reply in replies) == [201, 409], [reply.text for reply in replies]
    accepted = next(reply.json() for reply in replies if reply.status_code == 201)
    rejected = next(reply.json() for reply in replies if reply.status_code == 409)
    assert rejected["detail"]["items"][0]["reason"] == "timeslot_full"
    before = api.post(f"{FLEET}/drivers/{seed_id('driver/4')}/disable", headers=auth(OPERATOR))
    assert before.status_code == 409 and before.json()["detail"]["order_ids"] == [accepted["id"]]
    after_midnight = api.get(f"{FLEET}/capacity", headers=auth(OPERATOR), params={
        "supplier_id": SUPPLIER_ID, "model_code": "sedan",
        "starts_at": at(0, day=DAY + timedelta(days=1)).isoformat(),
        "ends_at": at(1, day=DAY + timedelta(days=1)).isoformat(),
    })
    assert after_midnight.status_code == 200 and after_midnight.json()["available"] == 0, after_midnight.text
    clock[0] += timedelta(minutes=16)
    assert api.post(f"{FLEET}/drivers/{seed_id('driver/4')}/disable", headers=auth(OPERATOR)).status_code == 204


def test_vehicle_count_and_distinct_driver_qualifications_on_interval_boundaries():
    vehicles = [fleet_capacity.Car("sedan-1", "sedan", 4, 2), fleet_capacity.Car("sedan-2", "sedan", 4, 2),
                fleet_capacity.Car("business", "business", 6, 4)]
    drivers = [fleet_capacity.QualifiedDriver("one", ("sedan",)), fleet_capacity.QualifiedDriver("two", ("sedan", "business")),
               fleet_capacity.QualifiedDriver("three", ("business",))]
    sedan = lambda begin, end: fleet_capacity.Demand("sedan", begin, end, 2, 1)
    first, later = sedan(at(8), at(10)), sedan(at(10), at(12))
    noon = sedan(at(8), at(12))
    assert fleet_capacity.fits([first, later, noon], vehicles, drivers)
    assert not fleet_capacity.fits([noon, noon, later], vehicles, drivers)
    business = fleet_capacity.Demand("business", at(10), at(12), 4, 3)
    assert not fleet_capacity.fits([later, business], vehicles, drivers[1:2])
    assert fleet_capacity.fits([first, business], vehicles, drivers[1:2])


def test_service_cannot_switch_vehicle_or_driver_mid_trip():
    demand = fleet_capacity.Demand
    long_trip = demand("sedan", at(8), at(12), 2, 1)
    early = demand("sedan", at(8), at(10), 4, 1)
    late = demand("sedan", at(10), at(12), 2, 3)
    cars = [fleet_capacity.Car("more-seats", "sedan", 4, 2), fleet_capacity.Car("more-luggage", "sedan", 2, 4)]
    drivers = [fleet_capacity.QualifiedDriver("one", ("sedan", "business")),
               fleet_capacity.QualifiedDriver("two", ("sedan", "bus"))]
    assert fleet_capacity.fits([long_trip, early], cars, drivers)
    assert fleet_capacity.fits([long_trip, late], cars, drivers)
    assert not fleet_capacity.fits([early, late, long_trip], cars, drivers, affected_after=2)
    other_cars = cars + [fleet_capacity.Car("business", "business", 6, 4), fleet_capacity.Car("bus", "bus", 20, 10)]
    early_business = demand("business", at(8), at(10), 4, 1)
    late_bus = demand("bus", at(10), at(12), 2, 3)
    assert not fleet_capacity.fits([early_business, late_bus, long_trip], other_cars, drivers, affected_after=2)


def test_two_charters_use_both_sedans_before_pickup_daily_quota_runs_out(api, sessions, clock):
    async def start():
        await seed_users(sessions)
        await seed(sessions, DAY)
        return await add_trip(sessions), await add_trip(sessions, OTHER)
    trips = asyncio.run(start())
    charter = terms()
    for trip, user in zip(trips, (GUEST, OTHER)):
        row = selected(quote(api, trip, charter, user=user), charter, "sedan")
        response = submit(api, trip, [row], user=user)
        assert response.status_code == 201, response.text
    pickup = terms("airport_transfer", "10:30")
    result = quote(api, trips[0], pickup)
    sedan = next(choice for choice in result["options"] if choice["model_code"] == "sedan")
    assert sedan["reason"] == "timeslot_full"
    assert result["recommended_product_id"] == seed_id("product/business/airport_transfer")
    available = quote(api, trips[0], {**pickup, "start_time": "08:00"})
    assert available["recommended_product_id"] == seed_id("product/sedan/airport_transfer")


def test_operator_updates_model_name_keeps_snapshot_and_blocks_new_sales_if_fleet_is_inactive(api, sessions, clock):
    async def start():
        await seed_users(sessions)
        await seed(sessions, DAY)
        return await add_trip(sessions)
    trip = asyncio.run(start())
    fields = terms()
    result = submit(api, trip, [selected(quote(api, trip, fields), fields)])
    assert result.status_code == 201, result.text
    model_path = f"{FLEET}/models/sedan?supplier_id={SUPPLIER_ID}"
    assert api.patch(model_path, json={"name": "演示轿车新名称"}, headers=auth(OPERATOR)).status_code == 200
    assert api.delete(model_path, headers=auth(OPERATOR)).status_code == 409
    assert quote(api, trip, fields)["options"][0]["model_name"] == "演示轿车新名称"
    assert api.patch(f"/api/v1/admin/suppliers/{SUPPLIER_ID}", headers=auth(OPERATOR),
                     json={"status": "inactive"}).status_code == 200
    assert quote(api, trip, fields)["reason"] == "no_supply"
    view = api.get(f"{API}/{result.json()['id']}", headers=auth(GUEST)).json()
    assert view["items"][0]["attributes"]["fleet"]["model_name"] == "5 座轿车"
