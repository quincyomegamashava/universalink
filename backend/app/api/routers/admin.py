from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession
from app.models import (
    AdminAuditLog,
    ApiKey,
    Chat,
    Message,
    ModelRegistry,
    PlatformSetting,
    ToolPermission,
    UsageRecord,
    User,
)
from app.schemas import (
    HealthComponent,
    HealthOut,
    SettingOut,
    SettingUpsert,
    ToolPermissionOut,
    ToolPermissionUpdate,
    UsageSummary,
)
from app.services.models_sync import sync_local_models
from app.services.ollama import ollama_client
from app.services.rate_limit import rate_limiter
from app.services.rag import rag_service
from app.db.session import engine

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/health", response_model=HealthOut)
async def admin_health(_: AdminUser) -> HealthOut:
    components: list[HealthComponent] = []
    # Postgres
    try:
        async with engine.connect() as conn:
            await conn.execute(select(1))
        components.append(HealthComponent(name="postgres", status="ok"))
    except Exception as exc:  # noqa: BLE001
        components.append(HealthComponent(name="postgres", status="error", detail=str(exc)))

    components.append(
        HealthComponent(name="redis", status="ok" if await rate_limiter.ping() else "error")
    )
    components.append(
        HealthComponent(name="ollama", status="ok" if await ollama_client.health() else "error")
    )
    components.append(
        HealthComponent(name="qdrant", status="ok" if await rag_service.health() else "error")
    )
    overall = "ok" if all(c.status == "ok" for c in components) else "degraded"
    return HealthOut(status=overall, components=components)


@router.get("/usage/summary", response_model=UsageSummary)
async def usage_summary(_: AdminUser, db: DbSession) -> UsageSummary:
    result = await db.execute(
        select(
            func.count(UsageRecord.id),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
            func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
        )
    )
    total_requests, total_tokens, prompt_tokens, completion_tokens = result.one()
    return UsageSummary(
        total_requests=int(total_requests or 0),
        total_tokens=int(total_tokens or 0),
        prompt_tokens=int(prompt_tokens or 0),
        completion_tokens=int(completion_tokens or 0),
    )


@router.get("/usage/recent")
async def usage_recent(_: AdminUser, db: DbSession, limit: int = 100) -> list[dict[str, Any]]:
    result = await db.execute(select(UsageRecord).order_by(UsageRecord.created_at.desc()).limit(min(limit, 500)))
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "user_id": str(r.user_id) if r.user_id else None,
            "api_key_id": str(r.api_key_id) if r.api_key_id else None,
            "endpoint": r.endpoint,
            "model": r.model,
            "total_tokens": r.total_tokens,
            "latency_ms": r.latency_ms,
            "status_code": r.status_code,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/chats")
async def admin_list_chats(_: AdminUser, db: DbSession, limit: int = 100) -> list[dict[str, Any]]:
    result = await db.execute(select(Chat).order_by(Chat.updated_at.desc()).limit(min(limit, 500)))
    chats = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "user_id": str(c.user_id),
            "title": c.title,
            "model": c.model,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in chats
    ]


@router.get("/chats/{chat_id}/messages")
async def admin_chat_messages(chat_id: UUID, admin: AdminUser, db: DbSession, request: Request) -> list[dict[str, Any]]:
    result = await db.execute(select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.asc()))
    messages = result.scalars().all()
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="chat.view",
            target_type="chat",
            target_id=str(chat_id),
            detail={},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "model": m.model,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.get("/models")
async def admin_models(_: AdminUser, db: DbSession) -> dict[str, Any]:
    inventory = await sync_local_models(db)
    reg = await db.execute(select(ModelRegistry))
    registry = list(reg.scalars().all())
    return {
        "models": inventory,
        "registry": [
            {
                "name": r.name,
                "display_name": r.display_name,
                "is_allowed": r.is_allowed,
                "is_default": r.is_default,
                "size_bytes": r.size_bytes,
            }
            for r in registry
        ],
    }


@router.post("/models/sync")
async def admin_sync_models(admin: AdminUser, db: DbSession, request: Request) -> dict[str, Any]:
    inventory = await sync_local_models(db)
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="model.sync",
            target_type="model",
            target_id="local",
            detail={"count": len(inventory)},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    return {"status": "ok", "count": len(inventory), "models": inventory}


@router.post("/models/pull")
async def admin_pull_model(payload: dict[str, str], admin: AdminUser, db: DbSession, request: Request) -> dict[str, Any]:
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    result = await ollama_client.pull_model(name)
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
    return {"status": "ok", "result": result}


@router.delete("/models/{name}")
async def admin_delete_model(name: str, admin: AdminUser, db: DbSession, request: Request) -> dict[str, str]:
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
    return {"status": "deleted"}


@router.get("/settings", response_model=list[SettingOut])
async def list_settings(_: AdminUser, db: DbSession) -> list[PlatformSetting]:
    result = await db.execute(select(PlatformSetting).order_by(PlatformSetting.key))
    return list(result.scalars().all())


@router.put("/settings", response_model=SettingOut)
async def upsert_setting(body: SettingUpsert, admin: AdminUser, db: DbSession, request: Request) -> PlatformSetting:
    result = await db.execute(select(PlatformSetting).where(PlatformSetting.key == body.key))
    row = result.scalar_one_or_none()
    if row is None:
        row = PlatformSetting(key=body.key, value=body.value, description=body.description)
        db.add(row)
    else:
        row.value = body.value
        if body.description is not None:
            row.description = body.description
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="settings.upsert",
            target_type="setting",
            target_id=body.key,
            detail={"value": body.value},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/tools", response_model=list[ToolPermissionOut])
async def list_tools(_: AdminUser, db: DbSession) -> list[ToolPermission]:
    result = await db.execute(select(ToolPermission).order_by(ToolPermission.tool_name, ToolPermission.role))
    return list(result.scalars().all())


@router.patch("/tools/{tool_name}/{role}", response_model=ToolPermissionOut)
async def update_tool(
    tool_name: str,
    role: str,
    body: ToolPermissionUpdate,
    admin: AdminUser,
    db: DbSession,
    request: Request,
) -> ToolPermission:
    result = await db.execute(
        select(ToolPermission).where(ToolPermission.tool_name == tool_name, ToolPermission.role == role)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool permission not found")
    row.enabled = body.enabled
    if body.config is not None:
        row.config = body.config
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="tool.update",
            target_type="tool",
            target_id=f"{tool_name}:{role}",
            detail={"enabled": body.enabled},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/audit")
async def audit_logs(_: AdminUser, db: DbSession, limit: int = 100) -> list[dict[str, Any]]:
    result = await db.execute(select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(min(limit, 500)))
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "admin_user_id": str(r.admin_user_id) if r.admin_user_id else None,
            "action": r.action,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "detail": r.detail,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/stats")
async def admin_stats(_: AdminUser, db: DbSession) -> dict[str, int]:
    users = await db.scalar(select(func.count(User.id)))
    keys = await db.scalar(select(func.count(ApiKey.id)))
    chats = await db.scalar(select(func.count(Chat.id)))
    return {"users": int(users or 0), "api_keys": int(keys or 0), "chats": int(chats or 0)}
