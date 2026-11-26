"""Operator routes for the content layer (attractions and hotels)."""

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentOperator, DbSession as DB, WriteDbSession as WriteDB
from app.api.support import Page
from app.schemas.contents import (
    BindProducts, ContentCreate, ContentListPage, ContentPatch, ContentResponse, ContentStatus,
    SyncResult,
)
from app.services import contents

router = APIRouter(prefix="/contents")


@router.get("", response_model=ContentListPage)
async def list_contents(
    db: DB, page: Page,
    kind: str | None = Query(None, pattern="^(attraction|hotel)$"),
    city: str = Query("", max_length=100),
    status: ContentStatus | None = None,
    keyword: str = Query("", max_length=160),
):
    return await contents.list_contents(
        db, kind=kind, city=city, status=status, keyword=keyword,
        offset=page.offset, limit=page.limit,
    )


@router.post("", response_model=ContentResponse, status_code=201)
async def create_content(data: ContentCreate, db: WriteDB, operator: CurrentOperator):
    return await contents.create_content(db, data, operator.id)


@router.post("/sync-vectors", response_model=SyncResult)
async def sync_vectors(db: WriteDB, rebuild: bool = False):
    result = await contents.process_vector_job(db, force=True, rebuild=rebuild)
    if result is None:
        await db.commit()
        raise HTTPException(503, "向量同步暂时失败，已保留待重试任务。")
    return result


@router.get("/vector-status")
async def vector_status(db: DB):
    return await contents.vector_status(db)


@router.get("/{content_id}", response_model=ContentResponse)
async def content_detail(content_id: str, db: DB):
    return await contents.get_content(db, content_id)


@router.patch("/{content_id}", response_model=ContentResponse)
async def update_content(content_id: str, data: ContentPatch, db: WriteDB, operator: CurrentOperator):
    return await contents.update_content(db, content_id, data, operator.id)


@router.post("/{content_id}/publish", response_model=ContentResponse)
async def publish_content(content_id: str, db: WriteDB, operator: CurrentOperator):
    return await contents.publish_content(db, content_id, operator.id)


@router.post("/{content_id}/unpublish", response_model=ContentResponse)
async def unpublish_content(content_id: str, db: WriteDB, operator: CurrentOperator):
    return await contents.unpublish_content(db, content_id, operator.id)


@router.put("/{content_id}/products", response_model=ContentResponse)
async def bind_products(content_id: str, data: BindProducts, db: WriteDB, operator: CurrentOperator):
    return await contents.bind_products(db, content_id, data, operator.id)


@router.delete("/{content_id}", status_code=204)
async def delete_content(content_id: str, db: WriteDB):
    await contents.delete_content(db, content_id)
