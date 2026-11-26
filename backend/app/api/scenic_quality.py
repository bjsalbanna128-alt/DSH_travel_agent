from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentOperator, DbSession, WriteDbSession
from app.api.support import Page, no_store
from app.schemas.admin_resources import ResourcePage
from app.schemas.scenic_quality import (
    QualityDetail, QualityResult, QualityRule, QualitySummary, RestrictionKind, RestrictionVisibility,
    SaveScenicRule, ScenicEntry, ScenicRule,
)
from app.schemas.support import ExpectedRevision
from app.services import planning_quality, scenic_restrictions

router = APIRouter(prefix="/ai", tags=["ai-operations"], dependencies=[Depends(no_store)])


@router.get("/scenic-restrictions", response_model=ResourcePage[ScenicEntry])
async def list_restrictions(
    db: DbSession, page: Page, city: Annotated[str, Query(max_length=100)] = "",
    name: Annotated[str, Query(max_length=160)] = "", kind: RestrictionKind | None = None,
    visibility: RestrictionVisibility | None = None,
):
    return await scenic_restrictions.list_rules(
        db, city=city, name=name, kind=kind, visibility=visibility, limit=page.limit, offset=page.offset,
    )


@router.post("/scenic-restrictions", response_model=ScenicEntry, status_code=201)
async def create_restriction(body: ScenicRule, account: CurrentOperator, db: WriteDbSession):
    return await scenic_restrictions.create_rule(db, body, account.id)


@router.get("/scenic-restrictions/{restriction_id}", response_model=ScenicEntry)
async def get_restriction(restriction_id: str, db: DbSession):
    return await scenic_restrictions.read_rule(db, restriction_id)


@router.put("/scenic-restrictions/{restriction_id}/draft", response_model=ScenicEntry)
async def save_restriction(restriction_id: str, body: SaveScenicRule, account: CurrentOperator, db: WriteDbSession):
    return await scenic_restrictions.save_rule(db, restriction_id, body, account.id)


@router.post("/scenic-restrictions/{restriction_id}/publish", response_model=ScenicEntry)
async def publish_restriction(restriction_id: str, body: ExpectedRevision, account: CurrentOperator, db: WriteDbSession):
    return await scenic_restrictions.publish_rule(db, restriction_id, body.expected_revision, account.id)


@router.post("/scenic-restrictions/{restriction_id}/disable", response_model=ScenicEntry)
async def disable_restriction(restriction_id: str, body: ExpectedRevision, account: CurrentOperator, db: WriteDbSession):
    return await scenic_restrictions.disable_rule(db, restriction_id, body.expected_revision, account.id)


@router.delete("/scenic-restrictions/{restriction_id}", status_code=204)
async def delete_restriction(restriction_id: str, expected_revision: Annotated[int, Query(ge=1)], db: WriteDbSession):
    await scenic_restrictions.delete_rule(db, restriction_id, expected_revision)


@router.get("/quality-reports", response_model=ResourcePage[QualitySummary])
async def list_quality_reports(db: DbSession, page: Page, status: QualityResult | None = None, rule: QualityRule | None = None):
    return await planning_quality.list_reports(db, status=status, rule=rule, limit=page.limit, offset=page.offset)


@router.get("/quality-reports/{trip_id}/{version}", response_model=QualityDetail)
async def get_quality_report(trip_id: str, version: Annotated[int, Path(ge=1)], db: DbSession):
    return await planning_quality.get_report(db, trip_id, version)
