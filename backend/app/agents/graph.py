from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import agent_runtime
from app.core.config import get_settings
from app.services.ollama import ollama_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a helpful platform agent with access to tools. "
    "Use tools when they help answer the user. "
    "After tool results, give a concise final answer. "
    "Do not invent tool outputs."
)


class AgentState(TypedDict):
    messages: list[dict[str, Any]]
    iteration: int
    max_iterations: int
    model: str
    role: str
    tool_traces: list[dict[str, Any]]
    reply: str


def _to_ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pass through OpenAI-ish message dicts for Ollama /api/chat."""
    out: list[dict[str, Any]] = []
    for m in messages:
        item: dict[str, Any] = {"role": m["role"], "content": m.get("content") or ""}
        if m.get("tool_calls"):
            item["tool_calls"] = m["tool_calls"]
        if m.get("tool_name"):
            item["tool_name"] = m["tool_name"]
        out.append(item)
    return out


def _extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    calls = message.get("tool_calls") or []
    normalized = []
    for i, call in enumerate(calls):
        fn = call.get("function") or {}
        name = fn.get("name") or call.get("name")
        raw_args = fn.get("arguments") if "function" in call else call.get("arguments")
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": raw_args}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        call_id = call.get("id") or f"call_{i}_{name}"
        normalized.append({"id": call_id, "name": name, "arguments": args})
    return normalized


async def run_agent(
    session: AsyncSession,
    *,
    message: str,
    role: str,
    model: str | None = None,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    model_name = model or settings.default_chat_model
    max_iters = max_iterations or settings.agent_max_iterations

    allowed = await agent_runtime.allowed_tool_names(session, role)
    tools_schema = agent_runtime.openai_tools(allowed) if allowed else None

    initial: AgentState = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "iteration": 0,
        "max_iterations": max_iters,
        "model": model_name,
        "role": role,
        "tool_traces": [],
        "reply": "",
    }

    async def agent_node(state: AgentState) -> dict[str, Any]:
        ollama_msgs = _to_ollama_messages(state["messages"])
        result = await ollama_client.chat(
            state["model"],
            ollama_msgs,
            stream=False,
            tools=tools_schema,
        )
        assert isinstance(result, dict)
        msg = result.get("message") or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []
        assistant: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        new_messages = list(state["messages"]) + [assistant]
        return {
            "messages": new_messages,
            "iteration": state["iteration"] + 1,
            "reply": content,
        }

    async def tools_node(state: AgentState) -> dict[str, Any]:
        last = state["messages"][-1]
        calls = _extract_tool_calls(last)
        new_messages = list(state["messages"])
        traces = list(state["tool_traces"])
        for call in calls:
            name = call["name"]
            args = call["arguments"] if isinstance(call["arguments"], dict) else {}
            result = await agent_runtime.invoke(session, name, state["role"], **args)
            traces.append(
                {
                    "tool": name,
                    "arguments": args,
                    "success": result.success,
                    "output": result.output[:4000],
                    "data": result.data,
                }
            )
            new_messages.append(
                {
                    "role": "tool",
                    "tool_name": name,
                    "content": result.output,
                }
            )
        return {"messages": new_messages, "tool_traces": traces}

    def should_continue(state: AgentState) -> str:
        if state["iteration"] >= state["max_iterations"]:
            return "end"
        last = state["messages"][-1] if state["messages"] else {}
        if last.get("role") == "assistant" and last.get("tool_calls"):
            return "tools"
        return "end"

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "agent")

    compiled = graph.compile()
    final: AgentState = await compiled.ainvoke(initial)

    reply = (final.get("reply") or "").strip()
    if not reply:
        for m in reversed(final.get("messages") or []):
            if m.get("role") == "assistant" and (m.get("content") or "").strip():
                reply = m["content"].strip()
                break
        if not reply and final.get("tool_traces"):
            reply = "Tools ran but the model returned no final text. See tool_traces."

    return {
        "reply": reply,
        "model": model_name,
        "iterations": final.get("iteration", 0),
        "tool_traces": final.get("tool_traces") or [],
        "steps": [
            {
                "role": m.get("role"),
                "content": (m.get("content") or "")[:500],
                "has_tool_calls": bool(m.get("tool_calls")),
            }
            for m in (final.get("messages") or [])
            if m.get("role") != "system"
        ],
    }
