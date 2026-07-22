# Phase 5 — OpenAI-compatible API

## Endpoints

- `GET /v1/models`
- `POST /v1/chat/completions` (SSE streaming supported)
- `POST /v1/completions`
- `POST /v1/embeddings`

All require `Authorization: Bearer sk-ai-...`

## Cursor / Continue

Base URL: `http://<host>:8088/v1`  
API key: create at `/settings/api-keys` after signing in (or `POST /api/api-keys` with a JWT).

**Always enable streaming** in the client so tokens appear as they generate. Non-stream waits for the full completion.

Default model on CPU: `llama3.2:1b` (see [performance.md](performance.md)).

## Example (streaming — preferred)

```bash
curl -N http://localhost:8088/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

## Example (non-stream)

```bash
curl http://localhost:8088/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"hi"}],"stream":false}'
```

Avoid `collection_id` on IDE traffic unless you need RAG — it adds retrieval latency before generation.
