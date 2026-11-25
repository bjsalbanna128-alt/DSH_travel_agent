"""FastAPI dependencies for authentication."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session, get_db
from app.db.models import User, UserRole
from app.services.auth_service import decode_access_token, get_user_by_id

security = HTTPBearer(auto_error=False)


async def _authenticate_account(token: str) -> User | None:
    user_id = decode_access_token(token)
    if not user_id:
        return None
    async with async_session() as db:
        return await get_user_by_id(db, user_id)


async def authenticate_user(token: str) -> str | None:
    """Return the ID of an existing account with a valid token."""
    account = await _authenticate_account(token)
    return account.id if account is not None else None


async def get_current_account(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> User:
    """Require a valid JWT Bearer token for a business endpoint."""
    account = await _authenticate_account(credentials.credentials) if credentials else None
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请登录后使用旅游服务",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return account


CurrentAccount = Annotated[User, Depends(get_current_account)]


async def get_current_user(account: CurrentAccount) -> str:
    return account.id


CurrentUserId = Annotated[str, Depends(get_current_user)]


async def require_operator(account: CurrentAccount) -> User:
    if account.role != UserRole.OPERATOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要运营身份")
    return account


CurrentOperator = Annotated[User, Depends(require_operator)]

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def write_session(db: DbSession) -> AsyncSession:
    # SQLite ignores row locks. Reserve the write transaction before reading dependencies.
    if db.get_bind().dialect.name == "sqlite":
        await db.execute(text("BEGIN IMMEDIATE"))
    return db


WriteDbSession = Annotated[AsyncSession, Depends(write_session)]
