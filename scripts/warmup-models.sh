#!/usr/bin/env bash
# Warm the default chat model so the first user prompt is not a cold load.
# Usage: bash scripts/warmup-models.sh [model]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

load_env_key() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" .env 2>/dev/null | tail -n1 | sed 's/\r$//' || true)"
  if [[ -n "$line" ]]; then
    local val="${line#*=}"
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    export "${key}=${val}"
  fi
}

if [[ -f .env ]]; then
  load_env_key DEFAULT_CHAT_MODEL
  load_env_key OLLAMA_MODELS
fi

MODEL="${1:-${DEFAULT_CHAT_MODEL:-}}"
if [[ -z "$MODEL" ]]; then
  MODEL="${OLLAMA_MODELS%% *}"
fi
MODEL="${MODEL:-llama3.2:1b}"

if ! docker compose ps ollama --status running 2>/dev/null | grep -q ollama; then
  echo "Ollama is not running. Start the stack first."
  exit 1
fi

# Prefer an installed model if the configured default is not pulled yet
if ! docker compose exec -T ollama ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
  FALLBACK="$(docker compose exec -T ollama ollama list 2>/dev/null | awk 'NR==2 {print $1}')"
  if [[ -n "$FALLBACK" ]]; then
    echo "Model $MODEL not installed; warming $FALLBACK instead."
    echo "  Pull preferred default later: bash scripts/pull-models.sh $MODEL"
    MODEL="$FALLBACK"
  else
    echo "No models installed. Run: bash scripts/pull-models.sh"
    exit 1
  fi
fi

echo "Warming model: $MODEL (keep-alive from OLLAMA_KEEP_ALIVE)"
# ollama run loads the model; short prompt keeps warmup cheap
printf 'ok\n' | docker compose exec -T ollama ollama run "$MODEL" >/dev/null || true

echo "Loaded models:"
docker compose exec -T ollama ollama ps
echo "Done."
