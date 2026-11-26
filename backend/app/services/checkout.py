"""Use the saved route and current publishing/binding rules for browse and submit."""

import hmac
from collections import defaultdict
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.db.content_models import PlaceContent, PlaceContentProduct
from app.db.models import Trip
from app.db.resource_models import PriceOffer, Product, Supplier
from app.services.planning_quality import explicit_departure
from app.services.scenic_restrictions import city_key, name_key
from app.services.stock import remaining

PRODUCT_TYPES = {"hotel": "hotel_room", "ticket": "attraction_ticket"}
PLACE_TYPES = {"hotel": "hotel", "ticket": "attraction"}
LIMITS = {"hotel": 5, "ticket": 20}


def quote_token(trip, kind, product, day, price):
    value = f"checkout:{trip}:{kind}:{product}:{day.isoformat()}:{price}"
    return hmac.digest(settings.jwt_secret_key.encode(), value.encode(), "sha256").hex()


async def load_trip(db, user_id, trip_id, *, lock=False):
    trip = await db.get(Trip, trip_id, with_for_update=lock) if trip_id else None
    if trip is None or trip.user_id != user_id:
        raise HTTPException(404, "行程不存在")
    if trip.status != "completed":
        raise HTTPException(409, "请确认行程后再选择预订项目。")
    return trip


def _start(trip, chosen, today):
    known = explicit_departure((trip.travel_request or {}).get("travel_time"))
    if chosen is not None and known is not None and chosen != known:
        raise HTTPException(422, "本行程已有明确的出发日。")
    if chosen is not None and chosen < today:
        raise HTTPException(422, "出发日不能早于今天。")
    return known or chosen, known is None


def _stops(trip):
    itinerary = trip.itinerary or {}
    duration = trip.duration_days or itinerary.get("duration_days") or 0
    for plan in itinerary.get("day_plans") or []:
        day = plan.get("day")
        if type(day) is not int or day < 1 or day > duration:
            continue
        for place in plan.get("attractions") or []:
            if place.get("name"):
                yield "ticket", day, place
        hotel = plan.get("hotel") or {}
        if day < duration and hotel.get("name"):
            yield "hotel", day, hotel


async def _bindings(db, stops, *, lock):
    ids = {place["content_id"] for _, _, place in stops if place.get("content_id")}
    legacy = {(place.get("offer") or {}).get("product_id") for _, _, place in stops if not place.get("content_id")} - {None}
    if legacy:
        ids.update(await db.scalars(select(PlaceContentProduct.content_id).where(PlaceContentProduct.product_id.in_(legacy))))
    if not ids:
        return {}, {}
    statement = select(PlaceContent).where(PlaceContent.id.in_(ids)).order_by(PlaceContent.id)
    if lock:
        statement = statement.with_for_update()
    places = {row.id: row for row in await db.scalars(statement)}
    links = defaultdict(list)
    rows = await db.execute(select(PlaceContentProduct.content_id, Product, Supplier.status)
        .join(Product, Product.id == PlaceContentProduct.product_id)
        .join(Supplier, Supplier.id == Product.supplier_id)
        .where(PlaceContentProduct.content_id.in_(places))
        .order_by(Product.name, Product.id))
    for content, product, supplier_status in rows:
        links[content].append((product, supplier_status))
    return places, links


def _match_place(city, kind, snapshot, places, links):
    def valid(place):
        return (place is not None and place.status == "published" and place.kind == PLACE_TYPES[kind]
                and city_key(place.city) == city and name_key(place.name) == name_key(snapshot["name"]))

    if content_id := snapshot.get("content_id"):
        place = places.get(content_id)
        return place if valid(place) else None
    product_id = (snapshot.get("offer") or {}).get("product_id")
    if not product_id:
        return None
    matches = [place for place in places.values() if valid(place) and any(
        product.id == product_id and product.type == PRODUCT_TYPES[kind]
        for product, _ in links[place.id]
    )]
    return matches[0] if len(matches) == 1 else None


