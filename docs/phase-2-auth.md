# Phase 2 — FastAPI authentication, API keys, RBAC

## What was built

- JWT access + refresh tokens (argon2 password hashing)
- API key create/list/revoke (raw key shown once)
- Roles: `admin`, `user`
- Redis-backed rate limiting
- Bootstrap admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD`
- **Shared portal SSO** for chat + admin (see [auth-sso.md](auth-sso.md))

## Key endpoints

| Method | Path | Auth |
|--------|------|------|
| GET/POST | `/login` | public (browser) |
| GET/POST | `/register` | public if enabled |
| GET | `/auth/verify` | cookie (NGINX auth_request) |
| POST | `/api/auth/login` | public (API tokens) |
| POST | `/api/auth/refresh` | refresh token |
| POST | `/api/auth/register` | if enabled |
| GET | `/api/auth/me` | JWT |
| POST | `/api/api-keys` | JWT |
| GET/DELETE | `/api/api-keys` | JWT |
| GET/POST/PATCH | `/api/admin/users` | admin JWT |

## Test

```bash
docker compose --profile full up -d --build
curl -s http://localhost:8088/health
curl -s -X POST http://localhost:8088/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"ChangeMeAdmin123!"}'
```

Browser: open `http://localhost:8088/login`.

## Troubleshooting

- 401 on login: check `.env` admin password and backend logs
- Rate limit 429: wait 60s or raise `RATE_LIMIT_PER_MINUTE`
- Chat redirects to `/login`: start with `--profile full` so backend SSO is up
