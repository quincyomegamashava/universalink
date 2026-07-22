from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.agents.base import BaseTool, ToolResult
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|execute|merge)\b",
    re.IGNORECASE,
)


def is_read_only_sql(sql: str) -> bool:
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        return False
    if ";" in cleaned:
        return False  # single statement only
    if _FORBIDDEN.search(cleaned):
        return False
    return cleaned.lower().startswith("select") or cleaned.lower().startswith("with")


class DatabaseTool(BaseTool):
    name = "database"
    description = (
        "Run a read-only SQL SELECT (or WITH … SELECT) against AGENT_DB_URL or the platform database."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "SELECT statement"},
            "limit": {"type": "integer", "default": 50},
        },
        "required": ["query"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        query = (kwargs.get("query") or "").strip()
        if not query:
            return ToolResult(success=False, output="query is required")
        if not is_read_only_sql(query):
            return ToolResult(success=False, output="Only single SELECT / WITH … SELECT statements are allowed")

        limit = int(kwargs.get("limit") or 50)
        limit = max(1, min(limit, 200))

        settings = get_settings()
        url = settings.agent_db_url or settings.database_url
        # Ensure async driver
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        wrapped = f"SELECT * FROM ({query.rstrip(';')}) AS agent_q LIMIT {limit}"
        engine = create_async_engine(url, pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text(wrapped))
                rows = [dict(r._mapping) for r in result.fetchall()]
            # stringify non-JSON values lightly
            safe_rows = []
            for row in rows:
                safe_rows.append({k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v) for k, v in row.items()})
            output = "\n".join(str(r) for r in safe_rows) if safe_rows else "(no rows)"
            return ToolResult(success=True, output=output, data={"rows": safe_rows, "count": len(safe_rows)})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Database tool failed: %s", exc)
            return ToolResult(success=False, output=f"Query failed: {exc}")
        finally:
            await engine.dispose()
