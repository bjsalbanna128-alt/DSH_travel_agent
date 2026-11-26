"""Operator resource queries and transaction rules."""

from datetime import date, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.fleet_models import FleetModel
from app.db.resource_models import Driver, PriceOffer, Product, Supplier, Vehicle
from app.schemas.admin_resources import (
    MAX_OFFER_DAYS,
    PRICE_UNITS,
    HotelStay,
    OfferBatch,
    OfferBatchResult,
    OfferCreate,
    OfferDay,
    OfferPage,
    OfferPatch,
    OfferQuote,
    OfferStatus,
    ProductCreate,
    ProductPatch,
    ProductResponse,
    UnavailableReason,
)


async def flush(db: AsyncSession, on_conflict: str) -> None:
    try:
        await db.flush()
    except IntegrityError as error:
        raise HTTPException(409, on_conflict) from error


async def get_supplier(db: AsyncSession, supplier_id: str, *, lock: bool = False) -> Supplier:
    supplier = await db.get(Supplier, supplier_id, with_for_update=lock, populate_existing=lock)
    if supplier is None:
        raise HTTPException(404, "供应商不存在")
    return supplier


async def delete_supplier(db: AsyncSession, supplier: Supplier) -> None:
    detail = "该供应商仍有关联商品，请先在商品管理中处理后再删除。"
    if await db.scalar(select(Product.id).where(Product.supplier_id == supplier.id).limit(1)):
        raise HTTPException(409, detail)
    fleet_detail = "该供应商仍有车辆或司机，请先处理车队台账后再删除。"
    if await db.scalar(select(Vehicle.id).where(Vehicle.supplier_id == supplier.id).limit(1)):
        raise HTTPException(409, fleet_detail)
    if await db.scalar(select(Driver.id).where(Driver.supplier_id == supplier.id).limit(1)):
        raise HTTPException(409, fleet_detail)
    if await db.scalar(select(FleetModel.code).where(FleetModel.supplier_id == supplier.id).limit(1)):
        raise HTTPException(409, "该车队仍有车型，请先在车队台账处理车型后再删除。")
    await db.delete(supplier)
    await flush(db, detail)


def product_listing():
    counts = select(PriceOffer.product_id, func.count().label("offer_count")).group_by(
        PriceOffer.product_id
    ).subquery()
    return (
        select(Product, Supplier.name, Supplier.status, func.coalesce(counts.c.offer_count, 0))
        .join(Supplier, Supplier.id == Product.supplier_id)
        .outerjoin(counts, counts.c.product_id == Product.id)
    )


def product_response(row) -> ProductResponse:
    product, supplier_name, supplier_status, count = row
    return ProductResponse(
        **{name: getattr(product, name) for name in ProductCreate.model_fields},
        id=product.id, supplier_name=supplier_name, supplier_status=supplier_status,
        price_unit=PRICE_UNITS[product.type], offer_count=count,
        created_at=product.created_at, updated_at=product.updated_at,
    )


async def get_product(db: AsyncSession, product_id: str, *, lock: bool = False, new_supplier=None) -> Product:
    owners = {}
    if lock:
        from app.services.fleet_capacity import lock_product_suppliers

        owners = await lock_product_suppliers(db, [product_id], additional=[new_supplier] if new_supplier else [])
    product = await db.get(Product, product_id, with_for_update=lock, populate_existing=lock)
    if product is None:
        raise HTTPException(404, "商品不存在")
    if lock and product.supplier_id not in (owners.get(product.id), new_supplier):
        raise HTTPException(409, "商品归属已变化，请刷新后重试。")
    return product


async def get_product_details(db: AsyncSession, product_id: str) -> ProductResponse:
    row = (await db.execute(product_listing().where(Product.id == product_id))).one_or_none()
    if row is None:
        raise HTTPException(404, "商品不存在")
    return product_response(row)


