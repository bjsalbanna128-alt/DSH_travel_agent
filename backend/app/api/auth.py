"""Auth endpoints — register, login, token refresh."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentAccount
from app.db.database import get_db
from app.db.models import User, UserRole
from app.services.auth_service import (
    create_access_token,
    create_user,
    get_user_by_email,
    get_user_by_username,
    verify_password,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AccountResponse(BaseModel):
    user_id: str
    username: str
    role: UserRole

    @classmethod
    def from_account(cls, account: User) -> "AccountResponse":
        return cls(user_id=account.id, username=account.username, role=account.role)


class TokenResponse(AccountResponse):
    access_token: str
    token_type: str = "bearer"


def _token_response(account: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(account.id),
        user_id=account.id,
        username=account.username,
        role=account.role,
    )


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Register a new user and return a JWT token."""
    if "role" in await request.json():
        raise HTTPException(status_code=422, detail="注册时不能指定账号身份")
    if len(body.username) < 2 or len(body.username) > 50:
        raise HTTPException(status_code=400, detail="用户名长度需在 2-50 之间")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于 6 位")

    if await get_user_by_username(db, body.username):
        raise HTTPException(status_code=409, detail="用户名已被注册")
    if await get_user_by_email(db, body.email):
        raise HTTPException(status_code=409, detail="邮箱已被注册")

    user = await create_user(db, body.username, body.email, body.password)
    await db.commit()

    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with username + password, return JWT token."""
    user = await get_user_by_username(db, body.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    return _token_response(user)


@router.get("/me", response_model=AccountResponse)
async def current_account(account: CurrentAccount):
    return AccountResponse.from_account(account)
