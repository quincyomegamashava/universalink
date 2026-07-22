from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseTool, ToolResult
from app.agents.tools import TOOL_REGISTRY
from app.models import ToolPermission

logger = logging.getLogger(__name__)

__all__ = ["AgentRuntime", "BaseTool", "ToolResult", "TOOL_REGISTRY", "agent_runtime"]


class AgentRuntime:
    """Permission-gated tool runtime used by direct invoke and the LangGraph agent loop."""

    def list_tools(self) -> list[dict[str, str]]:
        return [{"name": t.name, "description": t.description} for t in TOOL_REGISTRY.values()]

    def openai_tools(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        tools = []
        for name, tool in TOOL_REGISTRY.items():
            if names is not None and name not in names:
                continue
            tools.append(tool.openai_schema())
        return tools

    async def allowed_tool_names(self, session: AsyncSession, role: str) -> list[str]:
        names = []
        for name in TOOL_REGISTRY:
            if await self.is_allowed(session, name, role):
                names.append(name)
        return names

    async def is_allowed(self, session: AsyncSession, tool_name: str, role: str) -> bool:
        result = await session.execute(
            select(ToolPermission).where(ToolPermission.tool_name == tool_name, ToolPermission.role == role)
        )
        perm = result.scalar_one_or_none()
        return bool(perm and perm.enabled)

    async def invoke(self, session: AsyncSession, tool_name: str, role: str, **kwargs: Any) -> ToolResult:
        if tool_name not in TOOL_REGISTRY:
            return ToolResult(success=False, output=f"Unknown tool: {tool_name}")
        if not await self.is_allowed(session, tool_name, role):
            return ToolResult(success=False, output=f"Tool '{tool_name}' is disabled for role '{role}'")
        tool = TOOL_REGISTRY[tool_name]
        logger.info("Invoking tool %s for role %s", tool_name, role)
        return await tool.run(**kwargs)


agent_runtime = AgentRuntime()
