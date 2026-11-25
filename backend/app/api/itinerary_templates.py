"""Operator template management and the authenticated publication feed."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentOperator, CurrentUserId, DbSession, WriteDbSession
from app.schemas.admin_resources import ResourcePage
from app.schemas.itinerary_templates import (
    MAX_DAYS,
    ReaderTemplateDetail,
    ReaderTemplateSummary,
    RevisionRequest,
    SaveDraft,
    TemplateDetail,
    TemplateDraft,
    TemplateSummary,
    Visibility,
)
from app.services import itinerary_templates as templates

admin_router = APIRouter(prefix="/itinerary-templates")
reader_router = APIRouter(prefix="/v1/itinerary-templates", tags=["itinerary templates"])
TitleFilter = Annotated[str, Query(max_length=160)]
DestinationFilter = Annotated[str, Query(max_length=100)]
Page = Annotated[int, Query(ge=1, le=1_000_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@admin_router.get("", response_model=ResourcePage[TemplateSummary])
async def list_working_templates(
    db: DbSession, title: TitleFilter = "", destination: DestinationFilter = "",
    visibility: Visibility | None = None, page: Page = 1, page_size: PageSize = 20,
):
    return await templates.list_drafts(
        db, title=title.strip(), destination=destination.strip(), visibility=visibility,
        offset=(page - 1) * page_size, limit=page_size,
    )


@admin_router.post("", response_model=TemplateDetail, status_code=201)
async def create_template(draft: TemplateDraft, operator: CurrentOperator, db: WriteDbSession):
    return await templates.create_draft(db, draft, operator.id)


@admin_router.get("/{template_id}", response_model=TemplateDetail)
async def working_template(template_id: str, db: DbSession):
    return await templates.get_draft(db, template_id)


@admin_router.put("/{template_id}/draft", response_model=TemplateDetail)
async def update_template(template_id: str, body: SaveDraft, operator: CurrentOperator, db: WriteDbSession):
    return await templates.save_draft(db, template_id, body.expected_revision, body.draft, operator.id)


@admin_router.post("/{template_id}/publish", response_model=TemplateDetail)
async def publish_template(template_id: str, body: RevisionRequest, operator: CurrentOperator, db: WriteDbSession):
    return await templates.publish_draft(db, template_id, body.expected_revision, operator.id)


@admin_router.post("/{template_id}/unpublish", response_model=TemplateDetail)
async def unpublish_template(template_id: str, body: RevisionRequest, operator: CurrentOperator, db: WriteDbSession):
    return await templates.unpublish_template(db, template_id, body.expected_revision, operator.id)


@reader_router.get("", response_model=ResourcePage[ReaderTemplateSummary])
async def list_published_templates(
    response: Response, db: DbSession, _account: CurrentUserId, title: TitleFilter = "",
    destination: DestinationFilter = "", days: Annotated[int | None, Query(ge=1, le=MAX_DAYS)] = None,
    page: Page = 1, page_size: PageSize = 20,
):
    response.headers["Cache-Control"] = "no-store"
    return await templates.list_published(
        db, title=title.strip(), destination=destination.strip(), days_count=days,
        offset=(page - 1) * page_size, limit=page_size,
    )


@reader_router.get("/{template_id}", response_model=ReaderTemplateDetail)
async def published_template(template_id: str, response: Response, db: DbSession, _account: CurrentUserId):
    response.headers["Cache-Control"] = "no-store"
    return await templates.get_published(db, template_id)
