import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.users.models import OAuthAccount, User
from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password

settings = get_settings()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

REFRESH_KEY_PREFIX = "refresh_token:"
OAUTH_STATE_KEY_PREFIX = "oauth_state:"


async def issue_token_pair(user: User, redis: Redis) -> tuple[str, str]:
    access_token = create_access_token(user.id)
    refresh_token, jti, expires_at = create_refresh_token(user.id)
    ttl_seconds = int((expires_at - datetime.now(timezone.utc)).total_seconds())
    await redis.set(f"{REFRESH_KEY_PREFIX}{jti}", str(user.id), ex=ttl_seconds)
    return access_token, refresh_token


async def register_user(db: AsyncSession, email: str, password: str, full_name: str | None) -> User:
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")

    user = User(email=email, hashed_password=hash_password(password), full_name=full_name)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or user.hashed_password is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is inactive")
    return user


async def rotate_refresh_token(db: AsyncSession, redis: Redis, refresh_token: str) -> tuple[str, str]:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")

    key = f"{REFRESH_KEY_PREFIX}{payload['jti']}"
    stored_user_id = await redis.get(key)
    if stored_user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token has been revoked or expired")

    # One-time use: revoke immediately so a stolen refresh token can't be replayed.
    await redis.delete(key)

    user = await db.get(User, uuid.UUID(stored_user_id))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    return await issue_token_pair(user, redis)


async def revoke_refresh_token(redis: Redis, refresh_token: str) -> None:
    payload = decode_token(refresh_token)
    await redis.delete(f"{REFRESH_KEY_PREFIX}{payload['jti']}")


async def build_google_login_redirect_url(redis: Redis, next_url: str | None) -> str:
    state = uuid.uuid4().hex
    await redis.set(
        f"{OAUTH_STATE_KEY_PREFIX}{state}",
        next_url or settings.frontend_url,
        ex=settings.oauth_state_ttl_seconds,
    )
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def handle_google_callback(
    db: AsyncSession, redis: Redis, code: str, state: str
) -> tuple[str, str, str]:
    state_key = f"{OAUTH_STATE_KEY_PREFIX}{state}"
    next_url = await redis.get(state_key)
    if next_url is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")
    await redis.delete(state_key)

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != 200:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Failed to exchange Google authorization code")
        google_access_token = token_response.json()["access_token"]

        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {google_access_token}"},
        )
        if userinfo_response.status_code != 200:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Failed to fetch Google user info")
        profile = userinfo_response.json()

    if not profile.get("email_verified"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google account email is not verified")

    user = await _get_or_create_google_user(db, profile)
    access_token, refresh_token = await issue_token_pair(user, redis)
    return access_token, refresh_token, next_url


async def _get_or_create_google_user(db: AsyncSession, profile: dict) -> User:
    provider_account_id = profile["sub"]

    oauth_account = await db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_account_id == provider_account_id,
        )
    )
    if oauth_account is not None:
        return await db.get(User, oauth_account.user_id)

    # No existing Google identity — link to an existing account by verified
    # email, or create a fresh one. Google has already verified this email,
    # so no password is set (the user can only sign in via Google).
    user = await db.scalar(select(User).where(User.email == profile["email"]))
    if user is None:
        user = User(email=profile["email"], full_name=profile.get("name"), hashed_password=None)
        db.add(user)
        await db.flush()

    db.add(OAuthAccount(user_id=user.id, provider="google", provider_account_id=provider_account_id))
    await db.commit()
    await db.refresh(user)
    return user
