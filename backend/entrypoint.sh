#!/bin/sh
set -eu
if [ "${APP_ENV:-production}" = "production" ]; then
  echo "==> Running Alembic migrations"
  alembic upgrade head
fi
echo "==> Starting API"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
