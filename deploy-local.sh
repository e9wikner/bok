#!/usr/bin/env bash
# Deploy app containers locally on the server
# Run: cd /opt/docker/bok && ./deploy-local.sh
#
# Multi-tenant mode is enabled by default with test keys.
# Override with environment variables if needed:
#   MULTI_TENANT=false ./deploy-local.sh
#
# Create a tenant after deploy:
#   docker exec -it bokfoering-api \
#     python main.py --create-tenant acme "Acme AB" key-acme-123
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_HOST=${DEPLOY_HOST:-$(hostname)}

cd "$SCRIPT_DIR"

# Pull latest code if this is a git repo
if [ -d .git ]; then
    echo "==> Pulling latest code"
    git pull --ff-only
fi

echo "==> Starting containers with DEPLOY_HOST=$DEPLOY_HOST"
echo "    Multi-tenant mode enabled (hardcoded test keys)"

docker compose -f docker-compose.local.yml up -d --build

echo ""
echo "API:      http://$DEPLOY_HOST:8000"
echo "Frontend: http://$DEPLOY_HOST:3000"
echo ""
echo "Multi-tenant mode is ON."
echo "Default tenant 'default' is auto-created on startup."
echo ""
echo "API key:   dev-key-change-in-production"
echo "Admin key: test-admin-key"
echo ""
echo "Create additional tenants:"
echo "  docker exec -it bokfoering-api \\"
echo "    python main.py --create-tenant acme 'Acme AB' key-acme-123"
