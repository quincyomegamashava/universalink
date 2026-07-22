# Phase 6 — RAG

## Flow

Upload PDF / Markdown / ZIP (repo) → chunk → Ollama embeddings → Qdrant → inject context via `collection_id` on `/v1/chat/completions`.

## Endpoints

- `POST /api/rag/collections`
- `POST /api/rag/collections/{id}/upload`
- `POST /api/rag/collections/{id}/index-path`
- `POST /api/rag/search`
- `GET /api/rag/admin/collections` (admin)

## Prerequisite

```bash
docker compose exec ollama ollama pull nomic-embed-text
```
