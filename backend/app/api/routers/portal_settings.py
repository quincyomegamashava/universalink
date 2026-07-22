"""User settings portal: API keys, password change, forgot/reset password."""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.branding import app_display_name, public_base_url
from app.core.security import (
    create_password_reset_token,
    decode_password_reset_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.core.session import user_from_request
from app.core.templating import templates
from app.db.session import get_db
from app.models import ApiKey, User
from app.services.mail import send_email, smtp_configured

logger = logging.getLogger(__name__)

router = APIRouter(tags=["portal-settings"], include_in_schema=False)


def _login_redirect(next_path: str = "/settings/api-keys") -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


async def _require_user(request: Request, db: AsyncSession) -> User | None:
    return await user_from_request(request, db)


def _ctx(user: User, **extra: Any) -> dict[str, Any]:
    return {
        "user": user,
        "app_name": app_display_name(),
        "public_url": public_base_url(),
        "flash": None,
        "error": None,
        **extra,
    }


@router.get("/settings", response_class=HTMLResponse)
async def settings_index() -> RedirectResponse:
    return RedirectResponse(url="/settings/api-keys", status_code=303)


@router.get("/settings/api-keys", response_class=HTMLResponse)
async def api_keys_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    user = await _require_user(request, db)
    if user is None:
        return _login_redirect("/settings/api-keys")
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return templates.TemplateResponse(
        request,
        "portal/settings_api_keys.html",
        _ctx(
            user,
            active="api-keys",
            keys=result.scalars().all(),
            new_key=None,
            flash=request.query_params.get("flash"),
            error=request.query_params.get("error"),
        ),
    )


@router.post("/settings/api-keys", response_class=HTMLResponse)
async def api_keys_create(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()] = "Default",
) -> Any:
    user = await _require_user(request, db)
    if user is None:
        return _login_redirect("/settings/api-keys")
    label = (name or "Default").strip()[:120] or "Default"
    raw = generate_api_key()
    key = ApiKey(
        user_id=user.id,
        name=label,
        key_prefix=raw[:12],
        key_hash=hash_api_key(raw),
        is_active=True,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return templates.TemplateResponse(
        request,
        "portal/settings_api_keys.html",
        _ctx(
            user,
            active="api-keys",
            keys=result.scalars().all(),
            new_key=raw,
            flash="API key created — copy it now; it will not be shown again.",
        ),
    )


@router.post("/settings/api-keys/{key_id}/revoke")
async def api_keys_revoke(
    key_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    user = await _require_user(request, db)
    if user is None:
        return _login_redirect("/settings/api-keys")
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    key = result.scalar_one_or_none()
    if key is None:
        return RedirectResponse(url="/settings/api-keys?error=Key+not+found", status_code=303)
    key.is_active = False
    await db.commit()
    return RedirectResponse(url="/settings/api-keys?flash=Key+revoked", status_code=303)


@router.get("/settings/password", response_class=HTMLResponse)
async def password_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    user = await _require_user(request, db)
    if user is None:
        return _login_redirect("/settings/password")
    return templates.TemplateResponse(
        request,
        "portal/settings_password.html",
        _ctx(user, active="password", flash=request.query_params.get("flash"), error=request.query_params.get("error")),
    )


@router.post("/settings/password", response_class=HTMLResponse)
async def password_change(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
) -> Any:
    user = await _require_user(request, db)
    if user is None:
        return _login_redirect("/settings/password")
    ctx = _ctx(user, active="password")
    if not verify_password(current_password, user.password_hash):
        ctx["error"] = "Current password is incorrect"
        return templates.TemplateResponse(request, "portal/settings_password.html", ctx, status_code=400)
    if len(new_password) < 8:
        ctx["error"] = "New password must be at least 8 characters"
        return templates.TemplateResponse(request, "portal/settings_password.html", ctx, status_code=400)
    if new_password != confirm_password:
        ctx["error"] = "New passwords do not match"
        return templates.TemplateResponse(request, "portal/settings_password.html", ctx, status_code=400)
    user.password_hash = hash_password(new_password)
    await db.commit()
    return RedirectResponse(url="/settings/password?flash=Password+updated", status_code=303)


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request) -> Any:
    return templates.TemplateResponse(
        request,
        "portal/forgot_password.html",
        {
            "app_name": app_display_name(),
            "error": None,
            "flash": None,
            "smtp_ready": smtp_configured(),
        },
    )


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    email: Annotated[str, Form()],
) -> Any:
    # Always show the same message (no email enumeration)
    flash = (
        "If that email exists, a reset link was sent. "
        "Check your inbox (and spam). The link expires in one hour."
    )
    result = await db.execute(select(User).where(User.email == email.lower(), User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if user and smtp_configured():
        token = create_password_reset_token(str(user.id))
        link = f"{public_base_url()}/reset-password?token={token}"
        try:
            await send_email(
                user.email,
                f"Reset your {app_display_name()} password",
                f"Reset your password using this link (expires in 1 hour):\n\n{link}\n\n"
                f"If you did not request this, ignore this email.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Password reset email failed: %s", exc)
    elif user and not smtp_configured():
        # Self-hosted without SMTP: log a one-time link for the operator
        token = create_password_reset_token(str(user.id))
        link = f"{public_base_url()}/reset-password?token={token}"
        logger.warning("Password reset for %s (SMTP not configured). Operator link: %s", user.email, link)
        flash = (
            "SMTP is not configured. Ask an admin to check backend logs for a one-time reset link, "
            "or have them set a new password in Admin → Users."
        )

    return templates.TemplateResponse(
        request,
        "portal/forgot_password.html",
        {
            "app_name": app_display_name(),
            "error": None,
            "flash": flash,
            "smtp_ready": smtp_configured(),
        },
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request) -> Any:
    token = request.query_params.get("token") or ""
    payload = decode_password_reset_token(token) if token else None
    if not payload:
        return templates.TemplateResponse(
            request,
            "portal/reset_password.html",
            {
                "app_name": app_display_name(),
                "error": "This reset link is invalid or expired.",
                "token": "",
                "valid": False,
            },
            status_code=400,
        )
    return templates.TemplateResponse(
        request,
        "portal/reset_password.html",
        {
            "app_name": app_display_name(),
            "error": None,
            "token": token,
            "valid": True,
        },
    )


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
) -> Any:
    payload = decode_password_reset_token(token)
    if not payload:
        return templates.TemplateResponse(
            request,
            "portal/reset_password.html",
            {
                "app_name": app_display_name(),
                "error": "This reset link is invalid or expired.",
                "token": "",
                "valid": False,
            },
            status_code=400,
        )
    if len(new_password) < 8 or new_password != confirm_password:
        return templates.TemplateResponse(
            request,
            "portal/reset_password.html",
            {
                "app_name": app_display_name(),
                "error": "Passwords must match and be at least 8 characters.",
                "token": token,
                "valid": True,
            },
            status_code=400,
        )
    try:
        uid = UUID(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return RedirectResponse(url="/login", status_code=303)
    result = await db.execute(select(User).where(User.id == uid, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    user.password_hash = hash_password(new_password)
    await db.commit()
    return RedirectResponse(url="/login?flash=Password+reset.+Sign+in+with+your+new+password.", status_code=303)
