# Phase 3 — PostgreSQL data model

## Tables

Users, RefreshTokens, ApiKeys, Chats, Messages, UsageRecords, ModelRegistry, PlatformSettings, DocumentCollections, Documents, AdminAuditLogs, ToolPermissions.

## Migrations

App also runs `create_all` on startup for bootstrap. Prefer Alembic in production:

```bash
docker compose --profile full exec backend alembic upgrade head
```

## Test

```bash
docker compose --profile full exec postgres psql -U aiplatform -c '\dt'
```
