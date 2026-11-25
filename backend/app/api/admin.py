"""Operator endpoints, protected as a group when mounted on the application."""

from fastapi import APIRouter

from app.api.admin_resources import router as resource_router
from app.api.auth import AccountResponse
from app.api.deps import CurrentOperator
from app.api.itinerary_templates import admin_router as template_router
from app.api.membership import admin_router as membership_router
from app.api.recommendations import admin_router as recommendation_router
from app.api.support import admin_router as support_router

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/session", response_model=AccountResponse)
async def admin_session(account: CurrentOperator):
    return AccountResponse.from_account(account)


router.include_router(resource_router)
router.include_router(template_router)
router.include_router(recommendation_router)
router.include_router(support_router)
router.include_router(membership_router)
