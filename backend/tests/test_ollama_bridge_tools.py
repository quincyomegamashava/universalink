"""Bridge strips tools when the resolved model does not support them."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.api.routers import ollama_bridge as bridge


@pytest.fixture(autouse=True)
def _clear_caps_cache():
    bridge._capabilities_cache.clear()
    yield
    bridge._capabilities_cache.clear()


@pytest.mark.asyncio
async def test_rewrite_strips_tools_for_gemma():
    body = json.dumps(
        {
            "model": "auto",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "search"}}],
            "stream": False,
        }
    ).encode()

    with (
        patch.object(
            bridge.ollama_client,
            "resolve_chat_model",
            new=AsyncMock(return_value="gemma3:4b"),
        ),
        patch.object(
            bridge,
            "_capabilities_for",
            new=AsyncMock(return_value=["completion"]),
        ),
    ):
        out = await bridge._rewrite_model_in_body(body, path="api/chat")

    data = json.loads(out)
    assert data["model"] == "gemma3:4b"
    assert "tools" not in data


@pytest.mark.asyncio
async def test_rewrite_keeps_tools_when_supported():
    body = json.dumps(
        {
            "model": "llama3.2:3b",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "search"}}],
        }
    ).encode()

    with patch.object(
        bridge,
        "_capabilities_for",
        new=AsyncMock(return_value=["completion", "tools"]),
    ):
        out = await bridge._rewrite_model_in_body(body, path="api/chat")

    assert out == body
