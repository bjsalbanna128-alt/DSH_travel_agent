"""Work with recommendation drafts and expose only current published snapshots."""

from datetime import datetime, timezone

from fastapi import HTTPException, Response
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.db.recommendation_models import Recommendation, RecommendationDelivery, RecommendationImage, RecommendationVersion
from app.db.support_models import utc_now
from app.schemas.admin_resources import ResourcePage
from app.schemas.itinerary_templates import Visibility
from app.schemas.recommendations import CoverInfo, ReaderRecommendation, RecommendationDetail, RecommendationDraft
from app.services.recommendation_images import DecodedCover
from app.services.recommendation_delivery import LATEST_VERSION, eligible_at

SNAPSHOT_FIELDS = ("title", "place", "short_text", "display_order", "cover_id")
NO_STORE = {"Cache-Control": "private, no-store"}
REVISION_CONFLICT = "推荐内容已被修改，请保留当前输入，重新加载并核对后再提交。"


def _draft_cover_url(recommendation_id: str) -> str:
    return f"/api/v1/admin/recommendations/{recommendation_id}/draft/cover"


def _fields(row) -> dict:
    return {name: getattr(row, name) for name in SNAPSHOT_FIELDS}


def _describe(row: Recommendation, image: RecommendationImage | None, version: RecommendationVersion | None, *, message: str | None = None) -> RecommendationDetail:
    cover = CoverInfo(
        id=image.id, url=_draft_cover_url(row.id), mime=image.mime,
        width=image.width, height=image.height, size_bytes=image.size_bytes,
    ) if image else None
    return RecommendationDetail(
        id=row.id, title=row.title, place=row.place, short_text=row.short_text, display_order=row.display_order,
        cover=cover, visibility=row.visibility, revision=row.revision, published_version=row.published_version,
        has_unpublished_changes=version is not None and _fields(row) != _fields(version),
        updated_at=row.updated_at, message=message,
    )


def _with_cover_and_version():
    return (
        select(Recommendation, RecommendationImage, RecommendationVersion)
        .outerjoin(RecommendationImage, RecommendationImage.id == Recommendation.cover_id)
        .outerjoin(RecommendationVersion, LATEST_VERSION)
    )


async def list_drafts(db: AsyncSession, *, title: str, place: str, visibility: Visibility | None, offset: int, limit: int) -> ResourcePage[RecommendationDetail]:
    filters = []
    if title:
        filters.append(Recommendation.title.icontains(title, autoescape=True))
    if place:
        filters.append(Recommendation.place.icontains(place, autoescape=True))
    if visibility is not None:
        filters.append(Recommendation.visibility == visibility)
    total = await db.scalar(select(func.count()).select_from(Recommendation).where(*filters))
    rows = await db.execute(_with_cover_and_version().where(*filters).order_by(
        Recommendation.updated_at.desc(), Recommendation.id,
    ).offset(offset).limit(limit))
    return ResourcePage[RecommendationDetail](items=[_describe(*row) for row in rows], total=total or 0)


async def get_draft(db: AsyncSession, recommendation_id: str, *, message: str | None = None) -> RecommendationDetail:
    result = await db.execute(_with_cover_and_version().where(Recommendation.id == recommendation_id))
    row = result.one_or_none()
    if row is None:
        raise HTTPException(404, "推荐内容不存在。")
    return _describe(*row, message=message)


async def _lock(db: AsyncSession, recommendation_id: str, expected: int) -> Recommendation:
    row = await db.get(Recommendation, recommendation_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "推荐内容不存在。")
    if row.revision != expected:
        raise HTTPException(409, REVISION_CONFLICT)
    return row


