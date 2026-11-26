import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.db import database
from app.db.content_models import PlaceContent, PlaceContentProduct
from app.db.membership_models import PointAccount, PointTransaction
from app.db.models import Trip
from app.db.order_models import DemoPointEvent, Order, OrderDataMigration, OrderPayment, OrderRefund
from app.db.resource_models import OfferAllocation, PriceOffer, Product
from app.services import demo_points, orders
from app.services.sales_maintenance import maintenance_once
from app.services.member_points import record_payment, record_refund
from scripts.clean_mock_points import main as clean_points

from test_orders import ADMIN, API, DAY, GUEST, OPERATOR, OTHER, api, auth, body, seed_room, seed_users, sessions, stock_row, trip_for

OPTIONS = "/api/v1/checkout/options"


def ok(response, status=200):
    assert response.status_code == status, response.json().get("detail", "unexpected response") if not response.is_success else response.status_code
    return response.json()


def submit(api, payload, key, user=GUEST):
    return api.post(API, json=payload, headers={**auth(user), "Idempotency-Key": key})


def pay(api, order):
    return api.post(f'{API}/{order["id"]}/payments', json={"idempotency_key": "payment"}, headers=auth(GUEST))


def candidates(api, trip, day=None):
    params = {"trip_id": trip}
    if day is not None:
        params["departure_date"] = day.isoformat()
    return ok(api.get(OPTIONS, params=params, headers=auth(GUEST)))


def selected(item, quantity):
    return {key: item[key] for key in ("kind", "product_id", "check_in", "check_out", "service_date")
            if key != "service_date" or item["kind"] != "hotel"} | {
        "quantity": quantity,
        "quotes": [{key: day[key] for key in ("service_date", "token")} for day in item["days"]],
    }