async def _validate_listing(
    db: AsyncSession, data: ProductCreate, *, check_supplier: bool,
) -> None:
    supplier = await get_supplier(db, data.supplier_id, lock=True)
    if data.status != "on_shelf":
        return
    if check_supplier and supplier.status != "active":
        raise HTTPException(409, "供应商已停用，请启用供应商后再上架商品。")
    if data.type != "vehicle" and data.poi is None:
        place = "酒店" if data.type == "hotel_room" else "景点"
        raise HTTPException(409, f"请先绑定{place} POI，再上架商品。")
    if data.type == "vehicle":
        from app.services.scenic_restrictions import city_key

        attrs = data.attributes
        if (supplier.kind != "vehicle_fleet" or city_key(supplier.fleet_city) != "北京"
                or city_key(data.city) != "北京" or not attrs.model_code or not attrs.purpose
                or attrs.luggage_capacity is None or attrs.passenger_capacity > 100):
            raise HTTPException(422, "上架前请选择北京车队，填写车型编码、用途及人数和行李容量。")
        if await db.get(FleetModel, (supplier.id, attrs.model_code)) is None:
            raise HTTPException(422, "车型编码不属于该车队。")


async def create_product(db: AsyncSession, data: ProductCreate) -> ProductResponse:
    await _validate_listing(db, data, check_supplier=True)
    product = Product(**data.model_dump())
    db.add(product)
    await flush(db, "供应商状态或归属发生变化，请刷新后重试。")
    return await get_product_details(db, product.id)


async def _product_has_offers(db: AsyncSession, product_id: str) -> bool:
    return await db.scalar(
        select(PriceOffer.product_id).where(PriceOffer.product_id == product_id).limit(1)
    ) is not None


def _poi_key(poi: dict | None) -> tuple[str, str] | None:
    return (poi["source"], poi["id"]) if poi else None


async def update_product(db: AsyncSession, product: Product, patch: ProductPatch) -> ProductResponse:
    changes = patch.model_dump(exclude_unset=True)
    supplier_changed = changes.get("supplier_id", product.supplier_id) != product.supplier_id
    type_changed = changes.get("type", product.type) != product.type
    poi_changed = _poi_key(changes.get("poi", product.poi)) != _poi_key(product.poi)
    desired_status = changes.get("status", product.status)
    if (supplier_changed or type_changed or poi_changed) and await _product_has_offers(db, product.id):
        if supplier_changed or type_changed:
            raise HTTPException(409, "商品已有报价，变更供应商或商品类型需要新建商品。")
        if product.status == "on_shelf" or desired_status == "on_shelf":
            raise HTTPException(409, "商品已有报价，请在下架状态下更换 POI，核对报价后再上架。")

    current = {name: getattr(product, name) for name in ProductCreate.model_fields}
    try:
        desired = ProductCreate.model_validate(current | changes)
    except ValidationError as error:
        raise HTTPException(422, error.errors()[0]["msg"]) from error

    if desired.type == product.type == "vehicle" and await _product_has_offers(db, product.id):
        for field in ("model_code", "purpose"):
            if (old := product.attributes.get(field)) and old != getattr(desired.attributes, field):
                raise HTTPException(409, "已维护报价的车型编码和用途不能修改，请新建商品。")

    await _validate_listing(
        db, desired, check_supplier=supplier_changed or product.status != "on_shelf",
    )
    for name, value in desired.model_dump().items():
        setattr(product, name, value)
    await flush(db, "商品或供应商状态发生变化，请刷新后重试。")
    return await get_product_details(db, product.id)


async def delete_product(db: AsyncSession, product: Product) -> None:
    detail = "该商品仍有关联报价，请先在商品详情处理报价后再删除。"
    if await _product_has_offers(db, product.id):
        raise HTTPException(409, detail)
    await db.delete(product)
    await flush(db, detail)


def offer_days(start: date, end: date) -> list[date]:
    length = (end - start).days + 1
    if not 1 <= length <= MAX_OFFER_DAYS:
        raise HTTPException(422, f"日期范围应包含 1 到 {MAX_OFFER_DAYS} 天，且结束日不能早于开始日。")
    return [start + timedelta(days=index) for index in range(length)]


