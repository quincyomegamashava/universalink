#!/usr/bin/env bash
# Generate strong secrets for .env (does not write the file — prints values).
# Usage: bash scripts/rotate-secrets.sh
set -euo pipefail

PG_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
ADMIN_PASS="$(openssl rand -base64 18 | tr -d '/+=' | head -c 20)!"
GRAFANA_PASS="$(openssl rand -base64 18 | tr -d '/+=' | head -c 20)!"

echo "# Paste into .env (then recreate backend / open-webui / postgres so they reload env):"
echo "SECRET_KEY=$(openssl rand -hex 32)"
echo "WEBUI_SECRET_KEY=$(openssl rand -hex 32)"
echo "POSTGRES_PASSWORD=${PG_PASS}"
echo "DATABASE_URL=postgresql+asyncpg://aiplatform:${PG_PASS}@postgres:5432/aiplatform"
echo "ADMIN_PASSWORD=${ADMIN_PASS}"
echo "GRAFANA_PASSWORD=${GRAFANA_PASS}"
echo
echo "# Then: docker compose --profile full up -d --force-recreate backend open-webui"
echo "# If Postgres password changed on an existing volume, also recreate postgres or update the role."