async def _advance(db: AsyncSession, row: Recommendation, expected: int, operator_id: str, **changes) -> None:
    result = await db.execute(update(Recommendation).where(
        Recommendation.id == row.id, Recommendation.revision == expected,
    ).values(
        revision=expected + 1, updated_by=operator_id, updated_at=datetime.now(timezone.utc), **changes,
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, REVISION_CONFLICT)
    await db.refresh(row)


async def create_draft(db: AsyncSession, draft: RecommendationDraft, operator_id: str) -> RecommendationDetail:
    row = Recommendation(**draft.model_dump(), created_by=operator_id, updated_by=operator_id)
    db.add(row)
    await db.flush()
    return _describe(row, None, None)


async def save_draft(db: AsyncSession, recommendation_id: str, expected: int, draft: RecommendationDraft, operator_id: str) -> RecommendationDetail:
    row = await _lock(db, recommendation_id, expected)
    await _advance(db, row, expected, operator_id, **draft.model_dump())
    return await get_draft(db, recommendation_id)


async def replace_cover(db: AsyncSession, recommendation_id: str, expected: int, cover: DecodedCover, operator_id: str) -> RecommendationDetail:
    row = await _lock(db, recommendation_id, expected)
    previous_cover = row.cover_id
    image = RecommendationImage(
        content=cover.content, mime=cover.mime, width=cover.width, height=cover.height, size_bytes=len(cover.content),
    )
    db.add(image)
    await db.flush()
    await _advance(db, row, expected, operator_id, cover_id=image.id)
    if previous_cover:
        await db.execute(delete(RecommendationImage).where(
            RecommendationImage.id == previous_cover,
            ~exists().where(Recommendation.cover_id == previous_cover),
            ~exists().where(RecommendationVersion.cover_id == previous_cover),
        ))
    return await get_draft(db, recommendation_id)


async def publish(db: AsyncSession, recommendation_id: str, expected: int, operator_id: str) -> RecommendationDetail:
    row = await _lock(db, recommendation_id, expected)
    if row.visibility == "published":
        previous = await db.get(RecommendationVersion, (row.id, row.published_version))
        if previous and _fields(row) == _fields(previous):
            return await get_draft(db, recommendation_id, message="已是最新发布版本。")

    errors = [
        {"path": [name], "message": message}
        for name, value, message in (
            ("place", row.place, "请填写推荐地点。"),
            ("short_text", row.short_text, "请填写推荐短文。"),
            ("cover", row.cover_id, "请上传一张有效的封面图片。"),
        ) if not value
    ]
    if errors:
        raise HTTPException(422, {"message": "请补齐推荐内容后发布。", "errors": errors})

    version = row.published_version + 1
    await _advance(db, row, expected, operator_id, visibility="published", published_version=version)
    db.add(RecommendationVersion(
        recommendation_id=row.id, version=version, **_fields(row), published_by=operator_id, published_at=row.updated_at,
    ))
    await db.flush()
    return await get_draft(db, recommendation_id, message=f"已发布 v{version}。")


async def unpublish(db: AsyncSession, recommendation_id: str, expected: int, operator_id: str) -> RecommendationDetail:
    row = await _lock(db, recommendation_id, expected)
    if row.visibility != "published":
        raise HTTPException(409, "仅已上线的推荐内容可以下架。")
    await _advance(db, row, expected, operator_id, visibility="unpublished")
    return await get_draft(db, recommendation_id)


async def list_published(db: AsyncSession, *, at: datetime | None = None) -> list[ReaderRecommendation]:
    now = at.astimezone(timezone.utc) if at is not None else utc_now()
    versions = await db.scalars(select(RecommendationVersion).join(Recommendation, LATEST_VERSION)
        .join(RecommendationDelivery, RecommendationDelivery.recommendation_id == Recommendation.id)
        .where(Recommendation.visibility == "published", *eligible_at(now))
        .order_by(RecommendationVersion.display_order, RecommendationVersion.recommendation_id))
    return [ReaderRecommendation(
        id=row.recommendation_id, version=row.version, title=row.title, place=row.place, short_text=row.short_text,
        cover_url=f"/api/v1/recommendations/{row.recommendation_id}/versions/{row.version}/cover",
    ) for row in versions]


def _image_response(image: RecommendationImage | None) -> Response:
    if image is None:
        raise HTTPException(404, "封面不存在或不可见。", headers=NO_STORE)
    return Response(image.content, media_type=image.mime, headers={**NO_STORE, "X-Content-Type-Options": "nosniff"})


async def draft_cover(db: AsyncSession, recommendation_id: str) -> Response:
    image = await db.scalar(select(RecommendationImage).options(undefer(RecommendationImage.content))
        .join(Recommendation, Recommendation.cover_id == RecommendationImage.id)
        .where(Recommendation.id == recommendation_id))
    return _image_response(image)


async def published_cover(db: AsyncSession, recommendation_id: str, version: int) -> Response:
    image = await db.scalar(select(RecommendationImage).options(undefer(RecommendationImage.content))
        .join(RecommendationVersion, RecommendationVersion.cover_id == RecommendationImage.id)
        .join(Recommendation, LATEST_VERSION).where(
            Recommendation.id == recommendation_id, Recommendation.visibility == "published",
            RecommendationVersion.version == version,
        ))
    return _image_response(image)
