from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession, WriteDbSession
from app.api.support import Page, no_store
from app.db.fleet_models import FleetAllocation, FleetModel
from app.db.resource_models import Driver, PriceOffer, Product, Supplier, Vehicle
from app.schemas.fleet import DriverInput, FleetModelInput, FleetModelName, ModelCode, VehicleInput
from app.services import fleet_capacity, orders
from app.services.scenic_restrictions import city_key

router = APIRouter(prefix="/fleet", dependencies=[Depends(no_store)])


async def _fleet(db, supplier_id, *, lock=False):
    row = await db.get(Supplier, supplier_id, with_for_update=lock, populate_existing=lock)
    if row is None or row.kind != "vehicle_fleet" or city_key(row.fleet_city) != "北京":
        raise HTTPException(422, "请选择已设置北京服务城市的车队供应商。")
    return row


def _roster_view(row):
    fields = ("plate_no", "model_code", "model_name", "seats", "luggage") if isinstance(row, Vehicle) else (
        "name", "phone", "license_type", "service_cities", "model_codes",
    )
    return {key: getattr(row, key) for key in ("id", "supplier_id", "status", "notes", *fields)}


async def _list(db, model, supplier_id, page):
    filters = [model.supplier_id == supplier_id] if supplier_id else []
    total = await db.scalar(select(func.count()).select_from(model).where(*filters))
    rows = await db.scalars(select(model).where(*filters).order_by(model.id).limit(page.limit).offset(page.offset))
    return {"items": [_roster_view(row) for row in rows], "total": total}


async def _flush(db):
    try:
        await db.flush()
    except IntegrityError as error:
        raise HTTPException(409, "相同记录已存在，或该记录仍有业务引用。") from error


async def _find_locked(db, model, key, supplier_id=None):
    row = await db.get(model, key) if key else None
    if key and row is None:
        raise HTTPException(404, "记录不存在。")
    if row and supplier_id and row.supplier_id != supplier_id:
        raise HTTPException(422, "不能更改车辆或司机的车队归属。")
    fleet_id = supplier_id or row.supplier_id
    await _fleet(db, fleet_id, lock=True)
    if key:
        row = await db.get(model, key, populate_existing=True, with_for_update=True)
        if row is None or row.supplier_id != fleet_id:
            raise HTTPException(404, "记录不存在。")
    return fleet_id, row


async def _save(db, model, body, key=None):
    supplier_id, row = await _find_locked(db, model, key, body.supplier_id)
    before = await fleet_capacity.roster(db, supplier_id)
    values = body.model_dump()
    codes = [body.model_code] if model is Vehicle else list(dict.fromkeys(body.model_codes))
    names = {}
    for code in codes:
        record = await db.get(FleetModel, (supplier_id, code))
        if record is None:
            raise HTTPException(422, "车型编码不存在于所选车队。")
        names[code] = record.name
    if model is Vehicle:
        values["model_name"] = names[body.model_code]
        values["plate_no"] = body.plate_no.upper()
    else:
        if not any(city_key(city) == "北京" for city in body.service_cities):
            raise HTTPException(422, "北京试点司机须包含北京市服务资质。")
        values["model_codes"] = codes
    if row is None:
        row = model(**values)
        db.add(row)
    else:
        for field, value in values.items():
            setattr(row, field, value)
    await _flush(db)
    await fleet_capacity.verify_roster_change(db, supplier_id, before, now=orders.now_utc())
    return _roster_view(row)


async def _change_status(db, model, key, *, delete=False):
    supplier_id, row = await _find_locked(db, model, key)
    before = await fleet_capacity.roster(db, supplier_id)
    if delete:
        column = FleetAllocation.vehicle_id if model is Vehicle else FleetAllocation.driver_id
        if await db.scalar(select(FleetAllocation.order_item_id).where(column == key).limit(1)):
            raise HTTPException(409, "该记录有历史指派，只能停用。")
        await db.delete(row)
    else:
        row.status = "inactive"
    await _flush(db)
    await fleet_capacity.verify_roster_change(db, supplier_id, before, now=orders.now_utc())
    return Response(status_code=204)


@router.get("/models")
async def models(supplier_id: str, db: DbSession):
    await _fleet(db, supplier_id)
    return list(await db.scalars(select(FleetModel).where(FleetModel.supplier_id == supplier_id).order_by(FleetModel.code)))


@router.post("/models", status_code=201)
async def add_model(supplier_id: str, body: FleetModelInput, db: WriteDbSession):
    await _fleet(db, supplier_id, lock=True)
    row = FleetModel(supplier_id=supplier_id, **body.model_dump())
    db.add(row)
    await _flush(db)
    return row


@router.patch("/models/{code}")
async def rename_model(supplier_id: str, code: ModelCode, body: FleetModelName, db: WriteDbSession):
    await _fleet(db, supplier_id, lock=True)
    row = await db.get(FleetModel, (supplier_id, code))
    if row is None:
        raise HTTPException(404, "车型不存在。")
    row.name = body.name
    await db.execute(update(Vehicle).where(Vehicle.supplier_id == supplier_id, Vehicle.model_code == code)
                     .values(model_name=body.name))
    return row


