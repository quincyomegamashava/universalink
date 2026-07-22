#!/usr/bin/env bash
# Verify Phase 1 security: Ollama must NOT be reachable on the public/host published port.
set -euo pipefail

echo "==> Checking published ports (11434 should NOT appear)"
docker compose ps
echo
if ss -tlnp 2>/dev/null | grep -q ':11434'; then
  echo "FAIL: port 11434 is listening on the host — Ollama may be exposed"
  exit 1
fi
echo "OK: 11434 not listening on host"

echo "==> Checking Ollama from inside Docker network"
docker compose exec -T ollama ollama list >/dev/null
echo "OK: Ollama reachable inside container"

echo "==> Checking NGINX health"
curl -sf http://127.0.0.1/nginx-health | grep -q ok
echo "OK: NGINX health"

echo "Phase 1 smoke checks passed."
