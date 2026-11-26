"""Price one vehicle service and freeze the same terms when the order is written."""

import hmac
import json
from collections import defaultdict
from datetime import datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.db import database
from app.db.content_models import PlaceContent
from app.db.fleet_models import FleetAllocation, FleetModel
from app.db.order_models import OrderItem
from app.db.resource_models import PriceOffer, Product, Supplier
from app.schemas.fleet import VehicleSelection
from app.services import fleet_capacity
from app.services.planning_quality import explicit_departure
from app.services.scenic_restrictions import city_key, name_key
from app.services.vehicle_routes import DURATIONS, airport_name, build_vehicle_offers, destination_allowed


def product_config(product, supplier, model):
    attrs = product.attributes or {}
    seats, bags = attrs.get("passenger_capacity"), attrs.get("luggage_capacity")
    if (product.type == "vehicle" and product.status == "on_shelf" and supplier.kind == "vehicle_fleet"
            and supplier.status == "active" and city_key(supplier.fleet_city) == city_key(product.city) == "北京"
            and model is not None and attrs.get("purpose") in DURATIONS
            and type(seats) is int and seats > 0 and type(bags) is int and bags >= 0):
        return {
            "product_id": product.id, "supplier_id": supplier.id, "supplier_name": supplier.name,
            "model_code": model.code, "model_name": model.name, "purpose": attrs["purpose"],
            "passenger_capacity": seats, "luggage_capacity": bags,
        }
    return None


async def catalog(db, destination):
    if city_key(destination or "") != "北京":
        return []
    rows = await db.execute(select(Product, Supplier, FleetModel)
        .join(Supplier, Supplier.id == Product.supplier_id)
        .join(FleetModel, (FleetModel.supplier_id == Product.supplier_id)
              & (FleetModel.code == Product.attributes["model_code"].as_string()))
        .where(Product.type == "vehicle", Product.status == "on_shelf", Supplier.status == "active"))
    return [entry for row in rows if (entry := product_config(*row))]


async def attach_models(db, offers, destination):
    if not offers:
        return
    models = await catalog(db, destination)
    for offer in offers:
        offer.models = sorted((model for model in models if model["purpose"] == offer.purpose),
                              key=lambda model: (model["passenger_capacity"], model["model_code"], model["product_id"]))


def _plans(trip):
    return (trip.itinerary or {}).get("day_plans", [])


def trip_offers(trip, start):
    return build_vehicle_offers(_plans(trip), trip.travel_request or {}, trip.destination or "", start)


async def decorate_day_plans(plans, request, destination):
    if city_key(destination or "") != "北京":
        return
    offers = build_vehicle_offers(plans, request, destination, explicit_departure(request.get("travel_time")))
    if offers:
        try:
            async with database.async_session() as db:
                await attach_models(db, offers, destination)
        except SQLAlchemyError:
            # Route and airport candidates still render if the live catalog is unavailable.
            pass
    by_day = defaultdict(list)
    for offer in offers:
        by_day[offer.day].append(offer.model_dump(mode="json"))
    for plan in plans:
        plan["vehicle_offers"] = by_day[plan.get("day")]


