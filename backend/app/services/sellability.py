"""Resolve planning candidates and price hints using the current published catalog."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.content_models import PlaceContent, PlaceContentProduct
from app.db.resource_models import PriceOffer, Product, Supplier
from app.services.scenic_restrictions import city_key

PRODUCT_TYPE = {"attraction": "attraction_ticket", "hotel": "hotel_room"}


async def eligible_offers(db, ids, travel_date, *, kind=None, end_date=None):
    if not ids:
        return {}
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    query = (select(PlaceContent, Product, PriceOffer)
        .join(PlaceContentProduct, PlaceContentProduct.content_id == PlaceContent.id)
        .join(Product, Product.id == PlaceContentProduct.product_id)
        .join(Supplier, Supplier.id == Product.supplier_id)
        .join(PriceOffer, PriceOffer.product_id == Product.id)
        .where(PlaceContent.id.in_(ids), PlaceContent.status == "published",
               Product.status == "on_shelf", Supplier.status == "active", PriceOffer.status == "available",
               PriceOffer.service_date >= today,
               PriceOffer.total_quantity > PriceOffer.reserved_quantity + PriceOffer.confirmed_quantity))
    if kind:
        query = query.where(PlaceContent.kind == kind)
    if travel_date is not None:
        query = query.where(PriceOffer.service_date.between(travel_date, end_date or travel_date))
    found = {}
    for place, product, offer in (await db.execute(query.order_by(
        PriceOffer.sale_fen, PriceOffer.service_date, Product.id,
    ))).all():
        if product.type == PRODUCT_TYPE.get(place.kind) and city_key(product.city) == city_key(place.city):
            found.setdefault(place.id, offer)
    return found


def _candidate(place):
    location = ({"lat": place.lat, "lng": place.lng} if place.lat is not None and place.lng is not None else None)
    return {
        "id": place.id, "content_id": place.id, "source": "content", "kind": place.kind,
        "name": place.name, "city": place.city, "category": place.category, "rating": place.rating or 0,
        "visit_duration_hours": place.visit_duration_hours or 2, "ticket_price_cny": place.ticket_price_hint_cny or 0,
        "opening_hours": place.opening_hours, "description": place.description,
        "landmark_hint": place.landmark_hint, "tags": place.tags or [], "suitable_for": place.suitable_for or [],
        **({"location": location} if location else {}),
    }


async def resolve_content_candidates(db, items, city, kind, travel_date, end_date=None):
    """Resolve vector hits to current SQL rows and consider stocked rows before truncation."""
    variants = {city.strip(), city_key(city), city_key(city) + "市"}
    rows = (await db.scalars(select(PlaceContent).where(
        PlaceContent.kind == kind, PlaceContent.status == "published", PlaceContent.city.in_(variants),
    ).order_by(PlaceContent.id))).all()
    by_id = {row.id: row for row in rows if city_key(row.city) == city_key(city)}
    stocked = await eligible_offers(db, by_id, travel_date, kind=kind, end_date=end_date)
    ordered = dict.fromkeys([item.get("content_id") for item in items] + list(stocked))
    return [_candidate(by_id[key]) for key in ordered if key in by_id]


async def annotate_offers(db, items, *, kind, travel_date: date | None, end_date=None):
    found = await eligible_offers(db, {item["content_id"] for item in items if item.get("content_id")},
                                  travel_date, kind=kind, end_date=end_date)
    cities = dict((await db.execute(select(PlaceContent.id, PlaceContent.city).where(
        PlaceContent.id.in_(found),
    ))).all()) if found else {}
    for item in items:
        item["offer"] = None
        offer = found.get(item.get("content_id"))
        city = item.get("city")
        if offer is not None and (not item.get("kind") or item["kind"] == kind) and (
            not city or city_key(city) == city_key(cities.get(item["content_id"], ""))
        ):
            item["offer"] = {
                "product_id": offer.product_id, "price_cny": offer.sale_fen / 100,
                "remaining": offer.remaining_quantity if travel_date else None,
                "sellable": travel_date is not None, "date_unspecified": travel_date is None,
            }
    return items


async def reclaim_expired_holds(db):
    """Planning uses its own session. Finish unpaid recovery before reading prices."""
    from app.db.database import reserve_write
    from app.services.orders import expire_due

    if db.in_transaction():
        return
    try:
        await reserve_write(db)
        await expire_due(db)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()


def sort_candidates(items, *, anchor=None):
    from app.services.geo import haversine_km

    origin = anchor if anchor and "location" in anchor else {"location": anchor}

    def key(item):
        offer = item.get("offer") or {}
        priority = 0 if offer.get("sellable") else 1 if offer.get("date_unspecified") else 2
        location = item.get("location") or {}
        located = all(isinstance(location.get(axis), (float, int)) for axis in ("lat", "lng"))
        distance = haversine_km(origin, item) if origin["location"] and located else 0
        return priority, not located, round(distance, 2)

    return sorted(items, key=key)
