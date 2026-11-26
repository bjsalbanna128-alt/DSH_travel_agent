from fastapi import APIRouter, Depends
from pydantic import AwareDatetime

from app.api.deps import CurrentOperator, DbSession, WriteDbSession
from app.api.support import no_store
from app.schemas.recommendation_delivery import DeliveryEntry, SaveDelivery, SelectableRecommendation
from app.schemas.recommendations import ReaderRecommendation
from app.services import recommendation_delivery, recommendations

router = APIRouter(prefix="/ai/home-recommendations", tags=["ai-operations"], dependencies=[Depends(no_store)])


@router.get("", response_model=list[DeliveryEntry])
async def list_deliveries(db: DbSession):
    return await recommendation_delivery.list_deliveries(db)


@router.get("/selectable", response_model=list[SelectableRecommendation])
async def selectable(db: DbSession):
    return await recommendation_delivery.selectable(db)


@router.get("/preview", response_model=list[ReaderRecommendation])
async def preview(db: DbSession, at: AwareDatetime | None = None):
    return await recommendations.list_published(db, at=at)


@router.put("/{recommendation_id}", response_model=DeliveryEntry)
async def save(recommendation_id: str, payload: SaveDelivery, account: CurrentOperator, db: WriteDbSession):
    return await recommendation_delivery.save_delivery(db, recommendation_id, payload, account)
