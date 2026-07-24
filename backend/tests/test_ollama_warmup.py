"""Ollama client warmup / running helpers (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ollama import OllamaClient


def _tags_resp(names: list[str]) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"models": [{"name": n} for n in names]}
    return mock


def _ok_post(body: dict | None = None) -> MagicMock:
    mock = MagicMock()
    mock.is_error = False
    mock.raise_for_status = MagicMock()
    mock.json.return_value = body or {"response": "ok"}
    return mock


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
async def test_warmup_posts_generate_for_chat():
    client = OllamaClient(base_url="http://ollama:11434")
    http = AsyncMock()
    http.get = AsyncMock(return_value=_tags_resp(["llama3.2:1b"]))
    http.post = AsyncMock(return_value=_ok_post({"response": "ok"}))
    http.is_closed = False
    client._client = http
    out = await client.warmup("llama3.2:1b", keep_alive="-1")
    assert out["response"] == "ok"
    args, kwargs = http.post.await_args
    assert args[0] == "/api/generate"
    payload = kwargs["json"]
    assert payload["model"] == "llama3.2:1b"
    assert payload["keep_alive"] == -1
    assert payload["stream"] is False


@pytest.mark.asyncio
async def test_normalize_keep_alive_numeric_and_duration():
    client = OllamaClient(base_url="http://ollama:11434")
    assert client._normalize_keep_alive("-1") == -1
    assert client._normalize_keep_alive("0") == 0
    assert client._normalize_keep_alive(300) == 300
    assert client._normalize_keep_alive("5m") == "5m"
    assert client._normalize_keep_alive("-1m") == "-1m"


@pytest.mark.asyncio
async def test_warmup_posts_embeddings_for_embed_model():
    client = OllamaClient(base_url="http://ollama:11434")
    http = AsyncMock()
    http.get = AsyncMock(return_value=_tags_resp(["nomic-embed-text:latest"]))
    http.post = AsyncMock(return_value=_ok_post({"embedding": [0.1, 0.2]}))
    http.is_closed = False
    client._client = http
    out = await client.warmup("nomic-embed-text", keep_alive="-1")
    assert "embedding" in out
    args, kwargs = http.post.await_args
    assert args[0] == "/api/embeddings"
    assert kwargs["json"]["model"] == "nomic-embed-text:latest"


@pytest.mark.asyncio
async def test_warmup_missing_model_raises_clear_error():
    client = OllamaClient(base_url="http://ollama:11434")
    http = AsyncMock()
    http.get = AsyncMock(return_value=_tags_resp(["mistral:7b"]))
    http.is_closed = False
    client._client = http
    with pytest.raises(ValueError, match="not installed"):
        await client.warmup("llama3.2:1b")
    http.post.assert_not_called()


@pytest.mark.asyncio
async def test_pick_chat_model_falls_back_when_default_missing():
    client = OllamaClient(base_url="http://ollama:11434")
    http = AsyncMock()
    http.get = AsyncMock(return_value=_tags_resp(["nomic-embed-text", "llama3.2:3b"]))
    http.is_closed = False
    client._client = http
    picked = await client.pick_chat_model("llama3.2:1b")
    assert picked == "llama3.2:3b"
