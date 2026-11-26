"""Resource management routes mounted on the operator router."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, select
from app.api.deps import DbSession as DB, WriteDbSession as WriteDB
from app.db.resource_models import Product, Supplier
from app.schemas.admin_resources import (
    MAX_OFFER_DAYS,
    OfferBatch,
    OfferBatchResult,
    OfferCreate,
    OfferDay,
    OfferPage,
    OfferPatch,
    OfferStatus,
    PoiKind,
    PoiSearchResponse,
    ProductCreate,
    ProductPatch,
    ProductResponse,
    ProductStatus,
    ProductType,
    ResourcePage,
    ServiceDate,
    SupplierCreate,
    SupplierKind,
    SupplierPatch,
    SupplierResponse,
    SupplierStatus,
)
from app.services import admin_resources as resources
from app.services.admin_pois import find_binding_candidates

router = APIRouter()
Page = Annotated[int, Query(ge=1, le=1_000_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]
OfferPageSize = Annotated[int, Query(ge=1, le=MAX_OFFER_DAYS)]


@router.get("/suppliers", response_model=ResourcePage[SupplierResponse])
async def list_suppliers(
    db: DB, name: Annotated[str, Query(max_length=160)] = "",
    status: SupplierStatus | None = None, page: Page = 1, page_size: PageSize = 20,
    kind: SupplierKind | None = None,
):
    filters = []
    if name.strip():
        filters.append(Supplier.name.icontains(name.strip(), autoescape=True))
    if status is not None:
        filters.append(Supplier.status == status)
    if kind is not None:
        filters.append(Supplier.kind == kind)
    total = await db.scalar(select(func.count()).select_from(Supplier).where(*filters))
    suppliers = await db.scalars(select(Supplier).where(*filters).order_by(
        Supplier.name, Supplier.id,
    ).offset((page - 1) * page_size).limit(page_size))
    return ResourcePage[SupplierResponse](
        items=[SupplierResponse.model_validate(row) for row in suppliers], total=total or 0,
    )


@router.post("/suppliers", response_model=SupplierResponse, status_code=201)
async def create_supplier(data: SupplierCreate, db: WriteDB):
    supplier = Supplier(**data.model_dump())
    db.add(supplier)
    await db.flush()
    return supplier


@router.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def supplier_details(supplier_id: str, db: DB):
    return await resources.get_supplier(db, supplier_id)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(supplier_id: str, data: SupplierPatch, db: WriteDB):
    supplier = await resources.get_supplier(db, supplier_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    from app.db.fleet_models import FleetModel
    from app.services.scenic_restrictions import city_key

    if supplier.kind == "vehicle_fleet" and (
        changes.get("kind", supplier.kind) != supplier.kind
        or (supplier.fleet_city and city_key(changes.get("fleet_city", supplier.fleet_city)) != city_key(supplier.fleet_city))
    ) and await db.scalar(select(FleetModel.code).where(FleetModel.supplier_id == supplier_id).limit(1)):
        raise HTTPException(409, "车队已有车型台账，不能变更供应商分类或服务城市。")
    for name, value in changes.items():
        setattr(supplier, name, value)
    await db.flush()
    return supplier


@router.delete("/suppliers/{supplier_id}", status_code=204)
async def remove_supplier(supplier_id: str, db: WriteDB):
    await resources.delete_supplier(db, await resources.get_supplier(db, supplier_id, lock=True))
    return Response(status_code=204)


@router.get("/products", response_model=ResourcePage[ProductResponse])
async def list_products(
    db: DB, name: Annotated[str, Query(max_length=160)] = "", supplier_id: str | None = None,
    type: ProductType | None = None, status: ProductStatus | None = None,
    page: Page = 1, page_size: PageSize = 20,
):
    filters = []
    if name.strip():
        filters.append(Product.name.icontains(name.strip(), autoescape=True))
    if supplier_id is not None:
        filters.append(Product.supplier_id == supplier_id)
    if type is not None:
        filters.append(Product.type == type)
    if status is not None:
        filters.append(Product.status == status)
    total = await db.scalar(select(func.count()).select_from(Product).where(*filters))
    rows = await db.execute(resources.product_listing().where(*filters).order_by(
        Product.name, Product.id,
    ).offset((page - 1) * page_size).limit(page_size))
    return ResourcePage[ProductResponse](
        items=[resources.product_response(row) for row in rows], total=total or 0,
    )


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(data: ProductCreate, db: WriteDB):
    return await resources.create_product(db, data)


@router.get("/products/{product_id}", response_model=ProductResponse)
async def product_details(product_id: str, db: DB):
    return await resources.get_product_details(db, product_id)


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: str, data: ProductPatch, db: WriteDB):
    product = await resources.get_product(db, product_id, lock=True, new_supplier=data.supplier_id)
    return await resources.update_product(db, product, data)


@router.delete("/products/{product_id}", status_code=204)
async def remove_product(product_id: str, db: WriteDB):
    await resources.delete_product(db, await resources.get_product(db, product_id, lock=True))
    return Response(status_code=204)


@router.get("/pois", response_model=PoiSearchResponse)
async def list_pois(
    city: Annotated[str, Query(min_length=1, max_length=100, pattern=r"\S")],
    keyword: Annotated[str, Query(min_length=1, max_length=160, pattern=r"\S")],
    type: PoiKind,
):
    return await find_binding_candidates(city.strip(), keyword.strip(), type)


@router.get("/products/{product_id}/offers", response_model=OfferPage)
async def list_offers(
    product_id: str, db: WriteDB, start_date: ServiceDate | None = None,
    end_date: ServiceDate | None = None, status: OfferStatus | None = None,
    check_in: ServiceDate | None = None, check_out: ServiceDate | None = None,
    page: Page = 1, page_size: OfferPageSize = 20,
):
    from app.services.orders import expire_due

    product = await resources.get_product(db, product_id)
    await expire_due(db, product_ids={product_id})
    return await resources.list_offers(
        db, product, start=start_date, end=end_date, status=status,
        check_in=check_in, check_out=check_out, offset=(page - 1) * page_size, limit=page_size,
    )


@router.post("/products/{product_id}/offers", response_model=OfferDay, status_code=201)
async def create_offer(product_id: str, data: OfferCreate, db: WriteDB):
    product = await resources.get_product(db, product_id, lock=True)
    return await resources.create_offer(db, product, data)


@router.post("/products/{product_id}/offers/batch", response_model=OfferBatchResult)
async def fill_offers(product_id: str, data: OfferBatch, db: WriteDB):
    product = await resources.get_product(db, product_id, lock=True)
    return await resources.batch_offers(db, product, data)


@router.patch("/products/{product_id}/offers/{service_date}", response_model=OfferDay)
async def update_offer(product_id: str, service_date: ServiceDate, data: OfferPatch, db: WriteDB):
    product = await resources.get_product(db, product_id, lock=True)
    return await resources.update_offer(db, product, service_date, data)


@router.delete("/products/{product_id}/offers/{service_date}", status_code=204)
async def remove_offer(product_id: str, service_date: ServiceDate, db: WriteDB):
    product = await resources.get_product(db, product_id, lock=True)
    await resources.delete_offer(db, product, service_date)
    await db.flush()
    return Response(status_code=204)
