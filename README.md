# AI Platform — Self-hosted Ollama on AWS

Production-oriented stack: **Ollama** (GPU inference) + **Open WebUI** (chat) + **FastAPI** (shared SSO, OpenAI-compatible API, RAG, agents) + **Jinja Admin Console** + **PostgreSQL / Redis / Qdrant** + **NGINX**.

Ollama is never exposed publicly. Chat and admin share one Postgres login (see [docs/auth-sso.md](docs/auth-sso.md)).

## Quick start (Phase 1 — chat server, no SSO)

```bash
cd ai-platform
cp .env.example .env
# edit secrets

# On Ubuntu 24.04 GPU EC2:
sudo bash scripts/host-setup-ubuntu.sh

docker compose -f docker-compose.yml -f compose.gpu.yml -f compose.phase1.yml up -d
bash scripts/pull-models.sh
bash scripts/smoke-phase1.sh
```

Open `http://<public-ip>:8088/` → Open WebUI (its own onboarding).

## Production on AWS (recommended)

Upload or clone this `ai-platform/` tree onto an Ubuntu 24.04 EC2 instance, point DNS at the host, open SG ports **22/80/443**, then:

```bash
cd ai-platform
DOMAIN=ai.example.com EMAIL=ops@example.com \
  ADMIN_EMAIL=admin@example.com \
  sudo -E bash scripts/aws-production-setup.sh
```

This rotates secrets, enables Let’s Encrypt TLS, starts the full stack (GPU overlay when `nvidia-smi` exists), and saves credentials under `/root/ai-platform-credentials.txt`. Details: [docs/phase-8-production.md](docs/phase-8-production.md).

Local/dev: keep `APP_ENV=development` in `.env` (production refuses `change-me*` secrets). Registration defaults to **closed** (`REGISTRATION_ENABLED=false`).

## Full platform (Phases 2–8) — shared SSO

```bash
docker compose -f docker-compose.yml -f compose.gpu.yml --profile full up -d --build
# optional monitoring (bound to 127.0.0.1):
docker compose --profile full --profile monitoring up -d
```

| Surface | URL |
|---------|-----|
| Sign in / register | `http://host:8088/login` · `/register` (register only if enabled) |
| API keys / password | `http://host:8088/settings/api-keys` · `/settings/password` |
| Chat (Open WebUI) | `http://host:8088/` (after SSO) |
| Admin Console (Jinja) | `http://host:8088/admin/` |
| Models (warm / pull) | `http://host:8088/admin/models` |
| OpenAPI docs | only when `APP_DEBUG=true` |
| OpenAI-compatible | `http://host:8088/v1/*` |
| Health | `http://host:8088/health` |
| Metrics | `http://host:8088/metrics` |

Default admin (change immediately): see `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env`.

## Architecture

```
Clients → NGINX → /login (FastAPI) → cookie
                 → auth_request → Open WebUI (trusted headers)
                 → /admin (FastAPI Jinja)
                 → /v1, /api/* (FastAPI)
                              FastAPI → Ollama (internal)
                              FastAPI → Postgres / Redis / Qdrant
```

## Project layout

```
ai-platform/
  backend/           FastAPI + portal SSO + Jinja Admin + Alembic + tests
  frontend/          Notes only (chat = Open WebUI; admin = Jinja in backend)
  nginx/             Reverse proxy (SSO in conf.d/; phase1/ for smoke tests)
  scripts/           Host setup, model pull, backup, HTTPS, aws-production-setup
  docs/              Per-phase guides + auth-sso.md
  monitoring/        Prometheus + Grafana
  docker-compose.yml
  compose.gpu.yml
  compose.prod.yml   # 80/443 for production
  compose.phase1.yml
```

## IDE / Cursor setup

1. Login → create API key: `POST /api/api-keys`
2. Point Continue / Cursor OpenAI-compatible provider to `http://<host>/v1` with that key.

## Documentation

- [Developer onboarding](docs/developer-onboarding.md)
- [Performance](docs/performance.md)
- [Auth / SSO](docs/auth-sso.md)
- [Phase 1 — AWS / Docker / Ollama](docs/phase-1-aws-docker-ollama.md)
- [Phase 2 — Auth](docs/phase-2-auth.md)
- [Phase 3 — Database](docs/phase-3-database.md)
- [Phase 4 — Admin](docs/phase-4-admin.md)
- [Phase 5 — OpenAI API](docs/phase-5-openai-api.md)
- [Phase 6 — RAG](docs/phase-6-rag.md)
- [Phase 7 — Agents](docs/phase-7-agents.md)
- [Phase 8 — Production](docs/phase-8-production.md)

## Tests

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
```

## License

Private / your organization.
