#!/usr/bin/env bash
# Deploy app containers locally on the server
# Run locally: cd /opt/docker/bok && ./deploy-local.sh
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
DEPLOY_HOST="$DEPLOY_HOST" docker compose -f docker-compose.local.yml up -d --build

echo ""
echo "API:      http://$DEPLOY_HOST:8000"
echo "Frontend: http://$DEPLOY_HOST:3000"
