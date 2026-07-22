from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class OllamaClient:
    """Thin async client for Ollama REST API. Never expose this service publicly."""

    def __init__(self, base_url: str | None = None, timeout: float = 600.0) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Reuse one AsyncClient for connection pooling across API-key traffic."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health(self) -> bool:
        try:
            resp = await self._get_client().get("/api/tags")
            return resp.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama health failed: %s", exc)
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        resp = await self._get_client().get("/api/tags")
        resp.raise_for_status()
        return resp.json().get("models", [])

    async def pull_model(self, name: str) -> dict[str, Any]:
        resp = await self._get_client().post("/api/pull", json={"name": name, "stream": False})
        resp.raise_for_status()
        return resp.json()

    async def delete_model(self, name: str) -> None:
        resp = await self._get_client().request("DELETE", "/api/delete", json={"name": name})
        resp.raise_for_status()

    async def list_running(self) -> list[dict[str, Any]]:
        """Models currently loaded in memory (Ollama GET /api/ps)."""
        resp = await self._get_client().get("/api/ps")
        resp.raise_for_status()
        return resp.json().get("models", [])

    async def warmup(self, model: str, *, keep_alive: str | None = None) -> dict[str, Any]:
        """Load a model with a cheap prompt so the first user request is not cold."""
        settings = get_settings()
        payload: dict[str, Any] = {
            "model": model,
            "prompt": "ok",
            "stream": False,
            "keep_alive": keep_alive if keep_alive is not None else settings.ollama_keep_alive,
        }
        resp = await self._get_client().post("/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        stream: bool = False,
        options: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if options:
            payload["options"] = options
        if tools:
            payload["tools"] = tools

        if stream:
            return self._stream("/api/chat", payload)
        resp = await self._get_client().post("/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def generate(
        self,
        model: str,
        prompt: str,
        *,
        stream: bool = False,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": stream}
        if options:
            payload["options"] = options
        if stream:
            return self._stream("/api/generate", payload)
        resp = await self._get_client().post("/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def embeddings(self, model: str, prompt: str) -> list[float]:
        resp = await self._get_client().post("/api/embeddings", json={"model": model, "prompt": prompt})
        resp.raise_for_status()
        data = resp.json()
        return data.get("embedding") or data.get("embeddings") or []

    async def _stream(self, path: str, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        client = self._get_client()
        async with client.stream("POST", path, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                yield json.loads(line)


ollama_client = OllamaClient()