async def _service_snapshot(db, offer, selection, trip, clock):
    from app.services.orders import BEIJING

    if offer.service_date is None:
        return "needs_date", None
    if not selection.start_time:
        return "needs_time", None
    if offer.purpose == "charter":
        if ((selection.pickup and name_key(selection.pickup) != name_key(offer.pickup))
                or (selection.dropoff and name_key(selection.dropoff) != name_key(offer.dropoff))):
            return "route_changed", None
        pickup, dropoff = offer.pickup, offer.dropoff
    else:
        pickup = airport_name(selection.pickup)
        dropoff = selection.dropoff
        if pickup is None:
            return "invalid_airport", None
        if not destination_allowed(dropoff, _plans(trip)):
            known = await db.scalar(select(PlaceContent.id).where(
                PlaceContent.name == dropoff, PlaceContent.city.in_(("北京", "北京市")),
                PlaceContent.status == "published",
            ).limit(1)) if dropoff else None
            if known is None:
                return "invalid_dropoff", None
    starts = datetime.combine(offer.service_date, time.fromisoformat(selection.start_time), tzinfo=BEIJING)
    try:
        ends = starts + timedelta(minutes=offer.duration_minutes)
    except OverflowError:
        return "invalid_time", None
    if starts <= clock:
        return "past_service_time", None
    return None, {
        "service_key": offer.service_key, "purpose": offer.purpose,
        "service_date": offer.service_date.isoformat(), "starts_at": starts.isoformat(), "ends_at": ends.isoformat(),
        "pickup": pickup, "dropoff": dropoff, "legs": [leg.model_dump() for leg in offer.legs],
        "passengers": selection.passengers, "luggage": selection.luggage,
    }


def _demand(snapshot):
    return fleet_capacity.Demand(
        snapshot["model_code"], fleet_capacity.utc(datetime.fromisoformat(snapshot["starts_at"])),
        fleet_capacity.utc(datetime.fromisoformat(snapshot["ends_at"])), snapshot["passengers"], snapshot["luggage"],
    )


async def _option(db, model, offer, info, shared_issue, clock, *, match_time=True):
    reason = shared_issue
    if info and not reason:
        if info["passengers"] > model["passenger_capacity"]:
            reason = "passenger_limit"
        elif info["luggage"] > model["luggage_capacity"]:
            reason = "luggage_limit"
        elif not offer:
            reason = "unquoted"
        elif not offer.trip_priced:
            reason = "unverified_trip_price"
        elif offer.status != "available":
            reason = "offer_stopped"
        elif not offer.stock_verified:
            reason = "unverified_stock"
        elif not offer.remaining_quantity:
            reason = "sold_out"
        elif match_time:
            day_use = _demand({**info, "model_code": model["model_code"]})
            if not await fleet_capacity.can_add(db, model["supplier_id"], [day_use], now=clock):
                reason = "timeslot_full"
    return reason


def _snapshot(model, offer, service):
    return {**service, **{key: model[key] for key in (
        "supplier_id", "supplier_name", "model_code", "model_name", "product_id",
    )}, "amount_fen": offer.sale_fen, "price_unit": "趟"}


