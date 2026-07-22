"""Shared browser session cookies for platform portal + admin console.

One login grants access to chat (via NGINX trusted headers → Open WebUI)
and, for admins, the Jinja admin console.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_api_key,
    safe_decode_token,
)
from app.models import RefreshToken, User

COOKIE_ACCESS = "platform_access_token"
COOKIE_REFRESH = "platform_refresh_token"

# Legacy admin cookie names (cleared on logout / migrated on read)
LEGACY_ACCESS = "admin_access_token"
LEGACY_REFRESH = "admin_refresh_token"


async def user_from_request(request: Request, db: AsyncSession, *, admin_only: bool = False) -> User | None:
    token = request.cookies.get(COOKIE_ACCESS) or request.cookies.get(LEGACY_ACCESS)
    if not token:
        return None
    payload = safe_decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    try:
        uid = UUID(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if admin_only and user.role != "admin":
        return None
    return user


async def issue_session(db: AsyncSession, user: User) -> tuple[str, str]:
    access = create_access_token(str(user.id), user.role)
    refresh = create_refresh_token(str(user.id), user.role)
    payload = decode_token(refresh)
    settings = get_settings()
    user.last_login_at = datetime.now(UTC)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=payload["jti"],
            token_hash=hash_api_key(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    await db.commit()
    return access, refresh


def set_session_cookies(response: Response, access: str, refresh: str) -> None:
    settings = get_settings()
    secure = settings.cookies_secure
    response.set_cookie(
        COOKIE_ACCESS,
        access,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        COOKIE_REFRESH,
        refresh,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    secure = get_settings().cookies_secure
    for name in (COOKIE_ACCESS, COOKIE_REFRESH, LEGACY_ACCESS, LEGACY_REFRESH):
        response.delete_cookie(name, path="/", secure=secure, samesite="lax")


async def revoke_refresh_cookie(request: Request, db: AsyncSession) -> None:
    refresh = request.cookies.get(COOKIE_REFRESH) or request.cookies.get(LEGACY_REFRESH)
    if not refresh:
        return
    payload = safe_decode_token(refresh)
    if not payload or not payload.get("jti"):
        return
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    stored = result.scalar_one_or_none()
    if stored:
        stored.revoked = True
        await db.commit()


def safe_next_url(next_url: str | None, default: str = "/") -> str:
    """Only allow same-origin relative redirects."""
    if not next_url:
        return default
    next_url = next_url.strip()
    if not next_url.startswith("/") or next_url.startswith("//"):
        return default
    return next_url


def redirect_with_session(url: str, access: str, refresh: str) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=303)
    set_session_cookies(response, access, refresh)
    return response


def webui_role(platform_role: str) -> str:
    """Map platform roles to Open WebUI trusted-header roles."""
    return "admin" if platform_role == "admin" else "user"


def identity_headers(user: User) -> dict[str, str]:
    return {
        "X-User-Email": user.email,
        "X-User-Name": user.name,
        "X-User-Role": webui_role(user.role),
    }
