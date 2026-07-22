from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import AdminUser, CurrentUser, DbSession, enforce_rate_limit
from app.core.security import generate_api_key, hash_api_key, hash_password
from app.models import AdminAuditLog, ApiKey, User
from app.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api", tags=["users-keys"])


@router.get("/users/me", response_model=UserOut)
async def get_me(user: CurrentUser) -> User:
    return user


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(body: ApiKeyCreate, user: CurrentUser, db: DbSession, request: Request) -> ApiKeyCreated:
    await enforce_rate_limit(request, f"user:{user.id}")
    raw = generate_api_key()
    key = ApiKey(
        user_id=user.id,
        name=body.name,
        key_prefix=raw[:12],
        key_hash=hash_api_key(raw),
        expires_at=body.expires_at,
        rate_limit_per_minute=body.rate_limit_per_minute,
        is_active=True,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return ApiKeyCreated(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        is_active=key.is_active,
        expires_at=key.expires_at,
        rate_limit_per_minute=key.rate_limit_per_minute,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        raw_key=raw,
    )


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(user: CurrentUser, db: DbSession) -> list[ApiKey]:
    result = await db.execute(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()))
    return list(result.scalars().all())


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke_api_key(key_id: UUID, user: CurrentUser, db: DbSession) -> Response:
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    key.is_active = False
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Admin user management ---


@router.get("/admin/users", response_model=list[UserOut])
async def admin_list_users(_: AdminUser, db: DbSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


@router.post("/admin/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def admin_create_user(body: UserCreate, admin: AdminUser, db: DbSession, request: Request) -> User:
    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    user = User(
        email=body.email.lower(),
        name=body.name,
        password_hash=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="user.create",
            target_type="user",
            detail={"email": user.email, "role": user.role},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/admin/users/{user_id}", response_model=UserOut)
async def admin_update_user(
    user_id: UUID, body: UserUpdate, admin: AdminUser, db: DbSession, request: Request
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if body.name is not None:
        user.name = body.name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="user.update",
            target_type="user",
            target_id=str(user.id),
            detail=body.model_dump(exclude_none=True, exclude={"password"}),
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/admin/api-keys", response_model=list[ApiKeyOut])
async def admin_list_api_keys(_: AdminUser, db: DbSession) -> list[ApiKey]:
    result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return list(result.scalars().all())


@router.delete("/admin/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def admin_revoke_api_key(key_id: UUID, admin: AdminUser, db: DbSession, request: Request) -> Response:
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    key.is_active = False
    db.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="api_key.revoke",
            target_type="api_key",
            target_id=str(key.id),
            detail={},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