def _token(trip_id, snapshot):
    payload = json.dumps([trip_id, snapshot], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hmac.digest(settings.jwt_secret_key.encode(), b"fleet-quote:" + payload.encode(), "sha256").hex()


async def quote(db, trip, start, selection, clock):
    service = next((service for service in trip_offers(trip, start) if service.service_key == selection.service_key), None)
    if service is None:
        raise HTTPException(409, "当前行程中没有该用车服务。")
    shared_issue, info = await _service_snapshot(db, service, selection, trip, clock)
    choices = []
    for model in await catalog(db, trip.destination):
        if model["purpose"] != service.purpose:
            continue
        offer = await db.get(PriceOffer, (model["product_id"], service.service_date)) if service.service_date else None
        reason = await _option(db, model, offer, info, shared_issue, clock)
        snapshot = _snapshot(model, offer, info) if not reason else None
        choices.append({
            **model, "reason": reason or "sellable", "sellable": reason is None,
            "price_fen": offer.sale_fen if offer and offer.trip_priced else None,
            "token": _token(trip.id, snapshot) if snapshot else None,
        })
    choices.sort(key=lambda model: (not model["sellable"], model["passenger_capacity"],
                                    model["price_fen"] if model["price_fen"] is not None else float("inf"),
                                    model["model_code"], model["product_id"]))
    return {
        "service_key": service.service_key, "service_date": service.service_date,
        "starts_at": info["starts_at"] if info else None, "ends_at": info["ends_at"] if info else None,
        "reason": shared_issue or ("no_supply" if not choices else None),
        "recommended_product_id": next((choice["product_id"] for choice in choices if choice["sellable"]), None),
        "options": choices,
    }


def _conflict(row, reason):
    return {"service_key": row["vehicle"]["service_key"], "product_id": row["product_id"],
            "service_date": row["service_date"].isoformat(), "reason": reason}


async def verify_purchase(db, trip, start, rows, clock):
    if not rows:
        return
    services = {offer.service_key: offer for offer in trip_offers(trip, start)}
    issues, by_supplier = [], defaultdict(list)
    for row in rows:
        selection = VehicleSelection.model_validate(row["vehicle"])
        service = services.get(selection.service_key)
        if service is None or service.service_date != row["service_date"]:
            issues.append(_conflict(row, "not_in_itinerary"))
            continue
        product, supplier, offer = row["product"], row["supplier"], row["offer"]
        model = await db.get(FleetModel, (supplier.id, (product.attributes or {}).get("model_code")))
        config = product_config(product, supplier, model)
        if config is None or config["purpose"] != service.purpose:
            issues.append(_conflict(row, "product_unavailable"))
            continue
        reason, info = await _service_snapshot(db, service, selection, trip, clock)
        reason = await _option(db, config, offer, info, reason, clock, match_time=False)
        if reason:
            issues.append(_conflict(row, reason))
            continue
        snapshot = _snapshot(config, offer, info)
        if not hmac.compare_digest(_token(trip.id, snapshot), row["vehicle_token"]):
            issues.append(_conflict(row, "price_or_terms_changed"))
            continue
        row["fleet_snapshot"] = snapshot
        by_supplier[supplier.id].append(row)
    for supplier, selected in by_supplier.items():
        if not await fleet_capacity.can_add(db, supplier, [_demand(row["fleet_snapshot"]) for row in selected], now=clock):
            issues.extend(_conflict(row, "timeslot_full") for row in selected)
    if issues:
        raise HTTPException(409, {"message": "部分用车项目的报价或时段运力已变化。", "items": issues})


def reserve(db, order, item, snapshot):
    slot = _demand(snapshot)
    db.add(FleetAllocation(
        order_item_id=item.id, order_id=order.id, supplier_id=item.supplier_id,
        service_key=snapshot["service_key"], model_code=slot.model_code,
        starts_at=slot.starts_at, ends_at=slot.ends_at, passengers=slot.passengers, luggage=slot.luggage,
    ))


async def verify_reserved(db, order_id, *, confirm=False):
    await fleet_capacity.lock_order_fleets(db, [order_id])
    items = (await db.scalars(select(OrderItem).where(OrderItem.order_id == order_id, OrderItem.product_type == "vehicle"))).all()
    slots = (await db.scalars(select(FleetAllocation).where(
        FleetAllocation.order_id == order_id, FleetAllocation.state == "reserved",
    ))).all()
    indexed = {row.order_item_id: row for row in slots}
    wanted = {item.id: item for item in items if (item.attributes or {}).get("fleet")}
    if indexed.keys() != wanted.keys():
        raise HTTPException(409, "用车时段占用与订单明细不符，请人工核实。")
    for key, item in wanted.items():
        hold = indexed[key]
        snapshot = item.attributes["fleet"]
        if (fleet_capacity.Demand.from_row(hold) != _demand(snapshot) or hold.supplier_id != item.supplier_id
                or hold.service_key != snapshot["service_key"]):
            raise HTTPException(409, "用车时段占用与订单明细不符，请人工核实。")
    if confirm:
        for hold in slots:
            hold.state = "confirmed"


async def release(db, order_id):
    await fleet_capacity.lock_order_fleets(db, [order_id])
    slots = await db.scalars(select(FleetAllocation).where(
        FleetAllocation.order_id == order_id, FleetAllocation.state.in_(fleet_capacity.HELD),
    ))
    for slot in slots:
        slot.state = "released"