async def itinerary_candidates(db, trip, departure_date, today, *, lock=False):
    start, date_selectable = _start(trip, departure_date, today)
    stops = list(_stops(trip))
    places, links = await _bindings(db, stops, lock=lock)
    city = city_key(trip.destination or (trip.itinerary or {}).get("destination", ""))
    result = {}
    for kind, day, snapshot in stops:
        place = _match_place(city, kind, snapshot, places, links)
        service_date = start + timedelta(days=day - 1) if start else None
        bound = [(product, supplier) for product, supplier in links[place.id]
                 if product.type == PRODUCT_TYPES[kind] and city_key(product.city) == city] if place else []
        if not bound:
            result[(kind, None, day, snapshot["name"])] = (kind, day, service_date, snapshot["name"], None, None)
        for product, supplier_status in bound:
            result[(kind, product.id, day, "")] = (kind, day, service_date, place.name, product, supplier_status)
    return start, date_selectable, list(result.values())


def quote_status(product, supplier, offer, day, today):
    if product.status != "on_shelf" or supplier != "active":
        return "product_unavailable"
    if day < today:
        return "past_service_date"
    if offer is None:
        return "unquoted"
    if offer.status != "available":
        return "offer_stopped"
    available = remaining(offer)
    if available is None:
        return "unverified_stock"
    if available <= 0:
        return "sold_out"
    return "sellable"


def _stay_segments(rows):
    segment = []
    for row in sorted(rows, key=lambda entry: entry["day"]):
        if segment and (row["day"] != segment[-1]["day"] + 1 or len(segment) == 30):
            yield segment
            segment = []
        segment.append(row)
    if segment:
        yield segment


def _item(kind, product, rows, people):
    first, last = rows[0], rows[-1]
    start = first["service_date"]
    problems = [row["reason"] for row in rows if row["reason"] != "sellable"]
    counts = [row["remaining"] for row in rows if row["remaining"] is not None]
    prices = [row["price_fen"] for row in rows if row["price_fen"] is not None]
    sellable = not problems
    reason = ("sold_out" if "sold_out" in problems else problems[0]) if problems else "sellable"
    status = "needs_date" if reason == "needs_date" else "sold_out" if reason == "sold_out" else (
        "sellable" if sellable else "reference")
    available = min(counts) if len(counts) == len(rows) else None
    return {
        "key": f"{kind}:{product.id if product else first['place_name']}:{start or first['day']}:{last['service_date'] or last['day']}",
        "kind": kind, "product_id": product.id if product else None, "place_name": first["place_name"],
        "name": product.name if product else first["place_name"], "service_date": start,
        "check_in": start if kind == "hotel" else None,
        "check_out": last["service_date"] + timedelta(days=1) if kind == "hotel" and start else None,
        "quantity": min(people if kind == "ticket" else 1, LIMITS[kind], available or 1),
        "unit_price_fen": (sum(prices) if len(prices) == len(rows) else None) if start else min(prices, default=None),
        "remaining": available, "sellable": sellable, "status": status, "reason": reason, "days": rows,
    }


