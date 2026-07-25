"""Ollama-compatible bridge so Open WebUI can see and use the virtual ``auto`` model.

Open WebUI talks Ollama protocol. Point ``OLLAMA_BASE_URL`` /
``OPEN_WEBUI_OLLAMA_URL`` at ``http://backend:8000/ollama``. Requests are
proxied to real Ollama; ``auto`` is rewritten to the fastest installed or
already-loaded chat model.

Not exposed publicly via NGINX — Docker network only.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.core.config import get_settings
from app.services.ollama import AUTO_MODEL_ALIASES, AUTO_MODEL_ID, ollama_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ollama", tags=["ollama-bridge"])

_REWRITE_PATHS = frozenset(
    {
        "api/chat",
        "api/generate",
        "api/embeddings",
        "api/show",
        "v1/chat/completions",
        "v1/completions",
    }
)

_CHAT_PATHS = frozenset({"api/chat", "v1/chat/completions"})

# Cache /api/show capabilities so we do not hit Ollama on every chat turn.
_capabilities_cache: dict[str, list[str]] = {}


def _is_auto_name(name: str | None) -> bool:
    if not name or not isinstance(name, str):
        return False
    return name.strip().lower() in AUTO_MODEL_ALIASES


def _names_match(a: str, b: str) -> bool:
    if a == b:
        return True
    if ":" not in a and (b == f"{a}:latest" or b.startswith(f"{a}:")):
        return True
    if ":" not in b and (a == f"{b}:latest" or a.startswith(f"{b}:")):
        return True
    return False


def _auto_tag_entry() -> dict[str, Any]:
    # Shape mirrors a real Ollama tag so Open WebUI does not filter it out.
    # Do not advertise "tools" here — copy real caps from the resolved model.
    return {
        "name": AUTO_MODEL_ID,
        "model": AUTO_MODEL_ID,
        "modified_at": "2026-01-01T00:00:00.000000Z",
        "size": 1,
        "digest": "sha256:" + ("a" * 64),
        "details": {
            "parent_model": "",
            "format": "gguf",
            "family": "auto",
            "families": ["auto"],
            "parameter_size": "auto",
            "quantization_level": "Q4_K_M",
        },
        "capabilities": ["completion"],
    }


async def _capabilities_for(model_name: str) -> list[str]:
    cached = _capabilities_cache.get(model_name)
    if cached is not None:
        return cached

    for entry in await ollama_client.list_models():
        name = ollama_client._entry_name(entry)
        if not _names_match(name, model_name):
            continue
        caps = entry.get("capabilities")
        if isinstance(caps, list) and caps:
            out = [str(c) for c in caps]
            _capabilities_cache[model_name] = out
            return out

    # /api/tags often omits capabilities; /api/show is authoritative.
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/show",
                json={"model": model_name, "name": model_name},
            )
        if resp.is_success:
            caps = resp.json().get("capabilities")
            if isinstance(caps, list) and caps:
                out = [str(c) for c in caps]
                _capabilities_cache[model_name] = out
                return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("ollama-bridge capabilities lookup failed for %s: %s", model_name, exc)

    out = ["completion"]
    _capabilities_cache[model_name] = out
    return out


def _strip_tools_from_payload(data: dict[str, Any]) -> bool:
    """Remove tool-calling fields Open WebUI may attach for unsupported models."""
    changed = False
    for key in ("tools", "tool_choice", "functions", "function_call"):
        if key in data:
            data.pop(key, None)
            changed = True
    messages = data.get("messages")
    if isinstance(messages, list):
        cleaned: list[Any] = []
        for msg in messages:
            if not isinstance(msg, dict):
                cleaned.append(msg)
                continue
            if msg.get("role") == "tool":
                changed = True
                continue
            if "tool_calls" in msg:
                msg = {k: v for k, v in msg.items() if k != "tool_calls"}
                changed = True
            cleaned.append(msg)
        if changed:
            data["messages"] = cleaned
    return changed


async def _rewrite_model_in_body(body: bytes, *, path: str) -> bytes:
    """Rewrite ``auto`` and strip tools when the target model cannot use them."""
    if not body:
        return body
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body
    if not isinstance(data, dict):
        return body

    changed = False
    model_name: str | None = None
    for key in ("model", "name"):
        val = data.get(key)
        if not isinstance(val, str):
            continue
        if _is_auto_name(val):
            try:
                resolved = await ollama_client.resolve_chat_model(val)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
            if resolved != val:
                logger.info("ollama-bridge resolved %s %r -> %r", key, val, resolved)
                data[key] = resolved
                changed = True
            model_name = resolved
        else:
            model_name = val

    if path in _CHAT_PATHS and model_name:
        has_tools = bool(data.get("tools") or data.get("tool_choice") or data.get("functions"))
        if has_tools or any(
            isinstance(m, dict) and (m.get("role") == "tool" or m.get("tool_calls"))
            for m in (data.get("messages") or [])
            if isinstance(data.get("messages"), list)
        ):
            caps = await _capabilities_for(model_name)
            if "tools" not in caps and _strip_tools_from_payload(data):
                logger.info("ollama-bridge stripped tools for %s (caps=%s)", model_name, caps)
                changed = True

    return json.dumps(data).encode() if changed else body


@router.get("/api/tags")
async def list_tags() -> dict[str, Any]:
    models = await ollama_client.list_models()
    entry = _auto_tag_entry()
    try:
        resolved = await ollama_client.resolve_chat_model(AUTO_MODEL_ID)
    except ValueError:
        resolved = None
    if resolved:
        for m in models:
            name = str(m.get("name") or m.get("model") or "")
            if _names_match(name, resolved):
                # Copy real size/digest so Open WebUI treats auto like a normal model.
                if m.get("size"):
                    entry["size"] = m["size"]
                if m.get("digest"):
                    entry["digest"] = m["digest"]
                details = m.get("details") if isinstance(m.get("details"), dict) else {}
                entry["details"] = {
                    **details,
                    "family": "auto",
                    "families": ["auto"],
                    "parameter_size": details.get("parameter_size") or "auto",
                }
                break
        entry["capabilities"] = await _capabilities_for(resolved)
    return {"models": [entry, *models]}


@router.post("/api/show")
async def show_model(request: Request) -> Response:
    """Open WebUI calls /api/show per model; ``auto`` must not 404 from real Ollama."""
    settings = get_settings()
    raw = await request.body()
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    requested = data.get("model") or data.get("name") or ""
    if _is_auto_name(str(requested)):
        try:
            resolved = await ollama_client.resolve_chat_model(AUTO_MODEL_ID)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        upstream_body = json.dumps({"model": resolved, "name": resolved}).encode()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                upstream = await client.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/show",
                    content=upstream_body,
                    headers={"Content-Type": "application/json"},
                )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Ollama unreachable: {exc}",
            ) from exc

        if upstream.is_error:
            # Still advertise auto so the UI can list it even if show fails.
            caps = await _capabilities_for(resolved)
            return JSONResponse(
                {
                    "modelfile": f"# virtual auto -> {resolved}",
                    "parameters": "",
                    "template": "",
                    "details": _auto_tag_entry()["details"],
                    "model_info": {},
                    "capabilities": caps,
                }
            )

        try:
            payload = upstream.json()
        except Exception:  # noqa: BLE001
            return Response(content=upstream.content, status_code=upstream.status_code)

        if isinstance(payload, dict):
            # Keep the public id as ``auto`` so the dropdown label stays correct.
            payload["model"] = AUTO_MODEL_ID
            if "modelfile" in payload and isinstance(payload["modelfile"], str):
                payload["modelfile"] = f"# virtual model: auto (routes to {resolved})\n" + payload["modelfile"]
            details = payload.get("details")
            if isinstance(details, dict):
                details = {**details, "family": "auto", "families": ["auto"], "parameter_size": "auto"}
                payload["details"] = details
            # Keep upstream capabilities (do not invent "tools").
            if not payload.get("capabilities"):
                payload["capabilities"] = await _capabilities_for(resolved)
            logger.info("ollama-bridge /api/show auto -> %s caps=%s", resolved, payload.get("capabilities"))
            return JSONResponse(payload)

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
        )

    # Non-auto: proxy as-is
    return await _proxy_request(request, "api/show", raw)


async def _proxy_request(request: Request, path: str, body: bytes | None = None) -> StreamingResponse:
    settings = get_settings()
    target = f"{settings.ollama_base_url.rstrip('/')}/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    if body is None:
        body = await request.body()
    if path in _REWRITE_PATHS and request.method.upper() == "POST":
        body = await _rewrite_model_in_body(body, path=path)

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length", "connection", "transfer-encoding"}
    }

    client = httpx.AsyncClient(timeout=600.0)
    try:
        upstream = await client.send(
            client.build_request(
                request.method,
                target,
                content=body if body else None,
                headers=headers,
            ),
            stream=True,
        )
    except httpx.RequestError as exc:
        await client.aclose()
        logger.warning("ollama-bridge upstream error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ollama unreachable: {exc}",
        ) from exc

    excluded = {"content-encoding", "transfer-encoding", "content-length", "connection"}
    out_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in excluded}

    async def byte_stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        byte_stream(),
        status_code=upstream.status_code,
        headers=out_headers,
        media_type=upstream.headers.get("content-type"),
    )


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
    response_model=None,
)
async def proxy_ollama(path: str, request: Request) -> StreamingResponse:
    """Transparent streaming proxy to Ollama, with ``auto`` resolution."""
    return await _proxy_request(request, path)
