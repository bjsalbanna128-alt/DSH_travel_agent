"""Protected recommendation editing and the authenticated homepage feed."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.api.deps import CurrentOperator, CurrentUserId, DbSession, WriteDbSession, write_session
from app.schemas.admin_resources import ResourcePage
from app.schemas.itinerary_templates import RevisionRequest, Visibility
from app.schemas.recommendations import (
    ReaderRecommendation, RecommendationDetail, RecommendationDraft, SaveRecommendationDraft,
)
from app.services import recommendations
from app.services.recommendation_images import read_cover_upload

admin_router = APIRouter(prefix="/recommendations")
reader_router = APIRouter(prefix="/v1/recommendations", tags=["recommendations"])


@admin_router.get("", response_model=ResourcePage[RecommendationDetail])
async def list_drafts(
    db: DbSession, title: Annotated[str, Query(max_length=40)] = "",
    place: Annotated[str, Query(max_length=100)] = "", visibility: Visibility | None = None,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return await recommendations.list_drafts(
        db, title=title.strip(), place=place.strip(), visibility=visibility,
        offset=(page - 1) * page_size, limit=page_size,
    )


@admin_router.post("", response_model=RecommendationDetail, status_code=201)
async def create_draft(body: RecommendationDraft, operator: CurrentOperator, db: WriteDbSession):
    return await recommendations.create_draft(db, body, operator.id)


@admin_router.get("/{recommendation_id}", response_model=RecommendationDetail)
async def get_draft(recommendation_id: str, db: DbSession):
    return await recommendations.get_draft(db, recommendation_id)


@admin_router.put("/{recommendation_id}/draft", response_model=RecommendationDetail)
async def save_draft(recommendation_id: str, body: SaveRecommendationDraft, operator: CurrentOperator, db: WriteDbSession):
    draft = RecommendationDraft.model_validate(body.model_dump(exclude={"expected_revision"}))
    return await recommendations.save_draft(db, recommendation_id, body.expected_revision, draft, operator.id)


@admin_router.put("/{recommendation_id}/draft/cover", response_model=RecommendationDetail)
async def upload_cover(
    recommendation_id: str, request: Request, operator: CurrentOperator, db: DbSession,
    expected_revision: Annotated[int, Query(ge=1)],
):
    cover = await read_cover_upload(request)
    await write_session(db)
    return await recommendations.replace_cover(db, recommendation_id, expected_revision, cover, operator.id)


@admin_router.get("/{recommendation_id}/draft/cover")
async def draft_cover(recommendation_id: str, db: DbSession) -> Response:
    return await recommendations.draft_cover(db, recommendation_id)


@admin_router.post("/{recommendation_id}/publish", response_model=RecommendationDetail)
async def publish(recommendation_id: str, body: RevisionRequest, operator: CurrentOperator, db: WriteDbSession):
    return await recommendations.publish(db, recommendation_id, body.expected_revision, operator.id)


@admin_router.post("/{recommendation_id}/unpublish", response_model=RecommendationDetail)
async def unpublish(recommendation_id: str, body: RevisionRequest, operator: CurrentOperator, db: WriteDbSession):
    return await recommendations.unpublish(db, recommendation_id, body.expected_revision, operator.id)


@reader_router.get("", response_model=list[ReaderRecommendation])
async def list_published(response: Response, db: DbSession, _account: CurrentUserId):
    response.headers.update(recommendations.NO_STORE)
    return await recommendations.list_published(db)


@reader_router.get("/{recommendation_id}/versions/{version}/cover")
async def published_cover(recommendation_id: str, version: int, db: DbSession, _account: CurrentUserId) -> Response:
    return await recommendations.published_cover(db, recommendation_id, version)
