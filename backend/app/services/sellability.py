"""Attach sellability (product, price, remaining) to retrieved places.

Sellability is always read live from the database: the vector store only knows
content, never price or stock.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.content_models import PlaceContentProduct
from app.db.resource_models import PriceOffer, Product, Supplier
from app.services.contents import sellable_products


def _offer(product_id: str, price_fen: int, remaining: int | None, *, unspecified: bool) -> dict:
    return {
        "product_id": product_id,
        "price_cny": round(price_fen / 100, 2),
        "remaining": remaining,
        "sellable": True,
        "date_unspecified": unspecified,
    }


async def _cheapest_open_offer(db: AsyncSession, content_ids: list[str]) -> dict[str, dict]:
    """No travel date yet: only check that a saleable product exists."""
    rows = (await db.execute(
        select(PlaceContentProduct.content_id, Product.id, PriceOffer)
        .join(Product, Product.id == PlaceContentProduct.product_id)
        .join(Supplier, Supplier.id == Product.supplier_id)
        .join(PriceOffer, PriceOffer.product_id == Product.id)
        .where(
            PlaceContentProduct.content_id.in_(content_ids),
            Product.status == "on_shelf",
            Supplier.status == "active",
            PriceOffer.status == "available",
            PriceOffer.total_quantity.is_not(None),
        )
        .order_by(PriceOffer.sale_fen)
    )).all()
    best: dict[str, dict] = {}
    for content_id, product_id, offer in rows:
        if content_id in best:
            continue
        best[content_id] = _offer(product_id, offer.sale_fen, None, unspecified=True)
    return best


async def annotate_offers(
    db: AsyncSession, items: list[dict], *, kind: str, travel_date: date | None,
) -> list[dict]:
    """Mutate items with ``offer`` (or None) and return them."""
    content_ids = [item["content_id"] for item in items if item.get("content_id")]
    found: dict[str, dict] = {}
    if content_ids:
        found = (await sellable_products(db, content_ids, travel_date) if travel_date is not None
                 else await _cheapest_open_offer(db, content_ids))
        if travel_date is not None:
            found = {
                content_id: _offer(row["product_id"], row["price_fen"], row["remaining"], unspecified=False)
                for content_id, row in found.items()
            }
    for item in items:
        item["offer"] = found.get(item.get("content_id", "")) if item.get("content_id") else None
    return items


def sort_candidates(items: list[dict], *, anchor: dict | None = None) -> list[dict]:
    """Sellable first, then distance to anchor; keeps semantic order as tie-breaker."""
    from app.services.geo import haversine_km

    def key(item: dict) -> tuple:
        sellable = 0 if (item.get("offer") or {}).get("sellable") else 1
        distance = haversine_km(anchor, item) if anchor and item.get("location") else 0.0
        return (sellable, round(distance, 2))

    return sorted(items, key=key)
