from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import UserRole
from app.core.security import hash_password
from app.core.session import clear_session_cookies, revoke_refresh_cookie, user_from_request
from app.core.templating import templates
from app.db.session import get_db
from app.models import (
    AdminAuditLog,
    ApiKey,
    Chat,
    DocumentCollection,
    PlatformSetting,
    ToolPermission,
    UsageRecord,
    User,
)
from app.services.models_sync import sync_local_models
from app.services.ollama import ollama_client
from app.services.rate_limit import rate_limiter
from app.services.rag import rag_service
from app.db.session import engine

router = APIRouter(prefix="/admin", tags=["admin-ui"], include_in_schema=False)


async def _user_from_cookie(request: Request, db: AsyncSession) -> User | None:
    return await user_from_request(request, db, admin_only=True)


async def require_admin_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user = await _user_from_cookie(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="login",
            headers={"Location": "/login?next=/admin/"},
        )
    return user


def _redirect_login() -> RedirectResponse:
    return RedirectResponse(url="/login?next=/admin/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> Any:
    """Legacy path — shared portal owns login now."""
    user = await _user_from_cookie(request, db)
    if user:
        return RedirectResponse(url="/admin/", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/login?next=/admin/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/login")
async def login_submit() -> RedirectResponse:
    return RedirectResponse(url="/login?next=/admin/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
@router.get("/logout")
async def logout(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> RedirectResponse:
    await revoke_refresh_cookie(request, db)
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookies(response)
    return response


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    user = await _user_from_cookie(request, db)
    if user is None:
        return _redirect_login()

    users_count = await db.scalar(select(func.count(User.id)))
    keys_count = await db.scalar(select(func.count(ApiKey.id)))
    chats_count = await db.scalar(select(func.count(Chat.id)))
    usage = await db.execute(
        select(
            func.count(UsageRecord.id),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        )
    )
    total_requests, total_tokens = usage.one()

    components = []
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        components.append({"name": "postgres", "status": "ok"})
    except Exception as exc:  # noqa: BLE001
        components.append({"name": "postgres", "status": "error", "detail": str(exc)})
    components.append({"name": "redis", "status": "ok" if await rate_limiter.ping() else "error"})
    components.append({"name": "ollama", "status": "ok" if await ollama_client.health() else "error"})
    components.append({"name": "qdrant", "status": "ok" if await rag_service.health() else "error"})

    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "user": user,
            "active": "dashboard",
            "stats": {
                "users": int(users_count or 0),
                "api_keys": int(keys_count or 0),
                "chats": int(chats_count or 0),
                "requests": int(total_requests or 0),
                "tokens": int(total_tokens or 0),
            },
            "components": components,
            "flash": request.query_params.get("flash"),
        },
    )


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> Any:
    user = await _user_from_cookie(request, db)
    if user is None:
        return _redirect_login()
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "user": user,
            "active": "users",
            "users": result.scalars().all(),
            "error": request.query_params.get("error"),
            "flash": request.query_params.get("flash"),
        },
    )


@router.post("/users")
async def users_create(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()] = "user",
) -> RedirectResponse:
    admin = await _user_from_cookie(request, db)
    if admin is None:
        return _redirect_login()
    existing = await db.execute(select(User).where(User.email == email.lower()))
    if existing.scalar_one_or_none():
        return RedirectResponse(url="/admin/users?error=Email+already+exists", status_code=303)
    new_user = User(
        email=email.lower(),
        name=name,
        password_hash=hash_password(password),
        role=role if role in {UserRole.ADMIN.value, UserRole.USER.value} else UserRole.USER.value,
        is_active=True,
    )
    db.add(new_user)
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="user.create",
            target_type="user",
            detail={"email": email.lower(), "role": role},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    return RedirectResponse(url="/admin/users?flash=User+created", status_code=303)


