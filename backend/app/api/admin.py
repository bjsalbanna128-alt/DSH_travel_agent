"""Operator endpoints, protected as a group when mounted on the application."""

from fastapi import APIRouter, Depends

from app.api.admin_resources import router as resource_router
from app.api.admin_trips import router as trip_router
from app.api.fleet import router as fleet_router
from app.api.ai_dialog import router as dialog_router
from app.api.auth import AccountResponse
from app.api.contents import router as content_router
from app.api.fulfillment import router as fulfillment_router
from app.api.deps import CurrentOperator, DbSession
from app.api.itinerary_templates import admin_router as template_router
from app.api.membership import admin_router as membership_router
from app.api.orders import admin_router as order_admin_router
from app.api.recommendations import admin_router as recommendation_router
from app.api.recommendation_delivery import router as recommendation_delivery_router
from app.api.scenic_quality import router as scenic_quality_router
from app.api.support import admin_router as support_router, no_store
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import load_dashboard

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/session", response_model=AccountResponse)
async def admin_session(account: CurrentOperator):
    return AccountResponse.from_account(account)


@router.get("/dashboard", response_model=DashboardResponse, dependencies=[Depends(no_store)])
async def dashboard(account: CurrentOperator, db: DbSession):
    return await load_dashboard(db, account)


router.include_router(resource_router)
router.include_router(fleet_router)
router.include_router(trip_router)
router.include_router(content_router)
router.include_router(template_router)
router.include_router(recommendation_router)
router.include_router(support_router)
router.include_router(membership_router)
router.include_router(order_admin_router)
router.include_router(fulfillment_router)
router.include_router(dialog_router)
router.include_router(recommendation_delivery_router)
router.include_router(scenic_quality_router)

