#!/usr/bin/env bash
# Enable HTTPS with Let's Encrypt (certbot) on Ubuntu host.
# Usage: DOMAIN=ai.example.com EMAIL=you@example.com bash scripts/enable-https.sh
set -euo pipefail

: "${DOMAIN:?Set DOMAIN}"
: "${EMAIL:?Set EMAIL}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

apt-get update -y
apt-get install -y certbot

# Prefer standalone when ports are free; fall back to webroot if nginx is already up
if ! curl -sf "http://127.0.0.1/nginx-health" >/dev/null 2>&1 \
   && ! curl -sf "http://127.0.0.1:8088/nginx-health" >/dev/null 2>&1; then
  certbot certonly --standalone -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL"
else
  mkdir -p /var/www/certbot
  certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL"
fi

mkdir -p certs
cp "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" certs/fullchain.pem
cp "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" certs/privkey.pem
chmod 600 certs/privkey.pem

# Activate HTTPS server (HTTP → redirect + TLS on 443)
cp nginx/https.conf.example nginx/conf.d/default.conf

echo "Certificates copied to ./certs and HTTPS NGINX config activated."
echo "Reload / recreate nginx:"
echo "  docker compose --profile full up -d nginx"
echo "  # or: docker compose exec nginx nginx -s reload"
echo "Set PUBLIC_URL=https://${DOMAIN} in .env and recreate backend if needed."
