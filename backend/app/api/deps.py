"""FastAPI dependencies for authentication."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.database import async_session
from app.services.auth_service import decode_access_token, get_user_by_id

security = HTTPBearer(auto_error=False)


async def authenticate_user(token: str) -> str | None:
    """Return the ID of an existing account with a valid token."""
    user_id = decode_access_token(token)
    if not user_id:
        return None
    async with async_session() as db:
        user = await get_user_by_id(db, user_id)
        return user.id if user else None


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> str:
    """Require a valid JWT Bearer token for a business endpoint."""
    user_id = await authenticate_user(credentials.credentials) if credentials else None
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请登录后使用旅游服务",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


CurrentUserId = Annotated[str, Depends(get_current_user)]