@router.post("/users/{user_id}/toggle")
async def users_toggle(
    user_id: UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    admin = await _user_from_cookie(request, db)
    if admin is None:
        return _redirect_login()
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        return RedirectResponse(url="/admin/users?error=Not+found", status_code=303)
    target.is_active = not target.is_active
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="user.toggle",
            target_type="user",
            target_id=str(target.id),
            detail={"is_active": target.is_active},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    return RedirectResponse(url="/admin/users?flash=Updated", status_code=303)


@router.get("/models", response_class=HTMLResponse)
async def models_page(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> Any:
    user = await _user_from_cookie(request, db)
    if user is None:
        return _redirect_login()
    settings = get_settings()
    models: list[dict[str, Any]] = []
    running: list[dict[str, Any]] = []
    error = None
    try:
        models = await sync_local_models(db)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    try:
        running = await ollama_client.list_running()
    except Exception:  # noqa: BLE001
        running = []
    return templates.TemplateResponse(
        request,
        "admin/models.html",
        {
            "user": user,
            "active": "models",
            "models": models,
            "running": running,
            "keep_alive": settings.ollama_keep_alive,
            "default_chat_model": settings.default_chat_model,
            "embedding_model": settings.embedding_model,
            "error": error or request.query_params.get("error"),
            "flash": request.query_params.get("flash"),
        },
    )


@router.post("/models/refresh")
async def models_refresh(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> RedirectResponse:
    admin = await _user_from_cookie(request, db)
    if admin is None:
        return _redirect_login()
    try:
        models = await sync_local_models(db)
        db.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                action="model.sync",
                target_type="model",
                target_id="local",
                detail={"count": len(models)},
                ip_address=request.client.host if request.client else None,
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=f"/admin/models?error={exc}", status_code=303)
    return RedirectResponse(url="/admin/models?flash=Synced+local+models", status_code=303)


def _models_redirect(*, error: str | None = None, flash: str | None = None) -> RedirectResponse:
    if error:
        return RedirectResponse(url=f"/admin/models?error={quote(error, safe='')}", status_code=303)
    return RedirectResponse(url=f"/admin/models?flash={quote(flash or 'Done', safe='')}", status_code=303)


@router.post("/models/warmup")
async def models_warmup(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()],
) -> RedirectResponse:
    admin = await _user_from_cookie(request, db)
    if admin is None:
        return _redirect_login()
    settings = get_settings()
    requested = name.strip()
    target = requested
    note = ""
    try:
        # "Warm default" should not 400 when DEFAULT_CHAT_MODEL is not pulled yet
        if requested == settings.default_chat_model:
            picked = await ollama_client.pick_chat_model(requested)
            if not picked:
                return _models_redirect(
                    error=(
                        f"No chat model installed. Pull '{settings.default_chat_model}' "
                        "or another chat model first."
                    )
                )
            if picked != requested:
                note = f" (default '{requested}' missing; used '{picked}')"
            target = picked
        await ollama_client.warmup(target)
        db.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                action="model.warmup",
                target_type="model",
                target_id=target,
                detail={"requested": requested},
                ip_address=request.client.host if request.client else None,
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        return _models_redirect(error=str(exc))
    return _models_redirect(flash=f"Warmed {target}{note}")


@router.post("/models/warmup-all")
async def models_warmup_all(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> RedirectResponse:
    admin = await _user_from_cookie(request, db)
    if admin is None:
        return _redirect_login()
    settings = get_settings()
    warmed: list[str] = []
    notes: list[str] = []
    try:
        chat = await ollama_client.pick_chat_model(settings.default_chat_model)
        if not chat:
            return _models_redirect(
                error=(
                    f"No chat model installed. Pull '{settings.default_chat_model}' "
                    "(or any chat model) first."
                )
            )
        if chat != settings.default_chat_model:
            notes.append(f"default '{settings.default_chat_model}' missing; warmed '{chat}'")
        await ollama_client.warmup(chat, embedding=False)
        warmed.append(chat)

        embed = (settings.embedding_model or "").strip()
        if embed:
            embed_resolved = await ollama_client.resolve_installed(embed)
            if embed_resolved:
                await ollama_client.warmup(embed_resolved, embedding=True)
                warmed.append(embed_resolved)
            else:
                notes.append(f"skipped embeddings '{embed}' (not installed)")

        db.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                action="model.warmup",
                target_type="model",
                target_id="chat+embeddings",
                detail={"models": warmed, "notes": notes},
                ip_address=request.client.host if request.client else None,
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        return _models_redirect(error=str(exc))
    flash = "Warmed " + ", ".join(warmed)
    if notes:
        flash += " — " + "; ".join(notes)
    return _models_redirect(flash=flash)


@router.post("/models/pull")
async def models_pull(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()],
) -> RedirectResponse:
    admin = await _user_from_cookie(request, db)
    if admin is None:
        return _redirect_login()
    try:
        await ollama_client.pull_model(name)
        await sync_local_models(db)
        db.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                action="model.pull",
                target_type="model",
                target_id=name,
                detail={},
                ip_address=request.client.host if request.client else None,
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=f"/admin/models?error={exc}", status_code=303)
    return RedirectResponse(url="/admin/models?flash=Model+installed", status_code=303)


