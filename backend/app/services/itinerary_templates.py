"""Persist working drafts and atomically switch the published snapshot."""

import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, func, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.resource_models import Product, Supplier
from app.db.template_models import ItineraryTemplate, ItineraryTemplateVersion
from app.schemas.admin_resources import ResourcePage
from app.schemas.itinerary_templates import (
    ProductSnapshot,
    PublishedActivity,
    PublishedContent,
    PublishedDay,
    ReaderTemplateDetail,
    ReaderTemplateSummary,
    TemplateDetail,
    TemplateDraft,
    TemplateFieldIssue,
    TemplateSummary,
    Visibility,
)

Template = ItineraryTemplate
Version = ItineraryTemplateVersion
LATEST_VERSION = and_(Version.template_id == Template.id, Version.version == Template.published_version)
REVISION_CONFLICT = "模板已被修改，请保留当前输入，重新加载并核对后再提交。"


def _draft_values(draft: TemplateDraft) -> dict:
    body = draft.model_dump(mode="json")
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "draft": body, "draft_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "title": draft.title, "destination": draft.destination, "days_count": len(draft.days),
    }


def _activities(draft: TemplateDraft):
    for day_index, day in enumerate(draft.days):
        for activity_index, activity in enumerate(day.activities):
            yield ["days", day_index, "activities", activity_index], activity


async def _linked_products(db: AsyncSession, draft: TemplateDraft, *, lock: bool = False) -> dict:
    ids = {activity.product_id for _, activity in _activities(draft) if activity.product_id is not None}
    if not ids:
        return {}
    statement = (
        select(Product.id, Product.name, Product.type, Product.status, Supplier.status.label("supplier_status"))
        .join(Supplier, Supplier.id == Product.supplier_id).where(Product.id.in_(ids)).order_by(Product.id)
    )
    if lock:
        statement = statement.with_for_update(read=True, of=(Product, Supplier))
    return {row.id: row for row in await db.execute(statement)}


def _snapshot_product(row) -> ProductSnapshot:
    return ProductSnapshot(id=row.id, name=row.name, type=row.type)


def _product_issues(draft: TemplateDraft, rows: dict, *, publishing: bool = False) -> list[TemplateFieldIssue]:
    issues = []
    for path, activity in _activities(draft):
        if activity.product_id is None:
            continue
        product = rows.get(activity.product_id)
        if product is None:
            message = f"关联商品（{activity.product_id}）已不存在，请替换或解除关联。"
        elif publishing and product.status != "on_shelf":
            message = f"关联商品「{product.name}」已下架，请替换或解除关联。"
        elif publishing and product.supplier_status != "active":
            message = f"关联商品「{product.name}」的供应商已停用，请替换或解除关联。"
        else:
            continue
        issues.append(TemplateFieldIssue(path=[*path, "product_id"], message=message))
    return issues


def _publication_issues(draft: TemplateDraft) -> list[TemplateFieldIssue]:
    issues = []
    if not draft.destination:
        issues.append(TemplateFieldIssue(path=["destination"], message="请填写主要目的地。"))
    if not draft.days:
        issues.append(TemplateFieldIssue(path=["days"], message="请至少添加一天有效安排。"))
    for index, day in enumerate(draft.days):
        if not day.theme:
            issues.append(TemplateFieldIssue(path=["days", index, "theme"], message="请填写当日主题。"))
        if not day.activities:
            issues.append(TemplateFieldIssue(path=["days", index, "activities"], message="请至少添加一项活动。"))
    for path, activity in _activities(draft):
        if not activity.name:
            issues.append(TemplateFieldIssue(path=[*path, "name"], message="请填写活动名称。"))
        if activity.category is None:
            issues.append(TemplateFieldIssue(path=[*path, "category"], message="请选择活动类别。"))
    return issues


def _reject_issues(issues: list[TemplateFieldIssue], message: str) -> None:
    if issues:
        raise HTTPException(422, {"message": message, "errors": [issue.model_dump() for issue in issues]})


