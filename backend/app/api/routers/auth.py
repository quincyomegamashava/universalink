from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, enforce_rate_limit
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_api_key,
    verify_password,
)
from app.core.constants import UserRole
from app.models import RefreshToken, User
from app.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserOut
from app.services.bootstrap import record_login
from fastapi import Request

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, request: Request, db: DbSession) -> TokenPair:
    await enforce_rate_limit(request, f"login:{body.email.lower()}", limit=20)
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")

    access = create_access_token(str(user.id), user.role)
    refresh = create_refresh_token(str(user.id), user.role)
    payload = decode_token(refresh)
    settings = get_settings()
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=payload["jti"],
            token_hash=hash_api_key(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await record_login(db, user)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(body: RefreshRequest, db: DbSession) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token type")
    jti = payload.get("jti")
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    stored = result.scalar_one_or_none()
    if stored is None or stored.revoked or stored.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or expired")
    user_result = await db.execute(select(User).where(User.id == UUID(payload["sub"])))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")

    stored.revoked = True
    access = create_access_token(str(user.id), user.role)
    new_refresh = create_refresh_token(str(user.id), user.role)
    new_payload = decode_token(new_refresh)
    settings = get_settings()
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=new_payload["jti"],
            token_hash=hash_api_key(new_refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.commit()
    return TokenPair(access_token=access, refresh_token=new_refresh)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbSession) -> User:
    settings = get_settings()
    if not settings.registration_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is disabled")
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=body.email.lower(),
        name=body.name,
        password_hash=hash_password(body.password),
        role=UserRole.USER.value,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.post("/logout")
async def logout(body: RefreshRequest, db: DbSession) -> dict[str, str]:
    try:
        payload = decode_token(body.refresh_token)
        jti = payload.get("jti")
        result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
        stored = result.scalar_one_or_none()
        if stored:
            stored.revoked = True
            await db.commit()
    except Exception:  # noqa: BLE001
        pass
    return {"status": "ok"}