def test_month_only_shift_dates_prices_and_independent_segments(api, sessions):
    async def prepare():
        await seed_users(sessions)
        room = await seed_room(sessions, total=3)
        trip_id = trip_for(room, GUEST)
        async with sessions.begin() as db:
            trip = await db.get(Trip, trip_id)
            trip.travel_request = {"travel_time": "十二月", "travelers": {"adults": 2}}
            plan = trip.itinerary["day_plans"]
            hotel = plan[0]["hotel"]
            room_row = await db.get(Product, room)
            room_place = await db.get(PlaceContent, hotel["content_id"])
            alternative = Product(supplier_id=room_row.supplier_id, type="hotel_room", city="北京",
                                  name="替代房型", attributes=room_row.attributes, status="on_shelf")
            ticket = Product(supplier_id=room_row.supplier_id, type="attraction_ticket", city="北京",
                             name="景区门票", attributes={"ticket_name": "通票"}, status="on_shelf")
            attraction = PlaceContent(kind="attraction", city="北京", name="测试景区", status="published")
            db.add_all([ticket, attraction, alternative])
            await db.flush()
            db.add_all([PlaceContentProduct(content_id=attraction.id, product_id=ticket.id),
                        PlaceContentProduct(content_id=room_place.id, product_id=alternative.id)])
            trip.duration_days = 5
            trip.itinerary = {"day_plans": [
                {**plan[0], "date": "2020-01-01"},
                {**plan[1], "attractions": [{"name": attraction.name, "content_id": attraction.id}]},
                {"day": 3}, {"day": 4, "hotel": hotel}, {"day": 5},
            ]}
            for offset, price in enumerate((30000, 50000, 30000, 50000, 50000, 50000)):
                day = DAY + timedelta(days=offset)
                offer = await db.get(PriceOffer, (room, day))
                if offer:
                    offer.sale_fen = price
                else:
                    db.add(PriceOffer(product_id=room, service_date=day, cost_fen=10000, sale_fen=price,
                                      total_quantity=3, status="available"))
                if offset in (1, 3):
                    db.add(PriceOffer(product_id=ticket.id, service_date=day, cost_fen=1000, sale_fen=1500,
                                      total_quantity=1 if offset == 1 else 0, status="available"))
            return room, trip_id, ticket.id, alternative.id

    room, trip_id, ticket, alternative = asyncio.run(prepare())
    undated = candidates(api, trip_id)
    assert undated["departure_date"] is None and undated["sellable_count"] == 0
    assert api.get(OPTIONS, params={"trip_id": trip_id}, headers=auth(OTHER)).status_code == 404
    assert api.get(OPTIONS, params={"trip_id": trip_id}, headers=auth(OPERATOR)).status_code == 403
    first = candidates(api, trip_id, DAY)
    stays = [item for item in first["items"] if item["product_id"] == room]
    assert len(stays) == 2 and stays[0]["key"] != stays[1]["key"]
    assert [day["price_fen"] for day in stays[0]["days"]] == [30000, 50000]
    assert [item["reason"] for item in first["items"] if item["product_id"] == alternative] == ["unquoted", "unquoted"]
    first_ticket = next(item for item in first["items"] if item["product_id"] == ticket)
    bad_qty = body(room) | {"departure_date": DAY.isoformat(), "selected": [selected(first_ticket, 2)]}
    assert submit(api, bad_qty, "ticket-oversold").json()["detail"]["items"][0]["reason"] == "sold_out"
    later = DAY + timedelta(days=2)
    second = candidates(api, trip_id, later)
    assert next(item for item in second["items"] if item["product_id"] == ticket)["status"] == "sold_out"
    stay = next(item for item in second["items"] if item["product_id"] == room)
    assert stay["check_out"] == (later + timedelta(days=2)).isoformat()
    payload = body(room) | {"departure_date": later.isoformat(), "selected": [selected(stay, 2)]}
    order = ok(submit(api, payload, "one-purchase"), 201)
    assert order["total_sale_fen"] == 160000
    assert order["departure_date"] == later.isoformat()
    assert order["items"][0]["attributes"]["stay"] == {"check_in": later.isoformat(), "check_out": stay["check_out"]}
    assert "total_cost_fen" not in order and "unit_cost_fen" not in order["items"][0]
    assert "reason" not in order["events"][0]
    for attempt in range(2):
        assert ok(submit(api, payload, "one-purchase"), 201)["id"] == order["id"]
    assert submit(api, {**payload, "contact_name": "另一位"}, "one-purchase").status_code == 409
    assert submit(api, payload, "foreign", OTHER).status_code == 404
    assert submit(api, payload, "forbidden", OPERATOR).status_code == 403

    async def verify():
        async with sessions() as db:
            route = await db.get(Trip, trip_id)
            assert route.travel_request["travel_time"] == "十二月"
            assert await db.scalar(select(func.count()).select_from(Order)) == 1
    asyncio.run(verify())


def test_changed_quote_and_document_validations(api, sessions, monkeypatch):
    asyncio.run(seed_users(sessions))
    room = asyncio.run(seed_room(sessions))
    payload = body(room, nights=2)

    async def adjust_price():
        async with sessions.begin() as db:
            offer = await db.get(PriceOffer, (room, DAY + timedelta(days=1)))
            offer.sale_fen -= 1000

    asyncio.run(adjust_price())
    changed = submit(api, payload, "before-price")
    assert changed.status_code == 409
    assert changed.json()["detail"]["items"] == [{"product_id": room, "service_date":
        (DAY + timedelta(days=1)).isoformat(), "reason": "price_changed"}]
    opts = candidates(api, payload["trip_id"])
    payload["selected"] = [selected(opts["items"][0], 1)]
    monkeypatch.setattr(settings, "pii_encryption_key", SecretStr(""))
    assert submit(api, payload, "no-key").status_code == 503
    payload["travelers"][0]["document_number"] = ""
    assert submit(api, payload, "no-key", user=OTHER).status_code == 404
    wrong = {"kind": "ticket", "product_id": room, "quantity": 1, "service_date": DAY.isoformat(),
             "quotes": [{"service_date": DAY.isoformat(), "token": "0" * 64}]}
    assert submit(api, {**payload, "selected": [wrong]}, "wrong-type").status_code == 422
    assert submit(api, {**payload, "selected": [{**wrong, "service_date": None}]}, "no-date").status_code == 422
    assert submit(api, payload, "no-key").status_code == 201


