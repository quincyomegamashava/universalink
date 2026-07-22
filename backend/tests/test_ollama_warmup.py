"""Ollama client warmup / running helpers (mocked HTTP)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ollama import OllamaClient


@pytest.mark.asyncio
async def test_list_running_parses_models():
    client = OllamaClient(base_url="http://ollama:11434")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"models": [{"name": "llama3.2:1b", "size": 1}]}
    http = AsyncMock()
    http.get = AsyncMock(return_value=mock_resp)
    http.is_closed = False
    client._client = http
    models = await client.list_running()
    assert models[0]["name"] == "llama3.2:1b"
    http.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_warmup_posts_generate():
    client = OllamaClient(base_url="http://ollama:11434")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": "ok"}
    http = AsyncMock()
    http.post = AsyncMock(return_value=mock_resp)
    http.is_closed = False
    client._client = http
    out = await client.warmup("llama3.2:1b", keep_alive="-1")
    assert out["response"] == "ok"
    args, kwargs = http.post.await_args
    assert args[0] == "/api/generate"
    payload = kwargs["json"]
    assert payload["model"] == "llama3.2:1b"
    assert payload["keep_alive"] == "-1"
    assert payload["stream"] is False