@router.post("/models/delete")
async def models_delete(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()],
) -> RedirectResponse:
    admin = await _user_from_cookie(request, db)
    if admin is None:
        return _redirect_login()
    try:
        await ollama_client.delete_model(name)
        db.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                action="model.delete",
                target_type="model",
                target_id=name,
                detail={},
                ip_address=request.client.host if request.client else None,
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=f"/admin/models?error={exc}", status_code=303)
    return RedirectResponse(url="/admin/models?flash=Model+deleted", status_code=303)


@router.get("/usage", response_class=HTMLResponse)
async def usage_page(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> Any:
    user = await _user_from_cookie(request, db)
    if user is None:
        return _redirect_login()
    result = await db.execute(select(UsageRecord).order_by(UsageRecord.created_at.desc()).limit(100))
    return templates.TemplateResponse(
        request,
        "admin/usage.html",
        {"user": user, "active": "usage", "rows": result.scalars().all()},
    )


@router.get("/rag", response_class=HTMLResponse)
async def rag_page(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> Any:
    user = await _user_from_cookie(request, db)
    if user is None:
        return _redirect_login()
    result = await db.execute(select(DocumentCollection).order_by(DocumentCollection.created_at.desc()))
    return templates.TemplateResponse(
        request,
        "admin/rag.html",
        {"user": user, "active": "rag", "collections": result.scalars().all()},
    )


@router.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> Any:
    user = await _user_from_cookie(request, db)
    if user is None:
        return _redirect_login()
    result = await db.execute(select(ToolPermission).order_by(ToolPermission.tool_name, ToolPermission.role))
    return templates.TemplateResponse(
        request,
        "admin/tools.html",
        {"user": user, "active": "tools", "tools": result.scalars().all(), "flash": request.query_params.get("flash")},
    )


@router.post("/tools/{tool_name}/{role}/toggle")
async def tools_toggle(
    tool_name: str,
    role: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    admin = await _user_from_cookie(request, db)
    if admin is None:
        return _redirect_login()
    result = await db.execute(
        select(ToolPermission).where(ToolPermission.tool_name == tool_name, ToolPermission.role == role)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return RedirectResponse(url="/admin/tools?flash=Not+found", status_code=303)
    row.enabled = not row.enabled
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="tool.toggle",
            target_type="tool",
            target_id=f"{tool_name}:{role}",
            detail={"enabled": row.enabled},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    return RedirectResponse(url="/admin/tools?flash=Updated", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> Any:
    user = await _user_from_cookie(request, db)
    if user is None:
        return _redirect_login()
    result = await db.execute(select(PlatformSetting).order_by(PlatformSetting.key))
    return templates.TemplateResponse(
        request,
        "admin/settings.html",
        {
            "user": user,
            "active": "settings",
            "settings": result.scalars().all(),
            "flash": request.query_params.get("flash"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/settings")
async def settings_save(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    key: Annotated[str, Form()],
    value_json: Annotated[str, Form()],
) -> RedirectResponse:
    import json

    admin = await _user_from_cookie(request, db)
    if admin is None:
        return _redirect_login()
    try:
        value = json.loads(value_json)
    except json.JSONDecodeError:
        return RedirectResponse(url="/admin/settings?error=Invalid+JSON", status_code=303)
    result = await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        db.add(PlatformSetting(key=key, value=value))
    else:
        row.value = value
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="settings.upsert",
            target_type="setting",
            target_id=key,
            detail={"value": value},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    return RedirectResponse(url="/admin/settings?flash=Saved", status_code=303)


@router.get("/health", response_class=HTMLResponse)
async def health_page(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> Any:
    user = await _user_from_cookie(request, db)
    if user is None:
        return _redirect_login()
    components = []
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        components.append({"name": "postgres", "status": "ok"})
    except Exception as exc:  # noqa: BLE001
        components.append({"name": "postgres", "status": "error", "detail": str(exc)})
    components.append({"name": "redis", "status": "ok" if await rate_limiter.ping() else "error"})
    components.append({"name": "ollama", "status": "ok" if await ollama_client.health() else "error"})
    components.append({"name": "qdrant", "status": "ok" if await rag_service.health() else "error"})
    overall = "ok" if all(c["status"] == "ok" for c in components) else "degraded"
    return templates.TemplateResponse(
        request,
        "admin/health.html",
        {"user": user, "active": "health", "overall": overall, "components": components},
    )
