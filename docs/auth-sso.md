# Platform SSO (shared login for chat + admin)

## Why this model

For a production stack you share with other developers or end users, **platform-owned login + Open WebUI trusted headers** is the default:

- One Postgres user store (`ADMIN_EMAIL` / `/register` / admin “Users”)
- One branded login/register UI you control (`/login`, `/register`)
- No Keycloak/Auth0 required for the happy path
- Open WebUI stays the chat UI; it never gets a separate password

Optional later: put OIDC in front of the same portal if an org already has an IdP.

## Flow

```
Browser → /login or /register (FastAPI + Postgres)
       → HTTP-only cookie platform_access_token
       → NGINX auth_request → /auth/verify
       → X-User-Email / X-User-Name / X-User-Role
       → Open WebUI (trusted-header auth)
```

Admins use the same login, then open `/admin/`.

## URLs

| URL | Purpose |
|-----|---------|
| `http://host:8088/login` | Sign in |
| `http://host:8088/register` | Sign up (if `REGISTRATION_ENABLED=true`) |
| `http://host:8088/settings/api-keys` | Create / revoke API keys |
| `http://host:8088/settings/password` | Change password |
| `http://host:8088/forgot-password` | Request reset |
| `http://host:8088/` | Chat (Open WebUI), after SSO |
| `http://host:8088/admin/` | Platform admin console (admin role only) |
| `http://host:8088/logout` | Sign out |

## Run (production / shared)

```bash
cd ai-platform
cp .env.example .env   # set SECRET_KEY, ADMIN_*, DB password
docker compose -f docker-compose.yml -f compose.gpu.yml --profile full up -d --build
```

Default admin: `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`.

Create a normal user via `/register`, or Admin → Users.

## Phase 1 GPU smoke (no SSO)

```bash
docker compose -f docker-compose.yml -f compose.gpu.yml -f compose.phase1.yml up -d
```

That mounts `nginx/phase1/` and clears trusted-header env so Open WebUI onboards by itself. Do not use for production.

## Security notes

- Open WebUI has **no published host port**; only NGINX can reach it (prevents header spoofing).
- Never expose `open-webui:8080` on the host.
- Keep `ENABLE_SIGNUP=false` on the Open WebUI container (compose already does).
- Rotate `SECRET_KEY` and admin password before any shared deploy.
