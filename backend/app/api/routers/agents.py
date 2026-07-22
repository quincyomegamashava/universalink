from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.agents import agent_runtime
from app.agents.graph import run_agent
from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings

router = APIRouter(prefix="/api/agents", tags=["agents"])


class ToolInvokeRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    model: str | None = None
    max_iterations: int | None = Field(default=None, ge=1, le=20)


@router.get("/tools")
async def list_available_tools(user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    tools = []
    for tool in agent_runtime.list_tools():
        allowed = await agent_runtime.is_allowed(db, tool["name"], user.role)
        tools.append({**tool, "enabled": allowed})
    return tools


@router.post("/tools/invoke")
async def invoke_tool(body: ToolInvokeRequest, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    result = await agent_runtime.invoke(db, body.tool_name, user.role, **body.arguments)
    if not result.success and "disabled" in result.output.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result.output)
    return {"success": result.success, "output": result.output, "data": result.data}


@router.post("/run")
async def run_agent_endpoint(body: AgentRunRequest, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    settings = get_settings()
    try:
        return await run_agent(
            db,
            message=body.message,
            role=user.role,
            model=body.model or settings.default_chat_model,
            max_iterations=body.max_iterations,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Agent run failed: {exc}") from exc
