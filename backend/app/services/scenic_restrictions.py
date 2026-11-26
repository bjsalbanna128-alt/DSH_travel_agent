import logging
import unicodedata

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db import database
from app.db.scenic_models import ScenicRestriction, ScenicRestrictionVersion
from app.db.support_models import utc_now
from app.schemas.admin_resources import ResourcePage
from app.schemas.scenic_quality import ScenicEntry, ScenicRule

logger = logging.getLogger(__name__)

LATEST = (
    (ScenicRestrictionVersion.restriction_id == ScenicRestriction.id)
    & (ScenicRestrictionVersion.version == ScenicRestriction.published_version)
)


def name_key(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def city_key(value: str) -> str:
    return name_key(value).removesuffix("市")


def _describe(row, version) -> ScenicEntry:
    return ScenicEntry(
        **row.draft, id=row.id, revision=row.revision, published_version=row.published_version,
        published_revision=version.draft_revision if version else None,
        has_unpublished_changes=version is None or row.draft != version.detail,
        visibility="published" if row.active else "inactive" if row.published_version else "draft",
        updated_by=row.updated_by, updated_at=row.updated_at,
    )


async def _get(db, restriction_id, *, expected=None):
    row = await db.get(ScenicRestriction, restriction_id, with_for_update=expected is not None)
    if row is None:
        raise HTTPException(404, "景区限制不存在")
    if expected is not None and row.revision != expected:
        raise HTTPException(409, "景区限制已被修改，请刷新后重试")
    version = await db.get(ScenicRestrictionVersion, (row.id, row.published_version)) if row.published_version else None
    return row, version


async def read_rule(db, restriction_id):
    return _describe(*await _get(db, restriction_id))


async def list_rules(db, *, city, name, kind, visibility, offset, limit):
    filters = []
    if city:
        filters.append(ScenicRestriction.city_key == city_key(city))
    if name:
        filters.append(ScenicRestriction.name_key.contains(name_key(name), autoescape=True))
    if kind:
        filters.append(ScenicRestriction.draft["kind"].as_string() == kind)
    if visibility == "draft":
        filters.append(ScenicRestriction.published_version == 0)
    elif visibility == "inactive":
        filters.extend((ScenicRestriction.published_version > 0, ScenicRestriction.active.is_(False)))
    elif visibility == "published":
        filters.append(ScenicRestriction.active.is_(True))
    total = await db.scalar(select(func.count()).select_from(ScenicRestriction).where(*filters))
    rows = await db.execute(select(ScenicRestriction, ScenicRestrictionVersion).outerjoin(
        ScenicRestrictionVersion, LATEST,
    ).where(*filters).order_by(ScenicRestriction.updated_at.desc(), ScenicRestriction.id)
        .offset(offset).limit(limit))
    return ResourcePage[ScenicEntry](items=[_describe(*row) for row in rows], total=total or 0)


def _apply(row, draft, actor):
    row.draft = draft.model_dump(mode="json")
    row.city_key = city_key(draft.poi.city)
    row.name_key = name_key(draft.poi.name)
    row.updated_by, row.updated_at = actor, utc_now()


async def create_rule(db, draft, actor):
    row = ScenicRestriction(revision=1, published_version=0, active=False)
    _apply(row, draft, actor)
    db.add(row)
    await db.flush()
    return _describe(row, None)


async def save_rule(db, restriction_id, draft, actor):
    row, version = await _get(db, restriction_id, expected=draft.expected_revision)
    _apply(row, ScenicRule.model_validate(draft.model_dump(exclude={"expected_revision"})), actor)
    row.revision += 1
    return _describe(row, version)


async def publish_rule(db, restriction_id, expected, actor):
    row, version = await _get(db, restriction_id, expected=expected)
    if version is not None and row.draft == version.detail:
        if row.active:
            raise HTTPException(409, "当前限制已发布")
    else:
        draft = ScenicRule.model_validate(row.draft)
        row.published_version += 1
        version = ScenicRestrictionVersion(
            restriction_id=row.id, version=row.published_version, draft_revision=row.revision,
            detail=draft.model_dump(mode="json"), city_key=row.city_key, published_by=actor, published_at=utc_now(),
        )
        db.add(version)
    row.active = True
    row.revision += 1
    row.updated_by, row.updated_at = actor, utc_now()
    return _describe(row, version)


async def disable_rule(db, restriction_id, expected, actor):
    row, version = await _get(db, restriction_id, expected=expected)
    if not row.active:
        raise HTTPException(409, "只有已发布的限制可停用")
    row.active = False
    row.revision += 1
    row.updated_by, row.updated_at = actor, utc_now()
    return _describe(row, version)


async def delete_rule(db, restriction_id, expected):
    row, version = await _get(db, restriction_id, expected=expected)
    if version is not None:
        raise HTTPException(409, "已有发布历史，请停用该限制")
    await db.delete(row)


async def _select_snapshot(db, destination):
    rows = await db.scalars(select(ScenicRestrictionVersion).join(ScenicRestriction, LATEST).where(
        ScenicRestriction.active.is_(True), ScenicRestrictionVersion.city_key == city_key(destination),
    ).order_by(ScenicRestrictionVersion.restriction_id))
    return {
        "available": True,
        "rules": [{**row.detail, "id": row.restriction_id, "version": row.version} for row in rows],
    }


async def restriction_snapshot(destination, db=None):
    try:
        if db is not None:
            async with db.begin_nested():
                return await _select_snapshot(db, destination)
        async with database.async_session() as session:
            return await _select_snapshot(session, destination)
    except SQLAlchemyError:
        logger.warning("Scenic restriction lookup unavailable", exc_info=True)
        return {"available": False, "rules": []}
