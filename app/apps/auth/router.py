from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.auth import services
from app.apps.auth.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.apps.users.models import User
from app.apps.users.schemas import UserRead
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=201)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPair:
    user = await services.register_user(db, payload.email, payload.password, payload.full_name)
    access_token, refresh_token = await services.issue_token_pair(user, redis)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPair:
    user = await services.authenticate_user(db, payload.email, payload.password)
    access_token, refresh_token = await services.issue_token_pair(user, redis)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenPair:
    access_token, refresh_token = await services.rotate_refresh_token(db, redis, payload.refresh_token)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=204)
async def logout(payload: RefreshRequest, redis: Redis = Depends(get_redis)) -> None:
    await services.revoke_refresh_token(redis, payload.refresh_token)


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/google/login")
async def google_login(
    next: str | None = Query(default=None),
    redis: Redis = Depends(get_redis),
) -> RedirectResponse:
    redirect_url = await services.build_google_login_redirect_url(redis, next)
    return RedirectResponse(redirect_url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> RedirectResponse:
    access_token, refresh_token, next_url = await services.handle_google_callback(db, redis, code, state)
    return RedirectResponse(f"{next_url}#access_token={access_token}&refresh_token={refresh_token}")