async def options(db, trip, departure, today):
    start, selectable, candidates = await itinerary_candidates(db, trip, departure, today)
    product_ids = {product.id for _, _, _, _, product, _ in candidates if product}
    dates = {day for _, _, day, _, _, _ in candidates if day}
    offers, hints = {}, {}
    if product_ids:
        statement = select(PriceOffer).where(PriceOffer.product_id.in_(product_ids))
        if start:
            offers = {(row.product_id, row.service_date): row for row in await db.scalars(
                statement.where(PriceOffer.service_date.in_(dates))
            )}
        else:
            hints = dict((await db.execute(select(PriceOffer.product_id, PriceOffer.sale_fen).where(
                PriceOffer.product_id.in_(product_ids), PriceOffer.service_date >= today,
                PriceOffer.status == "available",
                PriceOffer.total_quantity > PriceOffer.reserved_quantity + PriceOffer.confirmed_quantity,
            ).order_by(PriceOffer.sale_fen.desc()))).all())
    parties = (trip.travel_request or {}).get("travelers") or {}
    people = max(1, sum(value for role in ("adults", "children", "elderly")
                        if type(value := parties.get(role)) is int and value > 0))
    reference_prices = {}
    for kind, day, place in _stops(trip):
        price = place.get("ticket_price_cny" if kind == "ticket" else "price_per_night_cny")
        if type(price) in (float, int) and 0 < price < 1_000_000:
            reference_prices[kind, day, place["name"]] = round(price * 100)
    hotels = defaultdict(list)
    items = []
    for kind, day, service_date, place_name, product, supplier in candidates:
        offer = offers.get((product.id, service_date)) if product else None
        reason = ("reference" if product is None else "needs_date" if service_date is None
                  else quote_status(product, supplier, offer, service_date, today))
        hint = hints.get(product.id) if product and product.status == "on_shelf" and supplier == "active" else None
        if product is None:
            hint = reference_prices.get((kind, day, place_name))
        priced = {
            "day": day, "service_date": service_date, "reason": reason, "place_name": place_name,
            "remaining": remaining(offer) if offer else None, "price_fen": offer.sale_fen if offer else hint,
            "token": quote_token(trip.id, kind, product.id, service_date, offer.sale_fen) if reason == "sellable" else None,
        }
        if kind == "hotel" and product:
            hotels[product].append(priced)
        else:
            items.append(_item(kind, product, [priced], people))
    for product, rows in hotels.items():
        items.extend(_item("hotel", product, segment, people) for segment in _stay_segments(rows))
    items.sort(key=lambda row: (row["kind"], row["days"][0]["day"], row["name"], row["key"]))
    from app.services import fleet_sales

    vehicle_offers = fleet_sales.trip_offers(trip, start)
    await fleet_sales.attach_models(db, vehicle_offers, trip.destination)
    return {
        "trip_id": trip.id, "departure_date": start, "date_selectable": selectable, "today": today,
        "items": items, "travelers": people, "sellable_count": sum(item["sellable"] for item in items),
        "vehicle_offers": vehicle_offers,
        "undated_count": sum(item["status"] == "needs_date" for item in items),
        "total_fen": sum(item["unit_price_fen"] * item["quantity"] for item in items if item["sellable"]),
    }


def validate_purchase(trip, itinerary, selected, priced, today):
    start, _, candidates = itinerary
    city = city_key(trip.destination or (trip.itinerary or {}).get("destination", ""))
    eligible = {(kind, product.id, day) for kind, _, day, _, product, _ in candidates
                if product and city_key(product.city) == city}
    quoted = {(line["kind"], line["product_id"], quote["service_date"]): quote["token"]
              for line in selected for quote in line["quotes"]}
    expected = {(row["kind"], row["product_id"], row["service_date"]) for row in priced}
    if len(quoted) != sum(len(line["quotes"]) for line in selected) or quoted.keys() != expected:
        raise HTTPException(422, "每项所选服务日期都需要对应的报价版本。")
    conflicts = []
    for row in priced:
        key = row["kind"], row["product_id"], row["service_date"]
        kind, product_id, day = key
        status = quote_status(row["product"], row["supplier"].status, row["offer"], day, today)
        if key not in eligible:
            status = "not_in_itinerary"
        elif status == "sellable" and remaining(row["offer"]) < row["quantity"]:
            status = "sold_out"
        elif status == "sellable" and not hmac.compare_digest(
            quoted[key], quote_token(trip.id, kind, product_id, day, row["offer"].sale_fen),
        ):
            status = "price_changed"
        if status != "sellable":
            conflicts.append({"product_id": product_id, "service_date": day.isoformat(), "reason": status})
    if conflicts:
        raise HTTPException(409, {"message": "部分项目的价格或可售状态已变化，请重新确认。", "items": conflicts})
    return start
