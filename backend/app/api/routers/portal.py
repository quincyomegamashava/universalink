"""Platform portal: shared login/register + NGINX auth_request verify."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.branding import app_display_name
from app.core.config import get_settings
from app.core.constants import UserRole
from app.core.security import hash_password, verify_password
from app.core.session import (
    clear_session_cookies,
    identity_headers,
    issue_session,
    revoke_refresh_cookie,
    safe_next_url,
    redirect_with_session,
    user_from_request,
)
from app.core.templating import templates
from app.db.session import get_db
from app.models import User

router = APIRouter(tags=["portal"], include_in_schema=False)

DEFAULT_AFTER_LOGIN = "/home"


@router.get("/auth/verify")
async def auth_verify(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Internal endpoint for NGINX auth_request. Returns identity headers on success."""
    user = await user_from_request(request, db)
    if user is None:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)
    headers = identity_headers(user)
    return Response(status_code=status.HTTP_200_OK, headers=headers)


@router.get("/home", response_class=HTMLResponse)
async def home_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    user = await user_from_request(request, db)
    if user is None:
        return RedirectResponse(url="/login?next=/home", status_code=303)
    return templates.TemplateResponse(
        request,
        "portal/home.html",
        {
            "user": user,
            "app_name": app_display_name(),
            "active": "home",
            "flash": request.query_params.get("flash"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    settings = get_settings()
    user = await user_from_request(request, db)
    next_url = safe_next_url(request.query_params.get("next"), DEFAULT_AFTER_LOGIN)
    if user:
        if next_url.startswith("/admin") and user.role != UserRole.ADMIN.value:
            next_url = DEFAULT_AFTER_LOGIN
        return RedirectResponse(url=next_url, status_code=303)
    return templates.TemplateResponse(
        request,
        "portal/login.html",
        {
            "error": None,
            "flash": request.query_params.get("flash"),
            "email": "",
            "next": next_url,
            "registration_enabled": settings.registration_enabled,
            "app_name": app_display_name(),
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = DEFAULT_AFTER_LOGIN,
) -> Any:
    settings = get_settings()
    next_url = safe_next_url(next, DEFAULT_AFTER_LOGIN)
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash) or not user.is_active:
        return templates.TemplateResponse(
            request,
            "portal/login.html",
            {
                "error": "Invalid email or password",
                "flash": None,
                "email": email,
                "next": next_url,
                "registration_enabled": settings.registration_enabled,
                "app_name": app_display_name(),
            },
            status_code=401,
        )

    if next_url.startswith("/admin") and user.role != UserRole.ADMIN.value:
        next_url = DEFAULT_AFTER_LOGIN
    if next_url in {"/", ""}:
        next_url = DEFAULT_AFTER_LOGIN

    access, refresh = await issue_session(db, user)
    return redirect_with_session(next_url, access, refresh)


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    settings = get_settings()
    if not settings.registration_enabled:
        return RedirectResponse(url="/login", status_code=303)
    user = await user_from_request(request, db)
    if user:
        return RedirectResponse(url=DEFAULT_AFTER_LOGIN, status_code=303)
    return templates.TemplateResponse(
        request,
        "portal/register.html",
        {
            "error": None,
            "email": "",
            "name": "",
            "app_name": app_display_name(),
        },
    )


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Any:
    settings = get_settings()
    app_name = app_display_name()
    if not settings.registration_enabled:
        return RedirectResponse(url="/login", status_code=303)

    ctx = {"error": None, "email": email, "name": name, "app_name": app_name}
    if len(password) < 8:
        ctx["error"] = "Password must be at least 8 characters"
        return templates.TemplateResponse(request, "portal/register.html", ctx, status_code=400)

    existing = await db.execute(select(User).where(User.email == email.lower()))
    if existing.scalar_one_or_none():
        ctx["error"] = "Email already registered"
        return templates.TemplateResponse(request, "portal/register.html", ctx, status_code=409)

    user = User(
        email=email.lower(),
        name=name.strip() or email.split("@")[0],
        password_hash=hash_password(password),
        role=UserRole.USER.value,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access, refresh = await issue_session(db, user)
    return redirect_with_session("/settings/api-keys", access, refresh)


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> RedirectResponse:
    await revoke_refresh_cookie(request, db)
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookies(response)
    return response