def offer_day(
    product_status: str, supplier_status: str, day: date, offer: PriceOffer | None, *,
    vehicle=False, fleet_configured=True,
) -> OfferDay:
    reasons: list[UnavailableReason] = []
    if supplier_status != "active":
        reasons.append("supplier_inactive")
    if product_status != "on_shelf":
        reasons.append("product_off_shelf")
    if not fleet_configured:
        reasons.append("vehicle_configuration")
    if offer is None:
        reasons.append("unquoted")
    else:
        if vehicle and not offer.trip_priced:
            reasons.append("unverified_trip_price")
        if offer.status == "stopped":
            reasons.append("offer_stopped")
        if offer.total_quantity is None:
            # 未核定投放量的历史报价只能查看，游客不能下单。
            reasons.append("unverified_stock")
        elif offer.remaining_quantity is not None and offer.remaining_quantity <= 0:
            reasons.append("sold_out")

    quote = None if offer is None else OfferQuote(
        cost_fen=offer.cost_fen, sale_fen=offer.sale_fen, status=offer.status,
        below_cost=offer.sale_fen < offer.cost_fen,
        total_quantity=offer.total_quantity,
        reserved_quantity=offer.reserved_quantity,
        confirmed_quantity=offer.confirmed_quantity,
        remaining=offer.remaining_quantity,
        stock_verified=offer.stock_verified,
        trip_priced=offer.trip_priced if vehicle else None,
    )
    return OfferDay(service_date=day, quote=quote, can_sell=not reasons, reasons=reasons)


async def _offer_rules(db: AsyncSession, product: Product, supplier: Supplier) -> dict[str, bool]:
    vehicle = product.type == "vehicle"
    if not vehicle or product.status != "on_shelf" or supplier.status != "active":
        return {"vehicle": vehicle}
    from app.services.fleet_sales import product_config

    code = (product.attributes or {}).get("model_code")
    model = await db.get(FleetModel, (supplier.id, code)) if code else None
    return {"vehicle": True, "fleet_configured": product_config(product, supplier, model) is not None}


async def get_offer_day(db: AsyncSession, product: Product, offer: PriceOffer) -> OfferDay:
    supplier = await get_supplier(db, product.supplier_id)
    return offer_day(product.status, supplier.status, offer.service_date, offer,
                     **await _offer_rules(db, product, supplier))


async def list_offers(
    db: AsyncSession, product: Product, *, start: date | None, end: date | None,
    status: OfferStatus | None, check_in: date | None, check_out: date | None,
    offset: int, limit: int,
) -> OfferPage:
    supplier = await get_supplier(db, product.supplier_id)
    is_stay = check_in is not None or check_out is not None
    if is_stay:
        if product.type != "hotel_room":
            raise HTTPException(422, "仅酒店房型支持跨夜核对。")
        if start is not None or end is not None:
            raise HTTPException(422, "入住退房查询和服务日期查询应分别提交。")
        if check_in is None or check_out is None or check_out <= check_in:
            raise HTTPException(422, "请同时填写入住日与退房日，退房日须晚于入住日。")
        start, end = check_in, check_out - timedelta(days=1)

    rules = await _offer_rules(db, product, supplier)
    statement = select(PriceOffer).where(PriceOffer.product_id == product.id)
    if start is not None:
        statement = statement.where(PriceOffer.service_date >= start)
    if end is not None:
        statement = statement.where(PriceOffer.service_date <= end)

    if start is not None and end is not None:
        days = offer_days(start, end)
        by_day = {row.service_date: row for row in (await db.scalars(statement)).all()}
        entries = [offer_day(product.status, supplier.status, day, by_day.get(day), **rules)
                   for day in days]
        stay = None
        if is_stay:
            no_gaps = len(by_day) == len(days)
            unavailable = [entry for entry in entries if not entry.can_sell]
            stay = HotelStay(
                check_in=check_in, check_out=check_out, nights=len(days), can_sell=not unavailable,
                cost_fen=sum(row.cost_fen for row in by_day.values()) if no_gaps else None,
                sale_fen=sum(row.sale_fen for row in by_day.values()) if no_gaps else None,
                unavailable=unavailable,
            )
        if status is not None:
            entries = [entry for entry in entries if entry.quote and entry.quote.status == status]
        return OfferPage(items=entries[offset:offset + limit], total=len(entries), stay=stay)

    if status is not None:
        statement = statement.where(PriceOffer.status == status)
    total = await db.scalar(select(func.count()).select_from(statement.subquery()))
    offers = (await db.scalars(statement.order_by(PriceOffer.service_date).offset(offset).limit(limit))).all()
    return OfferPage(
        items=[offer_day(product.status, supplier.status, row.service_date, row, **rules)
               for row in offers],
        total=total or 0,
    )


