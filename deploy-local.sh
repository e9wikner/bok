#!/usr/bin/env bash
# Deploy to local test server
# Usage: ./deploy-local.sh [user@host]

set -euo pipefail

REMOTE=${1:-dave@homeassistant.local}
REMOTE_HOST=${REMOTE#*@}
REMOTE_DIR=/opt/docker/bok
REPO_URL=https://github.com/e9wikner/bok.git

echo "==> Deploying to $REMOTE:$REMOTE_DIR"

ssh "$REMOTE" bash -s "$REMOTE_DIR" "$REPO_URL" "$REMOTE_HOST" << 'ENDSSH'
set -euo pipefail
REMOTE_DIR=$1
REPO_URL=$2
DEPLOY_HOST=$3

if [ -d "$REMOTE_DIR/.git" ]; then
  git -C "$REMOTE_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$REMOTE_DIR"
fi

cd "$REMOTE_DIR"
DEPLOY_HOST="$DEPLOY_HOST" docker compose -f docker-compose.local.yml up -d --build

echo "API:      http://$DEPLOY_HOST:8000"
echo "Frontend: http://$DEPLOY_HOST:3000"
ENDSSH
