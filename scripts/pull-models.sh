#!/usr/bin/env bash
# Pull Ollama models into the running ollama container.
# Usage: bash scripts/pull-models.sh [model ...]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Safely load only KEY=VALUE lines (avoids breaking on spaces in values like "AI Platform")
load_env_key() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" .env 2>/dev/null | tail -n1 || true)"
  if [[ -n "$line" ]]; then
    local val="${line#*=}"
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    export "${key}=${val}"
  fi
}

if [[ -f .env ]]; then
  load_env_key OLLAMA_MODELS
fi

MODELS=("$@")
if [[ ${#MODELS[@]} -eq 0 ]]; then
  # Defaults from .env — prefer 1b-class on CPU; 3b+ on GPU
  read -r -a MODELS <<< "${OLLAMA_MODELS:-llama3.2:1b llama3.2:3b}"
fi

if ! docker compose ps ollama --status running 2>/dev/null | grep -q ollama; then
  echo "Ollama container is not running. Start the stack first:"
  echo "  docker compose up -d"
  exit 1
fi

echo "Pulling models: ${MODELS[*]}"
for model in "${MODELS[@]}"; do
  echo "==> ollama pull $model"
  # Retry a few times — large pulls often hit transient network EOFs
  attempt=1
  until docker compose exec -T ollama ollama pull "$model"; do
    if [[ "$attempt" -ge 4 ]]; then
      echo "Failed to pull $model after $attempt attempts (often a network timeout)."
      echo "Retry later with: bash scripts/pull-models.sh $model"
      exit 1
    fi
    echo "Pull failed (network?). Retrying in 5s (attempt $((attempt + 1))/4)..."
    attempt=$((attempt + 1))
    sleep 5
  done
done

echo "==> Installed models:"
docker compose exec -T ollama ollama list

# Warm the first / default model so the next chat is not a cold load
if [[ -x "$ROOT/scripts/warmup-models.sh" ]] || [[ -f "$ROOT/scripts/warmup-models.sh" ]]; then
  bash "$ROOT/scripts/warmup-models.sh" "${MODELS[0]}"
fi

echo "Done."
