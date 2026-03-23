#!/usr/bin/env bash
# Pull latest changes and rebuild if there are new commits.
# Usage: ./update.sh [compose-file]
#   Run via cron, e.g.: */5 * * * * cd /opt/docker/bok && ./update.sh

set -euo pipefail

COMPOSE_FILE=${1:-docker-compose.local.yml}

git fetch --quiet origin

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0
fi

echo "$(date): updating $LOCAL -> $REMOTE"
git pull --ff-only
DEPLOY_HOST=${DEPLOY_HOST:-$(hostname)} docker compose -f "$COMPOSE_FILE" up -d --build
