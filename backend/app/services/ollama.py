from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Virtual model id advertised by /v1/models and the Ollama bridge for Open WebUI.
AUTO_MODEL_ID = "auto"
AUTO_MODEL_ALIASES = frozenset({AUTO_MODEL_ID, f"{AUTO_MODEL_ID}:latest"})


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

    @staticmethod
    def _entry_name(entry: dict[str, Any]) -> str:
        return str(entry.get("name") or entry.get("model") or "").strip()

    @staticmethod
    def is_embedding_model(name: str) -> bool:
        """Heuristic: embedding tags are not valid for /api/generate."""
        n = name.lower()
        return "embed" in n

    async def resolve_installed(self, name: str) -> str | None:
        """Return the installed tag matching ``name``, or None if not pulled."""
        want = name.strip()
        if not want:
            return None
        models = await self.list_models()
        names = [self._entry_name(m) for m in models if self._entry_name(m)]
        if want in names:
            return want
        # Accept bare name when only name:tag is installed (and vice versa)
        if ":" not in want:
            for n in names:
                if n == f"{want}:latest" or n.startswith(f"{want}:"):
                    return n
        else:
            base = want.split(":", 1)[0]
            for n in names:
                if n == want or n == f"{base}:latest":
                    return n
        return None

    async def pick_chat_model(self, preferred: str | None = None) -> str | None:
        """Preferred chat model if installed, else first non-embedding local model."""
        settings = get_settings()
        candidate = (preferred or settings.default_chat_model or "").strip()
        resolved = await self.resolve_installed(candidate) if candidate else None
        if resolved and not self.is_embedding_model(resolved):
            return resolved
        for entry in await self.list_models():
            name = self._entry_name(entry)
            if name and not self.is_embedding_model(name):
                return name
        return None

    async def pick_fastest_chat_model(self) -> str | None:
        """Prefer an already-loaded chat model, else the smallest installed chat model.

        Used by the virtual ``auto`` model id for low-latency replies.
        """
        try:
            running = await self.list_running()
        except Exception:  # noqa: BLE001
            running = []
        for entry in running:
            name = self._entry_name(entry)
            if name and not self.is_embedding_model(name):
                return name

        chat_entries: list[tuple[int, str]] = []
        for entry in await self.list_models():
            name = self._entry_name(entry)
            if not name or self.is_embedding_model(name):
                continue
            size = int(entry.get("size") or 0)
            chat_entries.append((size, name))
        if not chat_entries:
            return await self.pick_chat_model()
        chat_entries.sort(key=lambda item: (item[0], item[1]))
        return chat_entries[0][1]

    async def resolve_chat_model(self, requested: str | None) -> str:
        """Map ``auto`` (or empty) to a concrete installed chat model."""
        name = (requested or "").strip()
        if not name or name.lower() in AUTO_MODEL_ALIASES:
            picked = await self.pick_fastest_chat_model()
            if not picked:
                raise ValueError(
                    "No chat model available for 'auto'. Pull a model first "
                    "(e.g. llama3.2:1b)."
                )
            return picked
        return name

    def _ollama_error_detail(self, resp: httpx.Response) -> str:
        try:
            data = resp.json()
            err = data.get("error") if isinstance(data, dict) else None
            if err:
                return str(err)
        except Exception:  # noqa: BLE001
            pass
        text = (resp.text or "").strip()
        return text[:300] if text else resp.reason_phrase

    def _normalize_keep_alive(self, value: str | int | float | None) -> str | int:
        """Ollama accepts a duration string (``5m``) or a numeric seconds value.

        The string ``\"-1\"`` is invalid (missing unit). Forever must be the
        JSON number ``-1``.
        """
        if value is None:
            value = get_settings().ollama_keep_alive
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if not text:
            return -1
        # Pure integer (including negatives) → send as number
        try:
            if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
                return int(text)
        except ValueError:
            pass
        return text

    async def warmup(
        self,
        model: str,
        *,
        keep_alive: str | int | None = None,
        embedding: bool | None = None,
    ) -> dict[str, Any]:
        """Load a model cheaply so the first user request is not cold.

        Chat models use ``/api/generate``. Embedding models use ``/api/embeddings``
        (generate returns 400 for embed-only weights).
        """
        resolved = await self.resolve_installed(model)
        if not resolved:
            raise ValueError(
                f"Model '{model}' is not installed on Ollama. "
                "Pull it first, or use Warm on a row in Local inventory."
            )

        use_embed = self.is_embedding_model(resolved) if embedding is None else embedding
        alive = self._normalize_keep_alive(keep_alive)

        if use_embed:
            payload: dict[str, Any] = {
                "model": resolved,
                "prompt": "ok",
                "keep_alive": alive,
            }
            resp = await self._get_client().post("/api/embeddings", json=payload)
            if resp.is_error:
                raise ValueError(
                    f"Failed to warm embedding model '{resolved}': "
                    f"{self._ollama_error_detail(resp)}"
                )
            return resp.json()

        payload = {
            "model": resolved,
            "prompt": "ok",
            "stream": False,
            "keep_alive": alive,
        }
        resp = await self._get_client().post("/api/generate", json=payload)
        if resp.is_error:
            raise ValueError(
                f"Failed to warm '{resolved}': {self._ollama_error_detail(resp)}"
            )
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
