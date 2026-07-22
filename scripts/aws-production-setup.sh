#!/usr/bin/env bash
# Full production bootstrap for Ubuntu 24.04 EC2 (Docker Compose stack).
#
# Prerequisites:
#   - DNS A/AAAA for DOMAIN points at this host
#   - Security group allows 22, 80, 443
#   - This script is run from the ai-platform/ directory (code already on the host)
#
# Usage:
#   DOMAIN=ai.example.com EMAIL=ops@example.com \
#     ADMIN_EMAIL=admin@example.com \
#     [SMTP_HOST=...] [SMTP_USER=...] [SMTP_PASSWORD=...] [SMTP_FROM=...] \
#     sudo -E bash scripts/aws-production-setup.sh
#
set -euo pipefail

: "${DOMAIN:?Set DOMAIN (e.g. ai.example.com)}"
: "${EMAIL:?Set EMAIL (Let's Encrypt registration)}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ADMIN_EMAIL="${ADMIN_EMAIL:-admin@${DOMAIN}}"
AWS_REGION="${AWS_REGION:-us-east-1}"
CRED_FILE="${CRED_FILE:-/root/ai-platform-credentials.txt}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (sudo -E bash scripts/aws-production-setup.sh)"
  exit 1
fi

echo "==> Preflight"
if ! grep -qi ubuntu /etc/os-release 2>/dev/null; then
  echo "Warning: this script targets Ubuntu 24.04 EC2."
fi

HOST_IP="$(curl -sf --max-time 3 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
if [[ -n "$HOST_IP" ]]; then
  RESOLVED="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1; exit}' || true)"
  if [[ -n "$RESOLVED" && "$RESOLVED" != "$HOST_IP" ]]; then
    echo "Warning: $DOMAIN resolves to $RESOLVED but this instance public IP is $HOST_IP"
    echo "         Fix DNS before relying on TLS / browser access."
  fi
fi

echo "==> Host setup (Docker + optional NVIDIA)"
bash scripts/host-setup-ubuntu.sh

echo "==> Generating production .env"
PG_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
ADMIN_PASS="$(openssl rand -base64 18 | tr -d '/+=' | head -c 20)!"
GRAFANA_PASS="$(openssl rand -base64 18 | tr -d '/+=' | head -c 20)!"
SECRET_KEY="$(openssl rand -hex 32)"
WEBUI_SECRET_KEY="$(openssl rand -hex 32)"

if [[ -f .env ]]; then
  cp .env ".env.bak.$(date +%Y%m%d%H%M%S)"
fi
cp .env.example .env

set_env() {
  local key="$1"
  local val="$2"
  if grep -qE "^${key}=" .env; then
    # Escape for sed replacement
    local esc
    esc="$(printf '%s' "$val" | sed -e 's/[\/&]/\\&/g')"
    sed -i "s/^${key}=.*/${key}=${esc}/" .env
  else
    echo "${key}=${val}" >> .env
  fi
}

set_env DOMAIN "$DOMAIN"
set_env PUBLIC_URL "https://${DOMAIN}"
set_env CORS_ORIGINS "https://${DOMAIN}"
set_env APP_ENV production
set_env APP_DEBUG false
set_env REGISTRATION_ENABLED false
set_env SECRET_KEY "$SECRET_KEY"
set_env WEBUI_SECRET_KEY "$WEBUI_SECRET_KEY"
set_env ADMIN_EMAIL "$ADMIN_EMAIL"
set_env ADMIN_PASSWORD "$ADMIN_PASS"
set_env POSTGRES_PASSWORD "$PG_PASS"
set_env DATABASE_URL "postgresql+asyncpg://aiplatform:${PG_PASS}@postgres:5432/aiplatform"
set_env GRAFANA_PASSWORD "$GRAFANA_PASS"
set_env AWS_REGION "$AWS_REGION"
set_env OLLAMA_KEEP_ALIVE -1

