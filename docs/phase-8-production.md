# Phase 8 — Production ops

Primary path on a fresh Ubuntu EC2 host:

```bash
# From the ai-platform/ directory (code already on the server):
DOMAIN=ai.example.com EMAIL=ops@example.com \
  ADMIN_EMAIL=admin@example.com \
  sudo -E bash scripts/aws-production-setup.sh
```

That script rotates secrets, obtains Let's Encrypt TLS, activates HTTPS NGINX,
starts the full stack (+ GPU overlay when `nvidia-smi` is present), pulls models,
and writes credentials to `/root/ai-platform-credentials.txt`.

## Monitoring

```bash
docker compose --profile full --profile monitoring up -d
```

- Prometheus: `http://127.0.0.1:9090` (SSH tunnel only)
- Grafana: `http://127.0.0.1:3000` (SSH tunnel only)
- Backend metrics: `http://127.0.0.1:8088/metrics` (or via HTTPS `/metrics` on the public host)

Do not publish 9090/3000 on the security group.

## Backups

```bash
bash scripts/backup-postgres.sh
# Also snapshot EC2 volumes for ollama_data / qdrant_data
```

Backups land in `./backups/postgres-*.sql.gz` (last 14 kept).

## HTTPS (manual)

```bash
DOMAIN=ai.example.com EMAIL=you@example.com sudo bash scripts/enable-https.sh
# Sets PUBLIC_URL=https://ai.example.com in .env (do this if not using aws-production-setup)
docker compose -f docker-compose.yml -f compose.prod.yml --profile full up -d
```

## Secrets rotation

```bash
bash scripts/rotate-secrets.sh
# Paste values into .env, update DATABASE_URL if Postgres password changed
docker compose --profile full up -d --force-recreate backend open-webui
```

## Models

Prefer **Admin → Models** in the console:

- **Warm chat + embeddings** / per-row **Warm** (keeps weights loaded; respects `OLLAMA_KEEP_ALIVE`)
- Pull / delete / refresh inventory

CLI (bootstrap / automation):

```bash
bash scripts/pull-models.sh
bash scripts/check-models.sh
bash scripts/warmup-models.sh
# GPU hosts:
REQUIRE_GPU=1 bash scripts/check-models.sh
```

See [performance.md](performance.md).

## Scaling notes

| Layer | Scale approach |
|-------|----------------|
| NGINX / FastAPI / Admin | Horizontal replicas behind LB |
| Postgres / Redis / Qdrant | Vertical then managed services / replicas |
| **Ollama** | Primary bottleneck — more GPU instances; shard models |

## Security checklist

- [x] Rotate `SECRET_KEY`, `WEBUI_SECRET_KEY`, DB password, admin password (`scripts/rotate-secrets.sh` or `aws-production-setup.sh`)
- [x] `PUBLIC_URL` matches the real origin (script sets `https://$DOMAIN`)
- [x] SG: 22/80/443 only (plus monitoring via SSH tunnel — ports bound to 127.0.0.1)
- [x] Ollama and Open WebUI ports not published on the host
- [x] `REGISTRATION_ENABLED=false` unless intentional open signup
- [ ] SMTP configured for password-reset emails (or document admin reset path — log-link fallback works without SMTP)
- [x] TLS enabled with real domain (`enable-https.sh` / aws script)
- [x] Developers onboarded via [developer-onboarding.md](developer-onboarding.md)
- [x] Production refuses placeholder secrets at backend startup
- [x] Session cookies set `Secure` when `PUBLIC_URL` is https
- [x] OpenAPI docs disabled when `APP_DEBUG=false`
- [x] Schema migrations via Alembic in production (`backend/entrypoint.sh`)
