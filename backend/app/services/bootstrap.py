from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import UserRole
from app.core.security import hash_password
from app.models import PlatformSetting, ToolPermission, User

logger = logging.getLogger(__name__)

DEFAULT_TOOLS = [
    "github",
    "filesystem",
    "docker",
    "terminal",
    "aws",
    "email",
    "database",
    "web_search",
    "calendar",
]


async def bootstrap_admin(session: AsyncSession) -> None:
    settings = get_settings()
    result = await session.execute(select(User).where(User.email == settings.admin_email))
    admin = result.scalar_one_or_none()
    if admin is None:
        admin = User(
            email=settings.admin_email,
            name=settings.admin_name,
            password_hash=hash_password(settings.admin_password),
            role=UserRole.ADMIN.value,
            is_active=True,
            last_login_at=None,
        )
        session.add(admin)
        logger.info("Bootstrapped admin user %s", settings.admin_email)
    else:
        logger.info("Admin user already exists: %s", settings.admin_email)

    defaults = {
        "registration_enabled": {"value": settings.registration_enabled},
        "default_model": {"value": settings.default_chat_model},
        "cors_origins": {"value": settings.cors_origin_list},
        "retention_days": {"value": 90},
    }
    for key, value in defaults.items():
        existing = await session.execute(select(PlatformSetting).where(PlatformSetting.key == key))
        if existing.scalar_one_or_none() is None:
            session.add(
                PlatformSetting(
                    key=key,
                    value=value,
                    description=f"Platform setting: {key}",
                )
            )

    for tool in DEFAULT_TOOLS:
        for role in (UserRole.ADMIN.value, UserRole.USER.value):
            existing = await session.execute(
                select(ToolPermission).where(ToolPermission.tool_name == tool, ToolPermission.role == role)
            )
            if existing.scalar_one_or_none() is None:
                session.add(
                    ToolPermission(
                        tool_name=tool,
                        role=role,
                        enabled=(role == UserRole.ADMIN.value and tool in {"web_search", "filesystem"}),
                        config={},
                    )
                )

    await session.commit()


async def record_login(session: AsyncSession, user: User) -> None:
    user.last_login_at = datetime.now(UTC)
    await session.commit()