if [[ -n "${SMTP_HOST:-}" ]]; then
  set_env SMTP_HOST "$SMTP_HOST"
  set_env SMTP_PORT "${SMTP_PORT:-587}"
  set_env SMTP_USER "${SMTP_USER:-}"
  set_env SMTP_PASSWORD "${SMTP_PASSWORD:-}"
  set_env SMTP_FROM "${SMTP_FROM:-$ADMIN_EMAIL}"
  set_env SMTP_USE_TLS "${SMTP_USE_TLS:-true}"
fi

COMPOSE_FILES=(-f docker-compose.yml -f compose.prod.yml)
GPU=0
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  echo "==> GPU detected — enabling compose.gpu.yml"
  COMPOSE_FILES+=(-f compose.gpu.yml)
  GPU=1
  set_env OLLAMA_MODELS "llama3.2:3b mistral:7b nomic-embed-text"
  set_env DEFAULT_CHAT_MODEL "llama3.2:3b"
else
  echo "==> CPU-only — small default models"
  set_env OLLAMA_MODELS "llama3.2:1b nomic-embed-text"
  set_env DEFAULT_CHAT_MODEL "llama3.2:1b"
fi

echo "==> Obtaining Let's Encrypt certificate (standalone; ports 80/443 must be free)"
# Stop any host nginx that might bind 80
systemctl stop nginx 2>/dev/null || true
docker compose "${COMPOSE_FILES[@]}" --profile full down 2>/dev/null || true

apt-get update -y
apt-get install -y certbot
certbot certonly --standalone -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL"

mkdir -p certs
cp "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" certs/fullchain.pem
cp "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" certs/privkey.pem
chmod 600 certs/privkey.pem

echo "==> Activating HTTPS NGINX config"
cp nginx/https.conf.example nginx/conf.d/default.conf

echo "==> Starting stack"
docker compose "${COMPOSE_FILES[@]}" --profile full --profile monitoring up -d --build

echo "==> Pulling and warming models"
bash scripts/pull-models.sh || true
bash scripts/check-models.sh || true
bash scripts/warmup-models.sh || true

echo "==> Smoke checks"
sleep 5
curl -sf "https://${DOMAIN}/nginx-health" | grep -q ok
curl -sf "https://${DOMAIN}/health" | grep -q ok
curl -sfI "https://${DOMAIN}/login" | head -n1

umask 077
cat > "$CRED_FILE" <<EOF
AI Platform production credentials
Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
PUBLIC_URL=https://${DOMAIN}
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASS}
GRAFANA_USER=admin
GRAFANA_PASSWORD=${GRAFANA_PASS}
# Access Grafana via SSH tunnel: ssh -L 3000:127.0.0.1:3000 user@host
# Registration is disabled — create users in Admin → Users
EOF
chmod 600 "$CRED_FILE"

echo "==> Installing cert renew cron"
RENEW_SCRIPT="/usr/local/bin/ai-platform-renew-certs.sh"
cat > "$RENEW_SCRIPT" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$ROOT"
certbot renew --quiet
cp "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" certs/fullchain.pem
cp "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" certs/privkey.pem
chmod 600 certs/privkey.pem
docker compose -f docker-compose.yml -f compose.prod.yml${GPU:+ -f compose.gpu.yml} exec -T nginx nginx -s reload || true
EOF
chmod 755 "$RENEW_SCRIPT"
(crontab -l 2>/dev/null | grep -v ai-platform-renew-certs || true; echo "15 3 * * * $RENEW_SCRIPT") | crontab -

echo
echo "=============================================="
echo " Production setup complete"
echo " URL:      https://${DOMAIN}"
echo " Admin:    ${ADMIN_EMAIL}"
echo " Password: (saved in ${CRED_FILE})"
echo " Security group: allow 22/80/443 only"
echo " Monitoring: SSH tunnel to 127.0.0.1:9090 / :3000"
echo " Models: Admin → Models → Warm chat + embeddings"
echo "=============================================="
