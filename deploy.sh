#!/bin/bash
# deploy.sh - Production deployment helper script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.production"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose plugin is not installed."
        exit 1
    fi
    
    # Check env file
    if [ ! -f "$ENV_FILE" ]; then
        log_warn "$ENV_FILE not found. Creating from template..."
        if [ -f ".env.production.example" ]; then
            cp .env.production.example "$ENV_FILE"
            log_warn "Please edit $ENV_FILE with your configuration before deploying."
            exit 1
        else
            log_error "No environment template found. Please create $ENV_FILE manually."
            exit 1
        fi
    fi
    
    # Create required directories
    mkdir -p letsencrypt backups logs
    
    log_info "Prerequisites check passed!"
}

# Deploy function
deploy() {
    log_info "Starting deployment..."
    
    # Pull latest images
    log_info "Pulling latest images..."
    docker compose -f "$COMPOSE_FILE" pull
    
    # Build services
    log_info "Building services..."
    docker compose -f "$COMPOSE_FILE" build --no-cache
    
    # Start services
    log_info "Starting services..."
    docker compose -f "$COMPOSE_FILE" up -d
    
    # Wait for health checks
    log_info "Waiting for services to be healthy..."
    sleep 10
    
    # Check status
    log_info "Checking service status..."
    docker compose -f "$COMPOSE_FILE" ps
    
    log_info "Deployment completed!"
}

# Health check
health_check() {
    log_info "Running health checks..."
    
    # Load env vars
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    
    # Check API
    if curl -sf "https://${API_DOMAIN:-api.localhost}/health" > /dev/null 2>&1; then
        log_info "✓ API is healthy"
    else
        log_error "✗ API health check failed"
        docker logs bokfoering-api --tail 50
        return 1
    fi
    
    # Check Frontend
    if curl -sf "https://${APP_DOMAIN:-app.localhost}" > /dev/null 2>&1; then
        log_info "✓ Frontend is healthy"
    else
        log_error "✗ Frontend health check failed"
        docker logs bokfoering-frontend --tail 50
        return 1
    fi
    
    log_info "All health checks passed!"
}

# Update function
update() {
    log_info "Updating deployment..."
    
    # Pull latest code
    log_info "Pulling latest code..."
    git pull origin main
    
    # Rebuild and restart
    deploy
    
    # Cleanup old images
    log_info "Cleaning up old images..."
    docker system prune -f
    
    log_info "Update completed!"
}

# Backup function
backup() {
    log_info "Creating backup..."
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="backups/bokfoering_backup_${TIMESTAMP}.tar.gz"
    
    # Create backup
    docker exec bokfoering-api python -c "
import sqlite3
import shutil
from datetime import datetime
conn = sqlite3.connect('/app/data/bokfoering.db')
conn.execute('VACUUM')
conn.close()
print('Database optimized')
"
    
    # Copy database
    docker cp bokfoering-api:/app/data/bokfoering.db "backups/bokfoering_${TIMESTAMP}.db"
    
    # Create archive
    tar -czf "$BACKUP_FILE" -C backups "bokfoering_${TIMESTAMP}.db"
    rm "backups/bokfoering_${TIMESTAMP}.db"
    
    log_info "Backup created: $BACKUP_FILE"
}

# Restore function
restore() {
    if [ -z "$1" ]; then
        log_error "Please specify backup file: ./deploy.sh restore <backup-file>"
        exit 1
    fi
    
    BACKUP_FILE="$1"
    
    if [ ! -f "$BACKUP_FILE" ]; then
        log_error "Backup file not found: $BACKUP_FILE"
        exit 1
    fi
    
    log_warn "This will replace the current database. Continue? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        log_info "Restore cancelled."
        exit 0
    fi
    
    log_info "Restoring from backup..."
    
    # Stop services
    docker compose -f "$COMPOSE_FILE" stop api
    
    # Restore database
    if [[ "$BACKUP_FILE" == *.tar.gz ]]; then
        tar -xzf "$BACKUP_FILE" -C backups/
        DB_FILE=$(tar -tzf "$BACKUP_FILE" | grep '\.db$' | head -1)
        docker cp "backups/$DB_FILE" bokfoering-api:/app/data/bokfoering.db
        rm "backups/$DB_FILE"
    else
        docker cp "$BACKUP_FILE" bokfoering-api:/app/data/bokfoering.db
    fi
    
    # Start services
    docker compose -f "$COMPOSE_FILE" start api
    
    log_info "Restore completed!"
}

# Show logs
logs() {
    SERVICE=${1:-api}
    docker logs -f "bokfoering-$SERVICE"
}

# Show status
status() {
    docker compose -f "$COMPOSE_FILE" ps
}

# Stop everything
stop() {
    log_info "Stopping all services..."
    docker compose -f "$COMPOSE_FILE" down
    log_info "All services stopped."
}

# Main menu
case "${1:-deploy}" in
    deploy)
        check_prerequisites
        deploy
        health_check
        ;;
    update)
        check_prerequisites
        update
        health_check
        ;;
    backup)
        backup
        ;;
    restore)
        restore "$2"
        ;;
    logs)
        logs "$2"
        ;;
    status)
        status
        ;;
    stop)
        stop
        ;;
    health)
        health_check
        ;;
    *)
        echo "Usage: ./deploy.sh [command]"
        echo ""
        echo "Commands:"
        echo "  deploy      - Deploy or redeploy all services (default)"
        echo "  update      - Pull latest code and update"
        echo "  backup      - Create database backup"
        echo "  restore     - Restore from backup file"
        echo "  logs [svc]  - Show logs (svc: api, frontend, traefik)"
        echo "  status      - Show service status"
        echo "  stop        - Stop all services"
        echo "  health      - Run health checks"
        echo ""
        echo "Examples:"
        echo "  ./deploy.sh                    # Deploy everything"
        echo "  ./deploy.sh backup             # Create backup"
        echo "  ./deploy.sh restore backups/bokfoering_backup_20240101.tar.gz"
        echo "  ./deploy.sh logs api           # Show API logs"
        exit 1
        ;;
esac