async def get_offer(db: AsyncSession, product: Product, day: date) -> PriceOffer:
    offer = await db.get(PriceOffer, (product.id, day), with_for_update=True, populate_existing=True)
    if offer is None:
        raise HTTPException(404, "该商品在此日期没有报价。")
    return offer


async def delete_offer(db: AsyncSession, product: Product, day: date) -> None:
    from app.db.order_models import OrderItem
    from app.db.resource_models import OfferAllocation

    offer = await get_offer(db, product, day)
    for model in (OrderItem, OfferAllocation):
        referenced = await db.scalar(select(model.id).where(
            model.product_id == product.id, model.service_date == day,
        ).limit(1))
        if referenced:
            raise HTTPException(409, "该日报价已有交易引用，请将其停售。")
    await db.delete(offer)


def _date_conflict(days: list[date]) -> HTTPException:
    return HTTPException(409, {
        "message": "所选日期已有报价，请核对冲突日期。",
        "dates": [day.isoformat() for day in days],
    })


async def create_offer(db: AsyncSession, product: Product, data: OfferCreate) -> OfferDay:
    if await db.get(PriceOffer, (product.id, data.service_date)) is not None:
        raise _date_conflict([data.service_date])
    if product.type == "vehicle" and data.status == "available" and not data.trip_priced:
        raise HTTPException(422, "请核对并确认用车售价为元/趟。")
    offer = PriceOffer(product_id=product.id, **data.model_dump())
    db.add(offer)
    try:
        await db.flush()
    except IntegrityError as error:
        raise _date_conflict([data.service_date]) from error
    return await get_offer_day(db, product, offer)


async def update_offer(db: AsyncSession, product: Product, day: date, patch: OfferPatch) -> OfferDay:
    offer = await get_offer(db, product, day)
    values = patch.model_dump(exclude_unset=True)
    if (product.type == "vehicle" and values.get("status") == "available"
            and not values.get("trip_priced", offer.trip_priced)):
        raise HTTPException(422, "请核对并确认用车售价为元/趟。")
    if "total_quantity" in values:
        _check_total(day, values["total_quantity"], offer.reserved_quantity + offer.confirmed_quantity)
    for name, value in values.items():
        setattr(offer, name, value)
    await flush(db, "报价已被修改，请刷新后重试。")
    return await get_offer_day(db, product, offer)


def _check_total(day: date, total: int | None, committed: int) -> None:
    if committed > (total or 0):
        raise HTTPException(409, {
            "message": "投放数量不能低于已预占与已确认的数量之和，请先处理订单或提高投放数量。",
            "dates": [day.isoformat()],
            "committed": committed,
            "requested": total,
        })


async def batch_offers(db: AsyncSession, product: Product, data: OfferBatch) -> OfferBatchResult:
    if product.type == "vehicle" and data.status == "available" and not data.trip_priced:
        raise HTTPException(422, "请核对并确认用车售价为元/趟。")
    days = offer_days(data.start_date, data.end_date)
    existing = (await db.scalars(select(PriceOffer).where(
        PriceOffer.product_id == product.id,
        PriceOffer.service_date.between(data.start_date, data.end_date),
    ).order_by(PriceOffer.service_date).with_for_update())).all()
    by_day = {row.service_date: row for row in existing}
    if by_day and not data.overwrite:
        raise _date_conflict(sorted(by_day))

    for day in days:
        offer = by_day.get(day)
        if offer is None:
            offer = PriceOffer(product_id=product.id, service_date=day, total_quantity=data.total_quantity)
            db.add(offer)
        elif data.total_quantity is not None:
            _check_total(day, data.total_quantity, offer.reserved_quantity + offer.confirmed_quantity)
            offer.total_quantity = data.total_quantity
        offer.cost_fen = data.cost_fen
        offer.sale_fen = data.sale_fen
        offer.status = data.status
        if product.type == "vehicle":
            offer.trip_priced = data.trip_priced
    await flush(db, "报价已被修改，批量填价未写入。请刷新日期预览后重试。")
    return OfferBatchResult(created=len(days) - len(by_day), updated=len(by_day))
