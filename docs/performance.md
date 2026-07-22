# Performance — chat and API keys

## Why ChatGPT / Gemini feel faster

Those products run on large GPU fleets. This platform runs **your** Ollama instance. Token speed is almost entirely hardware + model size. NGINX / FastAPI / Open WebUI add little compared to inference.

## Current defaults (CPU-friendly)

| Setting | Value | Why |
|---------|-------|-----|
| `DEFAULT_CHAT_MODEL` / first `OLLAMA_MODELS` | `llama3.2:1b` | Much higher tokens/sec on CPU than 3B/7B |
| `OLLAMA_KEEP_ALIVE` | `-1` | Keep weights loaded — no cold reload per prompt |
| `OLLAMA_NUM_PARALLEL` | `1` | Avoid CPU thrashing |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | One resident model |

After pull / restart:

```bash
bash scripts/pull-models.sh          # pulls + warms first model
bash scripts/warmup-models.sh        # warm again anytime
bash scripts/check-models.sh         # models present; notes GPU if missing
```

In Open WebUI, select **`llama3.2:1b`** for snappy local replies. Use `llama3.2:3b` when you want better quality and can wait (or have a GPU).

## GPU path (production / near ChatGPT feel)

```bash
# NVIDIA host with Container Toolkit
docker compose -f docker-compose.yml -f compose.gpu.yml --profile full up -d --build
REQUIRE_GPU=1 bash scripts/check-models.sh
bash scripts/warmup-models.sh
```

Verify:

```bash
docker compose exec ollama nvidia-smi -L
```

On GPU, prefer `llama3.2:3b` (or larger) as default; keep `OLLAMA_KEEP_ALIVE=-1`.

Windows laptop: GPU only works if Docker Desktop has NVIDIA/WSL2 GPU passthrough. Otherwise you stay on CPU.

## Measure tokens/sec

```bash
docker compose exec -T ollama ollama run llama3.2:1b "Say hello in one sentence"
# Watch eval rate in the footer, or:
docker compose exec -T ollama curl -s http://127.0.0.1:11434/api/chat \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"hi"}],"stream":false}' \
  | head -c 500
```

Look for `eval_count` / `eval_duration` in the JSON (`tokens ≈ eval_count`, `tok/s ≈ eval_count / (eval_duration_ns / 1e9)`).

## API keys — same speed as chat

`/v1` uses the same Ollama. To feel responsive in Cursor / Continue:

1. Use **streaming** (`"stream": true`) — otherwise the client waits for the full answer.
2. Use the warm default model (`llama3.2:1b` on CPU).
3. Do **not** pass `collection_id` (RAG) unless you need retrieval — that adds embedding + Qdrant latency before generation.
4. NGINX already has `proxy_buffering off` on `/v1/`.

Example (streaming):

```bash
curl -N http://localhost:8088/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

## What we do not promise

- Matching ChatGPT/Gemini latency on CPU.
- Fast `mistral:7b` without a GPU.
