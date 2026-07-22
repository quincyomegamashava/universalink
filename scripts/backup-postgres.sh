#!/usr/bin/env bash
# PostgreSQL logical backup into ./backups/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p backups
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="backups/postgres-${STAMP}.sql.gz"
docker compose --profile full exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-aiplatform}" "${POSTGRES_DB:-aiplatform}" | gzip > "$OUT"
echo "Wrote $OUT"
# Keep last 14 backups
ls -1t backups/postgres-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
