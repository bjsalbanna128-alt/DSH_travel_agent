"""Turn the Beijing seed places into sellable inventory (suppliers, products, offers).

Idempotent: existing suppliers, products, offers and bindings are skipped.

Usage: python -m scripts.seed_beijing_inventory
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db import database
from app.db.content_models import PlaceContent, PlaceContentProduct
from app.db.resource_models import PriceOffer, Product, Supplier

from scripts.import_seed_contents import attraction_rows, hotel_rows

HOTEL_SUPPLIER = "北京酒店试点供应商"
TICKET_SUPPLIER = "北京票务试点供应商"
OFFER_DAYS = 90
HOTEL_STOCK = 5
TICKET_STOCK = 200


async def _supplier(db, name: str, kind: str) -> Supplier:
    supplier = await db.scalar(select(Supplier).where(Supplier.name == name))
    if supplier is None:
        supplier = Supplier(name=name, settlement_name=name, kind=kind, status="active")
        db.add(supplier)
        await db.flush()
    return supplier


async def _product(db, supplier_id: str, name: str, kind: str, city: str,
                   attributes: dict, poi: dict) -> tuple[Product, bool]:
    product = await db.scalar(select(Product).where(
        Product.supplier_id == supplier_id, Product.name == name,
    ))
    if product is not None:
        return product, False
    product = Product(
        supplier_id=supplier_id, name=name, type=kind, city=city,
        attributes=attributes, poi=poi, status="on_shelf",
    )
    db.add(product)
    await db.flush()
    return product, True


async def _offers(db, product: Product, start: date, sale_fen: int, cost_fen: int, total: int) -> int:
    existing = set((await db.scalars(select(PriceOffer.service_date).where(
        PriceOffer.product_id == product.id,
    ))).all())
    created = 0
    for offset in range(OFFER_DAYS):
        day = start + timedelta(days=offset)
        if day in existing:
            continue
        db.add(PriceOffer(
            product_id=product.id, service_date=day, cost_fen=cost_fen, sale_fen=sale_fen,
            status="available", total_quantity=total, reserved_quantity=0, confirmed_quantity=0,
        ))
        created += 1
    return created


async def _bind(db, city: str, name: str, product: Product) -> bool:
    content = await db.scalar(select(PlaceContent).where(
        PlaceContent.city == city, PlaceContent.name == name,
    ))
    if content is None:
        return False
    exists = await db.get(PlaceContentProduct, (content.id, product.id))
    if exists is not None:
        return False
    db.add(PlaceContentProduct(content_id=content.id, product_id=product.id))
    return True


async def main() -> None:
    await database.init_db()
    start = date.today() + timedelta(days=1)
    stats = {"products": 0, "offers": 0, "bindings": 0, "free_attractions": 0}
    async with database.async_session() as db:
        hotel_supplier = await _supplier(db, HOTEL_SUPPLIER, "hotel")
        ticket_supplier = await _supplier(db, TICKET_SUPPLIER, "ticket")

        for index, hotel in enumerate(hotel_rows("北京"), start=1):
            product, created = await _product(
                db, hotel_supplier.id, f"{hotel['name']} · 标准大床房", "hotel_room", "北京",
                {"room_name": "标准大床房", "occupancy": 2, "breakfast": "不含早"},
                {"source": "seed", "id": f"bj-hotel-{index}", "name": hotel["name"], "city": "北京", "type": "hotel"},
            )
            stats["products"] += int(created)
            sale = int(round((hotel["ticket_price_hint_cny"] or 0) * 100))
            stats["offers"] += await _offers(db, product, start, sale, int(sale * 0.7), HOTEL_STOCK)
            stats["bindings"] += int(await _bind(db, "北京", hotel["name"], product))

        for index, attraction in enumerate(attraction_rows("北京"), start=1):
            price = attraction["ticket_price_hint_cny"] or 0
            if price <= 0:
                # Free sights stay content-only: they validate the "免费 · 无需预订" rule.
                stats["free_attractions"] += 1
                continue
            product, created = await _product(
                db, ticket_supplier.id, f"{attraction['name']} · 成人票", "attraction_ticket", "北京",
                {"ticket_name": "成人票", "audience": "成人"},
                {"source": "seed", "id": f"bj-ticket-{index}", "name": attraction["name"], "city": "北京", "type": "attraction"},
            )
            stats["products"] += int(created)
            sale = int(round(price * 100))
            stats["offers"] += await _offers(db, product, start, sale, int(sale * 0.6), TICKET_STOCK)
            stats["bindings"] += int(await _bind(db, "北京", attraction["name"], product))

        await db.commit()
    print(
        f"[BeijingInventory] 新建商品 {stats['products']} 个，报价 {stats['offers']} 条，"
        f"绑定 {stats['bindings']} 条，免费景点 {stats['free_attractions']} 个（不建商品）"
    )


if __name__ == "__main__":
    asyncio.run(main())

