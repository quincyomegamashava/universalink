#!/usr/bin/env bash
# Confirm Ollama models are present, and optionally that GPU is visible.
# Usage:
#   bash scripts/check-models.sh
#   REQUIRE_GPU=1 bash scripts/check-models.sh
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
  load_env_key OLLAMA_MODELS
fi

MODELS="${OLLAMA_MODELS:-llama3.2:1b}"
echo "Checking models: $MODELS"
MISSING=0
for m in $MODELS; do
  if docker compose exec -T ollama ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$m"; then
    echo "  OK  $m"
  else
    echo "  MISSING  $m"
    MISSING=1
  fi
done
if [[ "$MISSING" -ne 0 ]]; then
  echo "Pull missing models: bash scripts/pull-models.sh"
  exit 1
fi
echo "All configured models are present."

# GPU smoke check (required when REQUIRE_GPU=1 or compose.gpu.yml is in use)
REQUIRE_GPU="${REQUIRE_GPU:-0}"
if [[ "$REQUIRE_GPU" == "1" ]]; then
  echo "Checking GPU inside ai-ollama (REQUIRE_GPU=1)..."
  if docker compose exec -T ollama nvidia-smi -L >/dev/null 2>&1; then
    docker compose exec -T ollama nvidia-smi -L
    echo "GPU OK."
  else
    echo "ERROR: nvidia-smi not available in ai-ollama."
    echo "  Restart with GPU: docker compose -f docker-compose.yml -f compose.gpu.yml --profile full up -d"
    echo "  Host needs NVIDIA drivers + NVIDIA Container Toolkit (or Docker Desktop GPU)."
    exit 1
  fi
else
  if docker compose exec -T ollama nvidia-smi -L >/dev/null 2>&1; then
    echo "GPU detected in ai-ollama:"
    docker compose exec -T ollama nvidia-smi -L
  else
    echo "Note: no GPU in ai-ollama (CPU mode). For ChatGPT-like speed use compose.gpu.yml on an NVIDIA host."
    echo "  Verify later with: REQUIRE_GPU=1 bash scripts/check-models.sh"
  fi
fi
