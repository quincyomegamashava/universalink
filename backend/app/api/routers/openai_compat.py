from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, enforce_rate_limit, get_api_key_user
from app.core.config import get_settings
from app.models import ApiKey, DocumentCollection, UsageRecord, User
from app.schemas import ChatCompletionRequest, CompletionRequest, EmbeddingRequest
from app.services.ollama import AUTO_MODEL_ID, ollama_client
from app.services.rag import rag_service

router = APIRouter(prefix="/v1", tags=["openai-compatible"])


async def _resolve_model(requested: str) -> str:
    try:
        return await ollama_client.resolve_chat_model(requested)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def _log_usage(
    db: AsyncSession,
    user: User,
    api_key: ApiKey,
    endpoint: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    status_code: int = 200,
) -> None:
    db.add(
        UsageRecord(
            user_id=user.id,
            api_key_id=api_key.id,
            endpoint=endpoint,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
            status_code=status_code,
        )
    )
    await db.commit()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@router.get("/models")
async def list_models(
    request: Request,
    db: DbSession,
    auth: tuple[User, ApiKey] = Depends(get_api_key_user),
) -> dict[str, Any]:
    user, api_key = auth
    await enforce_rate_limit(request, f"key:{api_key.id}", api_key.rate_limit_per_minute)
    models = await ollama_client.list_models()
    now = int(time.time())
    data: list[dict[str, Any]] = [
        {
            "id": AUTO_MODEL_ID,
            "object": "model",
            "created": now,
            "owned_by": "ai-platform",
        }
    ]
    for m in models:
        mid = m.get("name") or m.get("model")
        if not mid:
            continue
        data.append(
            {
                "id": mid,
                "object": "model",
                "created": now,
                "owned_by": "ollama",
            }
        )
    await _log_usage(db, user, api_key, "/v1/models", None, 0, 0, 0)
    return {"object": "list", "data": data}


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    db: DbSession,
    auth: tuple[User, ApiKey] = Depends(get_api_key_user),
) -> Any:
    user, api_key = auth
    await enforce_rate_limit(request, f"key:{api_key.id}", api_key.rate_limit_per_minute)
    start = time.perf_counter()
    model = await _resolve_model(body.model)

    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    if body.collection_id is not None:
        col = await db.execute(select(DocumentCollection).where(DocumentCollection.id == body.collection_id))
        collection = col.scalar_one_or_none()
        if collection and messages:
            context = await rag_service.build_context(collection.qdrant_collection, messages[-1]["content"])
            if context:
                messages.insert(0, {"role": "system", "content": context})

    options: dict[str, Any] = {}
    if body.temperature is not None:
        options["temperature"] = body.temperature
    if body.max_tokens is not None:
        options["num_predict"] = body.max_tokens

    if body.stream:
        async def event_stream() -> AsyncIterator[bytes]:
            completion_text = ""
            chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
            stream = await ollama_client.chat(model, messages, stream=True, options=options or None)
            assert isinstance(stream, AsyncIterator)
            async for part in stream:
                msg = part.get("message") or {}
                delta = msg.get("content") or ""
                completion_text += delta
                payload = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(payload)}\n\n".encode()
                if part.get("done"):
                    done_payload = {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                    yield f"data: {json.dumps(done_payload)}\n\n".encode()
                    yield b"data: [DONE]\n\n"
            latency = int((time.perf_counter() - start) * 1000)
            prompt_tokens = _estimate_tokens("".join(m["content"] for m in messages))
            await _log_usage(
                db,
                user,
                api_key,
                "/v1/chat/completions",
                model,
                prompt_tokens,
                _estimate_tokens(completion_text),
                latency,
            )

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    result = await ollama_client.chat(model, messages, stream=False, options=options or None)
    assert isinstance(result, dict)
    content = (result.get("message") or {}).get("content", "")
    latency = int((time.perf_counter() - start) * 1000)
    prompt_tokens = int(result.get("prompt_eval_count") or _estimate_tokens("".join(m["content"] for m in messages)))
    completion_tokens = int(result.get("eval_count") or _estimate_tokens(content))
    await _log_usage(db, user, api_key, "/v1/chat/completions", model, prompt_tokens, completion_tokens, latency)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


@router.post("/completions")
async def completions(
    body: CompletionRequest,
    request: Request,
    db: DbSession,
    auth: tuple[User, ApiKey] = Depends(get_api_key_user),
) -> Any:
    user, api_key = auth
    await enforce_rate_limit(request, f"key:{api_key.id}", api_key.rate_limit_per_minute)
    start = time.perf_counter()
    model = await _resolve_model(body.model)
    options: dict[str, Any] = {}
    if body.temperature is not None:
        options["temperature"] = body.temperature
    if body.max_tokens is not None:
        options["num_predict"] = body.max_tokens

    if body.stream:
        async def event_stream() -> AsyncIterator[bytes]:
            text = ""
            stream = await ollama_client.generate(model, body.prompt, stream=True, options=options or None)
            assert isinstance(stream, AsyncIterator)
            completion_id = f"cmpl-{uuid.uuid4().hex[:24]}"
            async for part in stream:
                delta = part.get("response") or ""
                text += delta
                payload = {
                    "id": completion_id,
                    "object": "text_completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"text": delta, "index": 0, "finish_reason": None}],
                }
                yield f"data: {json.dumps(payload)}\n\n".encode()
                if part.get("done"):
                    yield b"data: [DONE]\n\n"
            latency = int((time.perf_counter() - start) * 1000)
            await _log_usage(
                db,
                user,
                api_key,
                "/v1/completions",
                model,
                _estimate_tokens(body.prompt),
                _estimate_tokens(text),
                latency,
            )

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    result = await ollama_client.generate(model, body.prompt, stream=False, options=options or None)
    assert isinstance(result, dict)
    text = result.get("response", "")
    latency = int((time.perf_counter() - start) * 1000)
    prompt_tokens = int(result.get("prompt_eval_count") or _estimate_tokens(body.prompt))
    completion_tokens = int(result.get("eval_count") or _estimate_tokens(text))
    await _log_usage(db, user, api_key, "/v1/completions", model, prompt_tokens, completion_tokens, latency)
    return {
        "id": f"cmpl-{uuid.uuid4().hex[:24]}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"text": text, "index": 0, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


@router.post("/embeddings")
async def embeddings(
    body: EmbeddingRequest,
    request: Request,
    db: DbSession,
    auth: tuple[User, ApiKey] = Depends(get_api_key_user),
) -> dict[str, Any]:
    user, api_key = auth
    await enforce_rate_limit(request, f"key:{api_key.id}", api_key.rate_limit_per_minute)
    settings = get_settings()
    model = body.model or settings.embedding_model
    inputs = body.input if isinstance(body.input, list) else [body.input]
    data = []
    total_tokens = 0
    for idx, text in enumerate(inputs):
        vector = await ollama_client.embeddings(model, text)
        data.append({"object": "embedding", "index": idx, "embedding": vector})
        total_tokens += _estimate_tokens(text)
    await _log_usage(db, user, api_key, "/v1/embeddings", model, total_tokens, 0, 0)
    return {
        "object": "list",
        "data": data,
        "model": model,
        "usage": {"prompt_tokens": total_tokens, "total_tokens": total_tokens},
    }
