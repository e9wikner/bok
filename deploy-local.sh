#!/usr/bin/env bash
# Deploy app containers locally on the server
# Run: cd /opt/docker/bok && ./deploy-local.sh
#
# Set AUTH_USERNAME and AUTH_PASSWORD in .env or as environment variables
# to configure login credentials.
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

# Stop any existing containers (from any compose file) to avoid name conflicts
docker compose -f docker-compose.local.yml down --remove-orphans 2>/dev/null || true
docker compose down --remove-orphans 2>/dev/null || true

docker compose -f docker-compose.local.yml up -d --build

echo ""
echo "API:      http://$DEPLOY_HOST:8000"
echo "Frontend: http://$DEPLOY_HOST:3000"
echo ""
echo "Login with AUTH_USERNAME / AUTH_PASSWORD (default: admin / admin)"
