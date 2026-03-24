#!/usr/bin/env bash
# Set up dockerized nginx reverse proxy with Let's Encrypt SSL
# Run locally on the server: cd /opt/docker/bok && ./proxy/setup-proxy.sh
set -euo pipefail

DOMAIN=q.stefanwikner.se
EMAIL=info@stefanwikner.se
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROXY_DIR="$SCRIPT_DIR"

cd "$PROXY_DIR"
mkdir -p certbot/www certbot/conf

# Stop any existing proxy
docker compose -f docker-compose.proxy.yml down 2>/dev/null || true
docker stop nginx-bootstrap 2>/dev/null && docker rm nginx-bootstrap 2>/dev/null || true

# Step 1: Start nginx with HTTP-only config for the certbot challenge
cp nginx-bootstrap.conf nginx-active.conf
docker run -d --name nginx-bootstrap \
    --network host \
    -v "$PROXY_DIR/nginx-active.conf:/etc/nginx/conf.d/default.conf:ro" \
    -v "$PROXY_DIR/certbot/www:/var/www/certbot:ro" \
    nginx:alpine

sleep 2

# Step 2: Request certificate (skip if already exists)
if [ ! -d "certbot/conf/live/$DOMAIN" ]; then
    echo "==> Requesting Let's Encrypt certificate for $DOMAIN"
    docker run --rm \
        -v "$PROXY_DIR/certbot/www:/var/www/certbot" \
        -v "$PROXY_DIR/certbot/conf:/etc/letsencrypt" \
        certbot/certbot certonly --webroot -w /var/www/certbot \
        -d "$DOMAIN" --email "$EMAIL" --agree-tos --non-interactive
else
    echo "==> Certificate already exists for $DOMAIN"
fi

# Step 3: Stop bootstrap, switch to full SSL config, start compose stack
docker stop nginx-bootstrap && docker rm nginx-bootstrap
cp nginx-q.conf nginx-active.conf
docker compose -f docker-compose.proxy.yml up -d

echo ""
echo "==> Nginx reverse proxy is running!"
echo "    https://$DOMAIN     → frontend (localhost:3000)"
echo "    https://$DOMAIN/api → API (localhost:8000)"

# Step 4: Rebuild frontend with public API URL
echo ""
echo "==> Rebuilding frontend with public API URL..."
cd "$BOK_DIR"
docker build -t bokfoering-frontend \
    --build-arg NEXT_PUBLIC_API_URL=https://$DOMAIN \
    ./frontend-v3
docker compose -f docker-compose.local.yml up -d --no-build frontend

echo ""
echo "==> Done! Verify at https://$DOMAIN"