@router.delete("/models/{code}", status_code=204)
async def remove_model(supplier_id: str, code: ModelCode, db: WriteDbSession):
    await _fleet(db, supplier_id, lock=True)
    row = await db.get(FleetModel, (supplier_id, code))
    if row is None:
        raise HTTPException(404, "车型不存在。")
    references = (
        select(Vehicle.id).where(Vehicle.supplier_id == supplier_id, Vehicle.model_code == code),
        select(Product.id).where(Product.supplier_id == supplier_id, Product.type == "vehicle",
                                 Product.attributes["model_code"].as_string() == code),
        select(FleetAllocation.order_item_id).where(FleetAllocation.supplier_id == supplier_id, FleetAllocation.model_code == code),
    )
    driver_codes = await db.scalars(select(Driver.model_codes).where(Driver.supplier_id == supplier_id))
    if any(code in (codes or []) for codes in driver_codes):
        raise HTTPException(409, "车型仍被司机资格引用。")
    for statement in references:
        if await db.scalar(statement.limit(1)):
            raise HTTPException(409, "车型仍被车辆、商品或订单引用。")
    await db.delete(row)
    return Response(status_code=204)


@router.get("/vehicles")
async def vehicles(db: DbSession, page: Page, supplier_id: str | None = None):
    return await _list(db, Vehicle, supplier_id, page)


@router.post("/vehicles", status_code=201)
async def add_vehicle(body: VehicleInput, db: WriteDbSession):
    return await _save(db, Vehicle, body)


@router.patch("/vehicles/{key}")
async def edit_vehicle(key: str, body: VehicleInput, db: WriteDbSession):
    return await _save(db, Vehicle, body, key)


@router.post("/vehicles/{key}/disable", status_code=204)
async def disable_vehicle(key: str, db: WriteDbSession):
    return await _change_status(db, Vehicle, key)


@router.delete("/vehicles/{key}", status_code=204)
async def delete_vehicle(key: str, db: WriteDbSession):
    return await _change_status(db, Vehicle, key, delete=True)


@router.get("/drivers")
async def drivers(db: DbSession, page: Page, supplier_id: str | None = None):
    return await _list(db, Driver, supplier_id, page)


@router.post("/drivers", status_code=201)
async def add_driver(body: DriverInput, db: WriteDbSession):
    return await _save(db, Driver, body)


@router.patch("/drivers/{key}")
async def edit_driver(key: str, body: DriverInput, db: WriteDbSession):
    return await _save(db, Driver, body, key)


@router.post("/drivers/{key}/disable", status_code=204)
async def disable_driver(key: str, db: WriteDbSession):
    return await _change_status(db, Driver, key)


@router.delete("/drivers/{key}", status_code=204)
async def delete_driver(key: str, db: WriteDbSession):
    return await _change_status(db, Driver, key, delete=True)


@router.get("/capacity")
async def capacity(db: WriteDbSession, supplier_id: str, model_code: ModelCode,
                   starts_at: AwareDatetime, ends_at: AwareDatetime,
                   passengers: Annotated[int, Query(ge=1, le=100)] = 1,
                   luggage: Annotated[int, Query(ge=0, le=100)] = 0):
    if not timedelta(0) < ends_at - starts_at <= timedelta(days=2):
        raise HTTPException(422, "请选择有效的起止时段（最长两天）。")
    await _fleet(db, supplier_id)
    if not await db.get(FleetModel, (supplier_id, model_code)):
        raise HTTPException(404, "车型不存在。")
    clock = orders.now_utc()
    await orders.expire_due(db, now=clock)
    cars, crew = await fleet_capacity.roster(db, supplier_id)
    item = fleet_capacity.Demand(model_code, fleet_capacity.utc(starts_at), fleet_capacity.utc(ends_at), passengers, luggage)
    rows = await fleet_capacity.commitments(db, supplier_id, start=min(item.starts_at, clock), now=clock)
    prior = [fleet_capacity.Demand.from_row(row) for row in rows]
    available = 0
    for count in range(1, min(sum(car.model_code == model_code for car in cars), len(crew)) + 1):
        if not fleet_capacity.fits([*prior, *([item] * count)], cars, crew, affected_after=len(prior)):
            break
        available = count
    day = starts_at.astimezone(orders.BEIJING).date()
    daily = await db.execute(select(Product, PriceOffer).outerjoin(
        PriceOffer, (Product.id == PriceOffer.product_id) & (PriceOffer.service_date == day),
    ).where(Product.supplier_id == supplier_id, Product.type == "vehicle",
            Product.attributes["model_code"].as_string() == model_code).order_by(Product.id))
    return {"model_code": model_code, "available": available, "service_date": day,
            "daily": [{"product_id": product.id, "name": product.name, "purpose": product.attributes.get("purpose"),
                       "total_quantity": offer.total_quantity if offer else None,
                       "reserved_quantity": offer.reserved_quantity if offer else 0,
                       "confirmed_quantity": offer.confirmed_quantity if offer else 0,
                       "remaining_quantity": offer.remaining_quantity if offer else None}
                      for product, offer in daily]}
