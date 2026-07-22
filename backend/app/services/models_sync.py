from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import ModelRegistry
from app.services.ollama import ollama_client


def _model_name(entry: dict[str, Any]) -> str:
    return str(entry.get("name") or entry.get("model") or "").strip()


async def sync_local_models(session: AsyncSession) -> list[dict[str, Any]]:
    """List Ollama models and upsert them into model_registry (no pull)."""
    settings = get_settings()
    ollama_models = await ollama_client.list_models()
    local_names: set[str] = set()
    inventory: list[dict[str, Any]] = []

    for entry in ollama_models:
        name = _model_name(entry)
        if not name:
            continue
        local_names.add(name)
        size = entry.get("size")
        modified = entry.get("modified_at") or entry.get("modified")

        existing = await session.execute(select(ModelRegistry).where(ModelRegistry.name == name))
        row = existing.scalar_one_or_none()
        if row is None:
            row = ModelRegistry(
                name=name,
                display_name=name,
                is_allowed=True,
                is_default=(name == settings.default_chat_model),
                size_bytes=int(size) if size is not None else None,
                meta={"modified_at": modified} if modified else {},
            )
            session.add(row)
        else:
            if size is not None:
                row.size_bytes = int(size)
            if modified:
                meta = dict(row.meta or {})
                meta["modified_at"] = modified
                row.meta = meta

        inventory.append(
            {
                "name": name,
                "size": size,
                "modified_at": modified,
                "digest": entry.get("digest"),
                "details": entry.get("details") or {},
                "is_allowed": row.is_allowed if row else True,
                "is_default": row.is_default if row else False,
                "display_name": row.display_name if row else name,
            }
        )

    await session.flush()

    if not local_names:
        await session.commit()
        return inventory

    # Refresh flags from DB after flush (new rows now have identity)
    reg = await session.execute(select(ModelRegistry).where(ModelRegistry.name.in_(local_names)))
    by_name = {r.name: r for r in reg.scalars().all()}
    for item in inventory:
        row = by_name.get(item["name"])
        if row:
            item["is_allowed"] = row.is_allowed
            item["is_default"] = row.is_default
            item["display_name"] = row.display_name

    await session.commit()
    return inventory