def test_paid_hold_review_and_missing_second_night(api, sessions, monkeypatch):
    asyncio.run(seed_users(sessions))
    room = asyncio.run(seed_room(sessions, total=1))
    clock = datetime.combine(DAY - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    monkeypatch.setattr(orders, "now_utc", lambda: clock)
    order = ok(submit(api, body(room, nights=2), "last-room"), 201)
    clock += timedelta(minutes=14, seconds=59)
    ok(pay(api, order))
    clock += timedelta(minutes=1, seconds=1)
    assert submit(api, body(room, user=OTHER), "other", OTHER).status_code == 409
    assert asyncio.run(stock_row(sessions, room)).reserved_quantity == 1
    clock += timedelta(minutes=30)
    summary = ok(api.get(ADMIN, params={"status": "paid_pending_review"}, headers=auth(OPERATOR)))["items"][0]
    assert summary["review_overdue"] and summary["waiting_minutes"] == 31

    async def remove_night():
        async with sessions.begin() as db:
            await db.execute(delete(OfferAllocation).where(OfferAllocation.order_id == order["id"],
                OfferAllocation.service_date == DAY + timedelta(days=1)))

    asyncio.run(remove_night())
    approval = api.post(f'{ADMIN}/{order["id"]}/approve', json={}, headers=auth(OPERATOR))
    assert approval.status_code == 409
    assert ok(api.get(f"{ADMIN}/inventory-audit", headers=auth(OPERATOR)))["total"] == 1
    first = asyncio.run(stock_row(sessions, room))
    assert (first.reserved_quantity, first.confirmed_quantity) == (1, 0)
    intact = asyncio.run(seed_room(sessions, total=1))
    another = ok(submit(api, body(intact), "intact"), 201)
    ok(pay(api, another))
    clock += timedelta(minutes=31)
    ok(api.post(f'{ADMIN}/{another["id"]}/approve', json={}, headers=auth(OPERATOR)))
    final = asyncio.run(stock_row(sessions, intact))
    assert (final.reserved_quantity, final.confirmed_quantity) == (0, 1)


def test_exact_expiry_reclaims_both_nights_with_payment_race(api, sessions, monkeypatch):
    asyncio.run(seed_users(sessions))
    room = asyncio.run(seed_room(sessions, total=1))
    clock = datetime.combine(DAY - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    monkeypatch.setattr(orders, "now_utc", lambda: clock)
    order = ok(submit(api, body(room, nights=2), "expires"), 201)
    ref = f"/api/v1/admin/products/{room}/offers/{DAY.isoformat()}"
    assert api.delete(ref, headers=auth(OPERATOR)).status_code == 409
    clock += timedelta(minutes=15)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(pay, api, order)
        read = pool.submit(api.get, ref.rsplit("/", 1)[0], headers=auth(OPERATOR))
        assert future.result().status_code == 409
        assert read.result().status_code == 200
    for day in (DAY, DAY + timedelta(days=1)):
        assert asyncio.run(stock_row(sessions, room, day)).reserved_quantity == 0
    assert ok(api.get(f'{API}/{order["id"]}', headers=auth(GUEST)))["status"] == "cancelled"
    assert ok(api.post(f"{ADMIN}/sweep", headers=auth(OPERATOR)))["expired"] == 0
    assert api.delete(ref, headers=auth(OPERATOR)).status_code == 409


def test_cancel_usage_and_isolated_demo_ledger(api, sessions):
    asyncio.run(seed_users(sessions))
    room = asyncio.run(seed_room(sessions))
    order = ok(submit(api, body(room), "cancel-used"), 201)
    ok(pay(api, order))
    order_id = order["id"]
    review = f"{ADMIN}/{order_id}"
    ok(api.post(f"{review}/approve", json={}, headers=auth(OPERATOR)))
    for _ in range(2):
        assert ok(api.post(f"{API}/{order_id}/cancel-request", json={}, headers=auth(GUEST)))["status"] == "cancel_requested"
    assert api.post(f"{API}/{order_id}/cancel", json={}, headers=auth(GUEST)).status_code == 409
    for usage in ("unknown", "used"):
        resolved = ok(api.post(f"{review}/cancel-request", json={"approve": False, "usage": usage,
            "note": "供应商核对了使用记录。"}, headers=auth(OPERATOR)))
        assert resolved["fund_status"] == "paid"
    guest = ok(api.get(f"{API}/{order_id}", headers=auth(GUEST)))
    assert guest["after_sales_ticket_id"]
    assert asyncio.run(stock_row(sessions, room)).confirmed_quantity == 1

    async def ledger():
        async with sessions() as db:
            assert (await demo_points.overview(db, GUEST))["balance"] == 5000
            assert await db.get(PointAccount, GUEST) is None
    asyncio.run(ledger())


def test_migrate_old_mock_points_and_preview_only_cleanup(api, sessions):
    async def migrate():
        await seed_users(sessions)
        start = datetime.now(timezone.utc) - timedelta(days=5)
        await record_payment(sessions, order_id="actual-one", member_id=GUEST, amount_fen=850,
                             paid_at=start, event_id="actual-event")
        async with sessions.begin() as db:
            for key, paid_at in (("mock-current", start), ("mock-expired", start - timedelta(days=500))):
                db.add(Order(id=key, order_no=key, user_id=GUEST, contact_name="演示", contact_phone="000",
                             status="cancelled", fund_status="refunded", total_sale_fen=2000, total_cost_fen=1000,
                             expires_at=start))
                await db.flush()
                db.add(OrderPayment(id=key, order_id=key, event_id=key, idempotency_key=key,
                                    amount_fen=2000, paid_at=paid_at))
                if key == "mock-current":
                    db.add(OrderRefund(order_id=key, refund_no=key, amount_fen=2000,
                                       status="succeeded", processed_at=start + timedelta(hours=1)))
            await db.execute(delete(OrderDataMigration))
        for key, when in (("mock-current", start), ("mock-expired", start - timedelta(days=500))):
            await record_payment(sessions, order_id=key, member_id=GUEST, amount_fen=2000,
                                 paid_at=when, event_id=f"mock-{key}")
        await record_refund(sessions, order_id="mock-current", refund_id="mock-return", amount_fen=2000,
                            refunded_at=start + timedelta(hours=1))
        await record_payment(sessions, order_id="actual-two", member_id=GUEST, amount_fen=150,
                             paid_at=start, event_id="actual-second")
        for _ in range(2):
            await database.init_db()
        await clean_points(sessions=sessions)
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(DemoPointEvent)) == 3
            assert await demo_points.overview(db, GUEST) == {"balance": 0, "payments": 2, "refunds": 1}
            formal = (await db.scalars(select(PointTransaction).order_by(PointTransaction.sequence))).all()
            assert [row.book_balance_after for row in formal] == [85, 100]
            assert (await db.get(PointAccount, GUEST)).book_balance == 100
        await clean_points(apply=True, sessions=sessions)
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(DemoPointEvent)) == 0
            assert (await db.get(PointAccount, GUEST)).book_balance == 100

    asyncio.run(migrate())


