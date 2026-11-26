"""Content layer: CRUD, product binding and vector synchronisation.

The vector store only holds published content; sellability is joined at query time
from `place_content_products` + `products` + `price_offers`.
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.content_models import PlaceContent, PlaceContentProduct
from app.db.resource_models import PriceOffer, Product, Supplier
from app.schemas.contents import (
    BindProducts, ContentCreate, ContentListPage, ContentPatch, ContentResponse, SyncResult,
)

PUBLISH_REQUIRED = {
    "city": "所在城市", "name": "名称", "description": "介绍",
    "lat": "纬度", "lng": "经度",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def content_document(row: PlaceContent) -> str:
    """Plain-text document that gets embedded."""
    parts: list[str] = []
    who = "、".join(row.suitable_for or [])
    tags = "、".join(row.tags or [])
    highlights = "、".join(row.highlights or [])
    if row.kind == "attraction":
        head = f"{row.name}是{row.city}的{row.category or '热门'}类景点。{row.description}"
        parts.append(head)
        metrics = []
        if row.rating is not None:
            metrics.append(f"评分{row.rating}/5")
        if row.visit_duration_hours:
            metrics.append(f"建议游玩{row.visit_duration_hours}小时")
        if row.opening_hours:
            metrics.append(f"开放时间{row.opening_hours}")
        if metrics:
            parts.append("，".join(metrics) + "。")
    else:
        hint = f"，{row.landmark_hint}" if row.landmark_hint else ""
        parts.append(f"{row.name}是{row.city}的{row.star_rating or ''}星级酒店{hint}。{row.description}")
        if row.rating is not None:
            parts.append(f"评分{row.rating}/5。")
    if who:
        parts.append(f"适合：{who}。")
    if tags:
        parts.append(f"标签：{tags}。")
    if highlights:
        parts.append(f"亮点：{highlights}。")
    return "".join(parts).strip()


def content_metadata(row: PlaceContent) -> dict:
    """Scalar metadata only; sellability is never stored here."""
    return {
        "name": row.name,
        "city": row.city,
        "kind": row.kind,
        "category": row.category or "",
        "rating": float(row.rating or 0),
        "visit_duration": float(row.visit_duration_hours or 0),
        "ticket_price_hint": float(row.ticket_price_hint_cny or 0),
        "opening_hours": row.opening_hours or "",
        "landmark_hint": row.landmark_hint or "",
        "lat": float(row.lat or 0),
        "lng": float(row.lng or 0),
        "tags": ",".join(row.tags or []),
        "suitable_for": ",".join(row.suitable_for or []),
    }


async def _bindings(db: AsyncSession, content_ids: list[str]) -> dict[str, list[Product]]:
    if not content_ids:
        return {}
    rows = (await db.execute(
        select(PlaceContentProduct.content_id, Product)
        .join(Product, Product.id == PlaceContentProduct.product_id)
        .where(PlaceContentProduct.content_id.in_(content_ids))
        .order_by(Product.name)
    )).all()
    grouped: dict[str, list[Product]] = {}
    for content_id, product in rows:
        grouped.setdefault(content_id, []).append(product)
    return grouped


def _response(row: PlaceContent, products: list[Product] | None = None) -> ContentResponse:
    response = ContentResponse.model_validate(row)
    response.products = [
        {"id": product.id, "name": product.name, "type": product.type, "status": product.status}
        for product in products or []
    ]
    return response


async def get_content(db: AsyncSession, content_id: str) -> ContentResponse:
    row = await db.get(PlaceContent, content_id)
    if row is None:
        raise HTTPException(404, "内容不存在")
    products = (await _bindings(db, [row.id])).get(row.id, [])
    return _response(row, products)


async def list_contents(
    db: AsyncSession, *, kind: str | None, city: str, status: str | None, keyword: str,
    offset: int, limit: int,
) -> ContentListPage:
    filters = []
    if kind:
        filters.append(PlaceContent.kind == kind)
    if city.strip():
        filters.append(PlaceContent.city == city.strip())
    if status:
        filters.append(PlaceContent.status == status)
    if keyword.strip():
        filters.append(PlaceContent.name.icontains(keyword.strip(), autoescape=True))
    total = await db.scalar(select(func.count()).select_from(PlaceContent).where(*filters))
    rows = (await db.scalars(
        select(PlaceContent).where(*filters)
        .order_by(PlaceContent.city, PlaceContent.name)
        .offset(offset).limit(limit)
    )).all()
    bindings = await _bindings(db, [row.id for row in rows])
    return ContentListPage(
        items=[_response(row, bindings.get(row.id, [])) for row in rows], total=total or 0,
    )


async def create_content(db: AsyncSession, data: ContentCreate, actor_id: str) -> ContentResponse:
    row = PlaceContent(**data.model_dump(), source="manual", status="draft",
                        created_by=actor_id, updated_by=actor_id)
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as error:
        raise HTTPException(409, "该城市下已存在同名内容，请先编辑已有条目。") from error
    return _response(row)


async def update_content(
    db: AsyncSession, content_id: str, patch: ContentPatch, actor_id: str,
) -> ContentResponse:
    row = await db.get(PlaceContent, content_id)
    if row is None:
        raise HTTPException(404, "内容不存在")
    for name, value in patch.model_dump(exclude_unset=True).items():
        setattr(row, name, value)
    row.updated_by = actor_id
    row.updated_at = _now()
    try:
        await db.flush()
    except IntegrityError as error:
        raise HTTPException(409, "该城市下已存在同名内容，请先编辑已有条目。") from error
    return await get_content(db, content_id)


async def publish_content(db: AsyncSession, content_id: str, actor_id: str) -> ContentResponse:
    row = await db.get(PlaceContent, content_id)
    if row is None:
        raise HTTPException(404, "内容不存在")
    missing = [label for field, label in PUBLISH_REQUIRED.items()
               if getattr(row, field) in (None, "")]
    if missing:
        raise HTTPException(422, {
            "message": f"发布前需要补全：{'、'.join(missing)}。",
            "missing": missing,
        })
    row.status = "published"
    row.updated_by = actor_id
    row.updated_at = _now()
    await db.flush()
    await _sync_quietly(db)
    return await get_content(db, content_id)


async def unpublish_content(db: AsyncSession, content_id: str, actor_id: str) -> ContentResponse:
    row = await db.get(PlaceContent, content_id)
    if row is None:
        raise HTTPException(404, "内容不存在")
    row.status = "unpublished"
    row.updated_by = actor_id
    row.updated_at = _now()
    await db.flush()
    await _sync_quietly(db)
    return await get_content(db, content_id)


async def delete_content(db: AsyncSession, content_id: str) -> None:
    row = await db.get(PlaceContent, content_id)
    if row is None:
        raise HTTPException(404, "内容不存在")
    bound = await db.scalar(
        select(PlaceContentProduct.content_id).where(PlaceContentProduct.content_id == content_id).limit(1)
    )
    if bound:
        raise HTTPException(409, "该内容仍绑定商品，请先解除绑定再删除。")
    await db.delete(row)
    await db.flush()


async def bind_products(
    db: AsyncSession, content_id: str, data: BindProducts, actor_id: str,
) -> ContentResponse:
    row = await db.get(PlaceContent, content_id)
    if row is None:
        raise HTTPException(404, "内容不存在")
    wanted = list(dict.fromkeys(data.product_ids))
    if wanted:
        found = set((await db.scalars(select(Product.id).where(Product.id.in_(wanted)))).all())
        missing = [product_id for product_id in wanted if product_id not in found]
        if missing:
            raise HTTPException(422, {"message": "以下商品不存在。", "product_ids": missing})
    await db.execute(delete(PlaceContentProduct).where(PlaceContentProduct.content_id == content_id))
    for product_id in wanted:
        db.add(PlaceContentProduct(content_id=content_id, product_id=product_id))
    row.updated_by = actor_id
    row.updated_at = _now()
    await db.flush()
    return await get_content(db, content_id)


async def _sync_quietly(db: AsyncSession) -> None:
    """发布/下架后顺手同步向量；同步失败不阻断发布，由运营手动重试。"""
    import logging

    try:
        await sync_vectors(db)
    except Exception:  # pragma: no cover - 依赖外部向量库
        logging.getLogger(__name__).warning("向量同步失败，可手动重试", exc_info=True)


async def sync_vectors(db: AsyncSession, *, rebuild: bool = False) -> SyncResult:
    """Push published content into ChromaDB; idempotent per content id."""
    from app.services.chroma_store import get_chroma_store

    store = get_chroma_store()
    result = SyncResult()
    for kind in ("attraction", "hotel"):
        rows = (await db.scalars(select(PlaceContent).where(
            PlaceContent.kind == kind, PlaceContent.status == "published",
        ))).all()
        desired = {row.id: row for row in rows}
        existing = set(store.content_ids(kind))
        removals = existing if rebuild else existing - set(desired)
        if removals:
            store.delete_content_ids(kind, sorted(removals))
            result.removed += len(removals)
        payload = [
            {"id": row.id, "document": content_document(row), "metadata": content_metadata(row)}
            for row in desired.values()
        ]
        if payload:
            store.replace_content(kind, payload)
        result.added += len(set(desired) - existing)
        result.updated += len(set(desired) & existing)
    return result


async def sellable_products(
    db: AsyncSession, content_ids: list[str], service_date,
) -> dict[str, dict]:
    """Cheapest sellable product per content on a given day."""
    if not content_ids:
        return {}
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
            PriceOffer.service_date == service_date,
            PriceOffer.total_quantity.is_not(None),
        )
    )).all() if service_date is not None else []

    best: dict[str, dict] = {}
    for content_id, product_id, offer in rows:
        remaining = offer.total_quantity - offer.reserved_quantity - offer.confirmed_quantity
        if remaining <= 0:
            continue
        candidate = {
            "product_id": product_id, "price_fen": offer.sale_fen,
            "remaining": remaining, "sellable": True,
        }
        current = best.get(content_id)
        if current is None or candidate["price_fen"] < current["price_fen"]:
            best[content_id] = candidate
    return best