def _summary(row, published_hash: str | None) -> TemplateSummary:
    return TemplateSummary(
        id=row.id, title=row.title, destination=row.destination, days_count=row.days_count,
        visibility=row.visibility, published_version=row.published_version,
        has_unpublished_changes=published_hash is not None and row.draft_hash != published_hash,
        updated_at=row.updated_at, revision=row.revision,
    )


async def _detail(db: AsyncSession, row: Template, *, message: str | None = None) -> TemplateDetail:
    current = await db.get(Version, (row.id, row.published_version)) if row.published_version else None
    draft = TemplateDraft.model_validate(row.draft)
    products = await _linked_products(db, draft)
    return TemplateDetail(
        **_summary(row, current.draft_hash if current else None).model_dump(),
        draft=draft, linked_products=[_snapshot_product(product) for product in products.values()],
        created_by=row.created_by, updated_by=row.updated_by, created_at=row.created_at,
        published_at=current.published_at if current else None, message=message,
    )


async def list_drafts(
    db: AsyncSession, *, title: str, destination: str, visibility: Visibility | None, offset: int, limit: int,
) -> ResourcePage[TemplateSummary]:
    filters = []
    if title:
        filters.append(Template.title.icontains(title, autoescape=True))
    if destination:
        filters.append(Template.destination.icontains(destination, autoescape=True))
    if visibility is not None:
        filters.append(Template.visibility == visibility)
    total = await db.scalar(select(func.count()).select_from(Template).where(*filters))
    rows = await db.execute(
        select(
            Template.id, Template.title, Template.destination, Template.days_count, Template.visibility,
            Template.published_version, Template.updated_at, Template.revision, Template.draft_hash,
            Version.draft_hash.label("published_hash"),
        ).outerjoin(Version, LATEST_VERSION).where(*filters).order_by(
            Template.updated_at.desc(), Template.id,
        ).offset(offset).limit(limit)
    )
    return ResourcePage[TemplateSummary](items=[_summary(row, row.published_hash) for row in rows], total=total or 0)


async def _get_template(db: AsyncSession, template_id: str, *, expected: int | None = None) -> Template:
    row = await db.get(Template, template_id, with_for_update=expected is not None)
    if row is None:
        raise HTTPException(404, "行程模板不存在。")
    if expected is not None and row.revision != expected:
        raise HTTPException(409, REVISION_CONFLICT)
    return row


