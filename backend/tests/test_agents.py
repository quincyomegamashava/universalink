from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.tools.database import is_read_only_sql
from app.agents.tools.filesystem import FilesystemTool
from app.agents.tools.terminal import TerminalTool
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_filesystem_rejects_path_escape(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    get_settings.cache_clear()
    tool = FilesystemTool()
    result = await tool.run(action="read", path="../outside.txt")
    assert result.success is False
    assert "escapes sandbox" in result.output.lower()


@pytest.mark.asyncio
async def test_filesystem_list_and_write(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    get_settings.cache_clear()
    tool = FilesystemTool()
    wrote = await tool.run(action="write", path="notes/hello.txt", content="hi")
    assert wrote.success is True
    listed = await tool.run(action="list", path="notes")
    assert listed.success is True
    assert "hello.txt" in listed.output
    read = await tool.run(action="read", path="notes/hello.txt")
    assert read.output == "hi"


@pytest.mark.asyncio
async def test_terminal_rejects_non_allowlisted(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_TERMINAL_ALLOWLIST", "ls,pwd,echo")
    get_settings.cache_clear()
    tool = TerminalTool()
    result = await tool.run(command="rm -rf /")
    assert result.success is False
    assert "not allowlisted" in result.output.lower()


@pytest.mark.asyncio
async def test_terminal_rejects_metacharacters(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_TERMINAL_ALLOWLIST", "echo")
    get_settings.cache_clear()
    tool = TerminalTool()
    result = await tool.run(command="echo hi; ls")
    assert result.success is False
    assert "metacharacter" in result.output.lower()


def test_database_rejects_non_select():
    assert is_read_only_sql("SELECT 1") is True
    assert is_read_only_sql("WITH x AS (SELECT 1) SELECT * FROM x") is True
    assert is_read_only_sql("DELETE FROM users") is False
    assert is_read_only_sql("SELECT 1; DROP TABLE users") is False
    assert is_read_only_sql("UPDATE users SET role='admin'") is False


@pytest.mark.asyncio
async def test_agent_stops_at_max_iterations(monkeypatch):
    from app.agents.graph import run_agent

    call_count = {"n": 0}

    async def fake_chat(model, messages, *, stream=False, options=None, tools=None):
        call_count["n"] += 1
        return {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "web_search",
                            "arguments": {"query": "loop"},
                        }
                    }
                ],
            }
        }

    session = AsyncMock()
    # is_allowed / allowed tools
    with (
        patch("app.agents.graph.ollama_client.chat", side_effect=fake_chat),
        patch("app.agents.graph.agent_runtime.allowed_tool_names", new=AsyncMock(return_value=["web_search"])),
        patch(
            "app.agents.graph.agent_runtime.openai_tools",
            return_value=[{"type": "function", "function": {"name": "web_search"}}],
        ),
        patch(
            "app.agents.graph.agent_runtime.invoke",
            new=AsyncMock(return_value=MagicMock(success=True, output="ok", data={})),
        ),
    ):
        result = await run_agent(
            session,
            message="keep searching",
            role="admin",
            model="test",
            max_iterations=2,
        )

    assert result["iterations"] == 2
    assert call_count["n"] == 2
    assert len(result["tool_traces"]) >= 1