def test_demo_events_recover_in_order_after_consumer_failure(api, sessions, monkeypatch):
    asyncio.run(seed_users(sessions))
    room = asyncio.run(seed_room(sessions))
    waiting = ok(submit(api, body(room), "demo-retry"), 201)
    replay = demo_points.apply_events

    async def fail(*args, **kwargs):
        raise OperationalError("demo ledger test", {}, RuntimeError("synthetic failure"))

    monkeypatch.setattr(demo_points, "apply_events", fail)
    ok(pay(api, waiting))
    ok(api.post(f'{API}/{waiting["id"]}/cancel', json={}, headers=auth(GUEST)))

    async def inspect(posted):
        async with sessions() as db:
            rows = (await db.scalars(select(DemoPointEvent).where(DemoPointEvent.order_id == waiting["id"]))).all()
            assert {row.kind for row in rows} == {"payment", "refund"}
            assert all((row.posted_at is not None) == posted for row in rows)
            assert (await demo_points.overview(db, GUEST))["balance"] == 0
            assert await db.get(PointAccount, GUEST) is None
    asyncio.run(inspect(False))
    monkeypatch.setattr(demo_points, "apply_events", replay)
    for _ in range(2):
        asyncio.run(maintenance_once(sessions))
    asyncio.run(inspect(True))