async def _advance(db: AsyncSession, row: Template, expected: int, actor: str, **changes) -> None:
    result = await db.execute(
        update(Template).where(Template.id == row.id, Template.revision == expected).values(
            revision=expected + 1, updated_by=actor, updated_at=datetime.now(timezone.utc), **changes,
        ).execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise HTTPException(409, REVISION_CONFLICT)
    await db.refresh(row)


async def get_draft(db: AsyncSession, template_id: str) -> TemplateDetail:
    return await _detail(db, await _get_template(db, template_id))


async def create_draft(db: AsyncSession, draft: TemplateDraft, actor: str) -> TemplateDetail:
    products = await _linked_products(db, draft, lock=True)
    _reject_issues(_product_issues(draft, products), "请核对草稿中的商品引用。")
    row = Template(**_draft_values(draft), created_by=actor, updated_by=actor)
    db.add(row)
    await db.flush()
    return await _detail(db, row)


async def save_draft(db: AsyncSession, template_id: str, expected: int, draft: TemplateDraft, actor: str) -> TemplateDetail:
    row = await _get_template(db, template_id, expected=expected)
    products = await _linked_products(db, draft, lock=True)
    _reject_issues(_product_issues(draft, products), "请核对草稿中的商品引用。")
    await _advance(db, row, expected, actor, **_draft_values(draft))
    return await _detail(db, row)


def _published_content(draft: TemplateDraft, products: dict) -> PublishedContent:
    days = [
        PublishedDay(
            day=index, theme=day.theme, notes=day.notes,
            activities=[
                PublishedActivity(
                    time=activity.time, name=activity.name, category=activity.category, description=activity.description,
                    product=_snapshot_product(products[activity.product_id]) if activity.product_id else None,
                )
                for activity in day.activities
            ],
        )
        for index, day in enumerate(draft.days, start=1)
    ]
    return PublishedContent(**draft.model_dump(exclude={"days"}), days=days)


async def publish_draft(db: AsyncSession, template_id: str, expected: int, actor: str) -> TemplateDetail:
    row = await _get_template(db, template_id, expected=expected)
    if row.visibility == "published":
        current = await db.get(Version, (row.id, row.published_version))
        if current and current.draft_hash == row.draft_hash:
            return await _detail(db, row, message="已是最新发布版本。")

    draft = TemplateDraft.model_validate(row.draft)
    products = await _linked_products(db, draft, lock=True)
    _reject_issues(
        _publication_issues(draft) + _product_issues(draft, products, publishing=True),
        "请修正以下字段后发布。",
    )
    snapshot = _published_content(draft, products)
    number = row.published_version + 1
    await _advance(db, row, expected, actor, published_version=number, visibility="published")
    db.add(Version(
        template_id=row.id, version=number, snapshot=snapshot.model_dump(mode="json"), draft_hash=row.draft_hash,
        title=snapshot.title, destination=snapshot.destination, days_count=len(snapshot.days),
        published_by=actor, published_at=row.updated_at,
    ))
    await db.flush()
    return await _detail(db, row, message=f"已发布 v{number}。")


async def unpublish_template(db: AsyncSession, template_id: str, expected: int, actor: str) -> TemplateDetail:
    row = await _get_template(db, template_id, expected=expected)
    if row.visibility != "published":
        raise HTTPException(409, "仅已上线的模板可以下架。")
    await _advance(db, row, expected, actor, visibility="unpublished")
    return await _detail(db, row)


def _readable_versions():
    return select(Version).join(Template, LATEST_VERSION).where(Template.visibility == "published")


def _reader_summary(row) -> ReaderTemplateSummary:
    return ReaderTemplateSummary(
        id=row.template_id, version=row.version, title=row.title, destination=row.destination,
        days_count=row.days_count, tags=row.snapshot["tags"], description=row.snapshot["description"],
        published_at=row.published_at,
    )


async def list_published(
    db: AsyncSession, *, title: str, destination: str, days_count: int | None, offset: int, limit: int,
) -> ResourcePage[ReaderTemplateSummary]:
    statement = _readable_versions()
    if title:
        statement = statement.where(Version.title.icontains(title, autoescape=True))
    if destination:
        statement = statement.where(Version.destination.icontains(destination, autoescape=True))
    if days_count is not None:
        statement = statement.where(Version.days_count == days_count)

    matching = statement.cte()
    page = select(matching).order_by(matching.c.published_at.desc(), matching.c.template_id).offset(offset).limit(limit).subquery()
    count = select(func.count().label("total")).select_from(matching).subquery()
    rows = (await db.execute(
        select(count.c.total, page).select_from(count).outerjoin(page, true())
        .order_by(page.c.published_at.desc(), page.c.template_id)
    )).all()
    return ResourcePage[ReaderTemplateSummary](
        items=[_reader_summary(row) for row in rows if row.template_id is not None], total=rows[0].total,
    )


async def get_published(db: AsyncSession, template_id: str) -> ReaderTemplateDetail:
    current = await db.scalar(_readable_versions().where(Version.template_id == template_id))
    if current is None:
        raise HTTPException(404, "行程模板不存在或未上线。", headers={"Cache-Control": "no-store"})
    return ReaderTemplateDetail(
        **_reader_summary(current).model_dump(), tips=current.snapshot["tips"], days=current.snapshot["days"],
    )
