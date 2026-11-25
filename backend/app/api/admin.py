"""Operator endpoints, protected as a group when mounted on the application."""

from fastapi import APIRouter

from app.api.auth import AccountResponse
from app.api.deps import CurrentOperator

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/session", response_model=AccountResponse)
async def admin_session(account: CurrentOperator):
    return AccountResponse.from_account(account)
