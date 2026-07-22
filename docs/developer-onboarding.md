# Developer onboarding

How to run the AI Platform locally or on a shared host, and how to get an API key for Cursor / Continue.

## Prerequisites

- Docker + Docker Compose
- (GPU hosts) NVIDIA Container Toolkit — see `docs/phase-1-aws-docker-ollama.md`

## First-time setup

```bash
cd ai-platform
cp .env.example .env
# Set SECRET_KEY, WEBUI_SECRET_KEY, ADMIN_PASSWORD, POSTGRES_PASSWORD, DATABASE_URL
# Optional: bash scripts/rotate-secrets.sh

docker compose -f docker-compose.yml -f compose.gpu.yml --profile full up -d --build
bash scripts/pull-models.sh
bash scripts/check-models.sh
# On GPU hosts, also: REQUIRE_GPU=1 bash scripts/check-models.sh
bash scripts/warmup-models.sh
```

Open:

| URL | Purpose |
|-----|---------|
| http://localhost:8088/login | Sign in |
| http://localhost:8088/register | Sign up (only if `REGISTRATION_ENABLED=true`) |
| http://localhost:8088/settings/api-keys | Create API keys |
| http://localhost:8088/ | Chat |
| http://localhost:8088/admin/ | Admin console (admin role) |

Default admin: `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`.

## Get an API key (no curl required)

1. Sign in at `/login` → you land on **Account home** (`/home`)
2. Click **API keys** (or open http://localhost:8088/settings/api-keys directly)
3. Create a key and copy `sk-ai-…` (shown once)
4. Point your client at `http://<host>:8088/v1` with `Authorization: Bearer sk-ai-…`

> Note: Platform API keys are **not** inside the Open WebUI gear/settings menu.
> That menu is chat UI preferences only.

## Cursor / Continue

- Base URL: `http://<host>:8088/v1`
- API key: from Settings → API keys
- Model id: prefer `llama3.2:1b` on CPU, `llama3.2:3b` on GPU (`GET /v1/models`)
- **Enable streaming** in the provider settings so responses feel live

Speed tips: [performance.md](performance.md).

## Shared / production checklist

Prefer one-shot EC2 bootstrap: `sudo -E bash scripts/aws-production-setup.sh` (see [phase-8-production.md](phase-8-production.md)).

Also see [auth-sso.md](auth-sso.md).

Highlights:

- Set `REGISTRATION_ENABLED=false` and create users in Admin → Users
- Set `PUBLIC_URL` to the real public origin (used in password-reset emails)
- Configure SMTP for password reset emails (`SMTP_HOST`, `SMTP_FROM`, …)
- Keep models warm from **Admin → Models** (no terminal required day-to-day)
- Enable HTTPS (`scripts/enable-https.sh` or the AWS setup script)
- Never publish Open WebUI or Ollama ports on the host

## Auth model (short)

One Postgres account gates chat (Open WebUI via trusted headers) and the admin console. Details: [auth-sso.md](auth-sso.md).
