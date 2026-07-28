"""Auth endpoints — register, login, token refresh."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
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


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user and return a JWT token."""
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

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with username + password, return JWT token."""
    user = await get_user_by_username(db, body.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
    )
