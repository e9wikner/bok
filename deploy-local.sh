#!/usr/bin/env bash
# Deploy app containers locally on the server
# Run locally: cd /opt/docker/bok && ./deploy-local.sh
#
# Multi-tenant mode:
#   MULTI_TENANT=true ADMIN_API_KEY=secret ./deploy-local.sh
#
# Create a tenant after deploy:
#   docker exec -e MULTI_TENANT=true -it bokfoering-api \
#     python main.py --create-tenant acme "Acme AB" key-acme-123
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_URL=https://github.com/e9wikner/bok.git
DEPLOY_HOST=${DEPLOY_HOST:-$(hostname)}

cd "$SCRIPT_DIR"

# Pull latest code if this is a git repo
if [ -d .git ]; then
    echo "==> Pulling latest code"
    git pull --ff-only
fi

echo "==> Starting containers with DEPLOY_HOST=$DEPLOY_HOST"
echo "    MULTI_TENANT=${MULTI_TENANT:-false}"

DEPLOY_HOST="$DEPLOY_HOST" \
MULTI_TENANT="${MULTI_TENANT:-false}" \
ADMIN_API_KEY="${ADMIN_API_KEY:-}" \
  docker compose -f docker-compose.local.yml up -d --build

echo ""
echo "API:      http://$DEPLOY_HOST:8000"
echo "Frontend: http://$DEPLOY_HOST:3000"

if [ "${MULTI_TENANT:-false}" = "true" ]; then
    echo ""
    echo "Multi-tenant mode enabled."
    echo "Create a tenant:"
    echo "  docker exec -e MULTI_TENANT=true -it bokfoering-api \\"
    echo "    python main.py --create-tenant <id> <name> <api_key>"
fi
