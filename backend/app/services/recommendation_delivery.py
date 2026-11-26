from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, insert, literal, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import User
from app.db.recommendation_models import (
    Recommendation, RecommendationDelivery, RecommendationDeliveryMigration, RecommendationVersion,
)
from app.db.support_models import utc_now
from app.schemas.recommendation_delivery import DeliveryEntry, SelectableRecommendation

LATEST_VERSION = and_(
    RecommendationVersion.recommendation_id == Recommendation.id,
    RecommendationVersion.version == Recommendation.published_version,
)


async def seed_deliveries(db):
    marker = (sqlite_insert if db.dialect.name == "sqlite" else pg_insert)(RecommendationDeliveryMigration)
    result = await db.execute(marker.values(id=1).on_conflict_do_nothing().returning(
        RecommendationDeliveryMigration.id,
    ))
    if result.scalar_one_or_none() is None:
        return
    await db.execute(insert(RecommendationDelivery).from_select(
        ["recommendation_id", "enabled", "revision", "updated_at"],
        select(Recommendation.id, literal(True), literal(1), literal(utc_now()))
        .where(Recommendation.visibility == "published"),
    ))


def _utc(value: datetime | None):
    if value is None:
        return None
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def eligible_at(now: datetime):
    return (
        RecommendationDelivery.enabled.is_(True),
        (RecommendationDelivery.starts_at.is_(None) | (RecommendationDelivery.starts_at <= now)),
        (RecommendationDelivery.ends_at.is_(None) | (RecommendationDelivery.ends_at > now)),
    )


def _describe(row, version, delivery, operator, now):
    starts, ends = _utc(delivery.starts_at), _utc(delivery.ends_at)
    if row.visibility != "published":
        status = "content_unpublished"
    elif not delivery.enabled:
        status = "paused"
    elif starts is not None and now < starts:
        status = "scheduled"
    elif ends is not None and now >= ends:
        status = "ended"
    else:
        status = "active"
    return DeliveryEntry(
        id=row.id, title=version.title, display_order=version.display_order, enabled=delivery.enabled,
        starts_at=starts, ends_at=ends, revision=delivery.revision, updated_by=delivery.updated_by,
        operator_name=operator, updated_at=delivery.updated_at, status=status,
    )


async def list_deliveries(db):
    now = utc_now()
    rows = await db.execute(select(Recommendation, RecommendationVersion, RecommendationDelivery, User.username)
        .join(RecommendationVersion, LATEST_VERSION)
        .join(RecommendationDelivery, RecommendationDelivery.recommendation_id == Recommendation.id)
        .outerjoin(User, User.id == RecommendationDelivery.updated_by)
        .order_by(RecommendationVersion.display_order, Recommendation.id))
    return [_describe(*row, now) for row in rows]


async def selectable(db):
    rows = await db.execute(select(Recommendation.id, RecommendationVersion.title, RecommendationVersion.display_order)
        .join(RecommendationVersion, LATEST_VERSION)
        .outerjoin(RecommendationDelivery, RecommendationDelivery.recommendation_id == Recommendation.id)
        .where(Recommendation.visibility == "published", RecommendationDelivery.recommendation_id.is_(None))
        .order_by(RecommendationVersion.display_order, Recommendation.id))
    return [SelectableRecommendation(id=row.id, title=row.title, display_order=row.display_order) for row in rows]


async def save_delivery(db, recommendation_id, payload, operator):
    row = await db.get(Recommendation, recommendation_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "推荐内容不存在")
    delivery = await db.get(RecommendationDelivery, recommendation_id)
    if (delivery.revision if delivery else 0) != payload.expected_revision:
        raise HTTPException(409, "投放已被修改，请重新加载")
    if delivery is None and row.visibility != "published":
        raise HTTPException(422, "首次投放须选择已发布的内容")
    now = utc_now()
    if payload.enabled and payload.ends_at is not None and payload.ends_at <= now:
        raise HTTPException(422, "投放已到期，请先调整结束时间")
    if delivery is None:
        delivery = RecommendationDelivery(recommendation_id=row.id)
        db.add(delivery)
    delivery.revision = payload.expected_revision + 1
    delivery.enabled = payload.enabled
    delivery.starts_at = payload.starts_at
    delivery.ends_at = payload.ends_at
    delivery.updated_by = operator.id
    delivery.updated_at = now
    await db.flush()
    version = await db.get(RecommendationVersion, (row.id, row.published_version))
    return _describe(row, version, delivery, operator.username, now)
