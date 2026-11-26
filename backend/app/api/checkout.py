"""Turn a saved itinerary into the add-on list a tourist can buy."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentAccount, DbSession as DB
from app.api.support import no_store
from app.db.resource_models import PriceOffer, Product, Supplier
from app.services import trip_store

router = APIRouter(prefix="/v1/checkout", dependencies=[Depends(no_store)])


def _day(plan: dict) -> date | None:
    raw = plan.get("date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


@router.get("/options")
async def checkout_options(trip_id: str, account: CurrentAccount, db: DB):
    trip = await trip_store.get_trip(db, trip_id, user_id=account.id)
    if trip is None:
        raise HTTPException(404, "行程不存在")
    itinerary = trip.get("itinerary") or {}
    day_plans = itinerary.get("day_plans") or []
    travelers = (trip.get("travel_request") or {}).get("travelers") or {}
    people = max(1, int(travelers.get("adults") or 1) + int(travelers.get("children") or 0)
                 + int(travelers.get("elderly") or 0))

    candidates: list[dict] = []
    for plan in day_plans:
        service_date = _day(plan)
        for attraction in plan.get("attractions") or []:
            offer = attraction.get("offer") or {}
            if not offer.get("product_id"):
                continue
            candidates.append({
                "kind": "ticket", "product_id": offer["product_id"],
                "name": attraction.get("name", ""), "service_date": service_date,
                "quantity": people, "check_in": None, "check_out": None,
                "unit_price_hint": int(round(float(offer.get("price_cny") or 0) * 100)),
            })
        hotel = plan.get("hotel") or {}
        offer = hotel.get("offer") or {}
        if offer.get("product_id"):
            candidates.append({
                "kind": "hotel", "product_id": offer["product_id"],
                "name": hotel.get("name", ""), "service_date": service_date,
                "quantity": 1, "check_in": service_date,
                "check_out": service_date + timedelta(days=1) if service_date else None,
                "unit_price_hint": int(round(float(offer.get("price_cny") or 0) * 100)),
            })

    merged: dict[tuple, dict] = {}
    for entry in candidates:
        key = (entry["kind"], entry["product_id"], entry["service_date"])
        if key in merged:
            continue
        merged[key] = entry

    items = []
    undated = 0
    for entry in merged.values():
        if entry["service_date"] is None:
            # 行程没给出日期（用户没说什么时候去）：先列出来并提示需选日期，
            # 否则用户会以为「我们的商品没出现」。
            undated += 1
            if entry.get("unit_price_hint"):
                items.append({
                    **entry, "service_date": None, "check_in": None, "check_out": None,
                    "unit_price_fen": entry["unit_price_hint"], "remaining": None,
                    "sellable": False, "needs_date": True,
                })
            continue
        row = (await db.execute(
            select(Product, Supplier, PriceOffer)
            .join(Supplier, Supplier.id == Product.supplier_id)
            .join(PriceOffer, PriceOffer.product_id == Product.id)
            .where(Product.id == entry["product_id"], PriceOffer.service_date == entry["service_date"])
        )).one_or_none()
        if row is None:
            continue
        product, supplier, offer = row
        remaining = None if offer.total_quantity is None else (
            offer.total_quantity - offer.reserved_quantity - offer.confirmed_quantity)
        sellable = (
            product.status == "on_shelf" and supplier.status == "active"
            and offer.status == "available" and offer.total_quantity is not None
            and (remaining or 0) > 0
        )
        items.append({
            **entry, "service_date": entry["service_date"].isoformat(),
            "check_in": entry["check_in"].isoformat() if entry["check_in"] else None,
            "check_out": entry["check_out"].isoformat() if entry["check_out"] else None,
            "unit_price_fen": offer.sale_fen, "remaining": remaining, "sellable": sellable,
            "needs_date": False,
        })

    items.sort(key=lambda item: (item["kind"], item.get("service_date") or ""))
    total = sum(item["unit_price_fen"] * item["quantity"] for item in items if item["sellable"])
    return {
        "trip_id": trip_id, "travelers": people, "items": items,
        "sellable_count": sum(1 for item in items if item["sellable"]),
        "undated_count": undated,
        "offer_count": len(candidates),
        "total_fen": total,
    }




