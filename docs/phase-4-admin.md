# Phase 4 — Admin Console (Jinja)

## Stack

Server-rendered **Jinja2** templates inside FastAPI (not React/Next.js).

- Templates: `backend/app/templates/admin/`
- CSS: `backend/app/static/admin.css`
- Routes: `backend/app/api/routers/admin_ui.py`
- Auth: HTTP-only JWT cookies (`admin_access_token`)

JSON admin APIs under `/api/admin/*` remain for automation.

## URL

`http://<host>/admin/`

## Pages

Dashboard, Users, Models, Usage, RAG, Agent Tools, Settings, Health.

## Test

```bash
docker compose --profile full up -d --build
# open http://localhost:8088/login
# ADMIN_EMAIL / ADMIN_PASSWORD from .env
# Admin console: http://localhost:8088/admin/
```

Shared SSO: see [auth-sso.md](auth-sso.md). Non-admin users can chat but cannot sign in to the console.
