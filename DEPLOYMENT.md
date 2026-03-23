# Deployment Guide

Complete guide for deploying the Bokföringssystem to on-premise servers or Hetzner Cloud.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Docker Deployment (On-Premise)](#docker-deployment-on-premise)
3. [Hetzner Cloud Deployment](#hetzner-cloud-deployment)
4. [SSL/TLS Configuration](#ssltls-configuration)
5. [Environment Variables](#environment-variables)
6. [Monitoring & Logging](#monitoring--logging)
7. [Backup Strategy](#backup-strategy)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

**Minimum (Development/Test):**
- CPU: 2 cores
- RAM: 4 GB
- Storage: 20 GB SSD
- OS: Ubuntu 22.04 LTS / Debian 12 / CentOS 9

**Recommended (Production):**
- CPU: 4+ cores
- RAM: 8+ GB
- Storage: 50+ GB SSD
- OS: Ubuntu 22.04 LTS

### Required Software

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose (v2)
sudo apt-get update
sudo apt-get install -y docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### Domain & DNS

- Domain name pointed to server IP
- Subdomains configured:
  - `api.yourdomain.com` → Backend API
  - `app.yourdomain.com` → Frontend v2
  - `docs.yourdomain.com` → API documentation (optional)

---

## Docker Deployment (On-Premise)

### 1. Clone Repository

```bash
git clone https://github.com/e9wikner/bok.git
cd bok
```

### 2. Configure Environment

Create production environment file:

```bash
cat > .env.production << 'EOF'
# API Configuration
API_KEY=your-secure-api-key-change-this
DATABASE_URL=sqlite:////app/data/bokfoering.db
DEBUG=False

# Frontend Configuration
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_API_KEY=your-secure-api-key-change-this

# Security
CORS_ORIGINS=https://app.yourdomain.com,https://yourdomain.com
EOF
```

### 3. Update Docker Compose for Production

Create `docker-compose.prod.yml`:

```yaml
services:
  # Reverse Proxy (Traefik)
  traefik:
    image: traefik:v3.0
    container_name: traefik
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=admin@yourdomain.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt
    restart: unless-stopped

  # Backend API
  api:
    build: .
    container_name: bokfoering-api
    env_file:
      - .env.production
    volumes:
      - bokfoering-data:/app/data
      - ./backups:/app/backups
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=Host(`api.yourdomain.com`)"
      - "traefik.http.routers.api.entrypoints=websecure"
      - "traefik.http.routers.api.tls.certresolver=letsencrypt"
      - "traefik.http.services.api.loadbalancer.server.port=8000"
    command: sh -c "python main.py --init-db && python main.py --host 0.0.0.0 --port 8000"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Frontend v2 (Next.js)
  frontend:
    build: ./frontend-v3
    container_name: bokfoering-frontend
    env_file:
      - .env.production
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.frontend.rule=Host(`app.yourdomain.com`)"
      - "traefik.http.routers.frontend.entrypoints=websecure"
      - "traefik.http.routers.frontend.tls.certresolver=letsencrypt"
      - "traefik.http.services.frontend.loadbalancer.server.port=3000"
    restart: unless-stopped
    depends_on:
      - api

  # Database Backup Service
  backup:
    image: offen/docker-volume-backup:latest
    container_name: backup
    environment:
      BACKUP_CRON_EXPRESSION: "0 2 * * *"  # Daily at 2 AM
      BACKUP_RETENTION_DAYS: "30"
      AWS_S3_BUCKET_NAME: your-backup-bucket
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}
      AWS_S3_ENDPOINT: s3.eu-central-1.amazonaws.com
    volumes:
      - bokfoering-data:/backup/data:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped

volumes:
  bokfoering-data:
    driver: local
```

### 4. Deploy

```bash
# Create required directories
mkdir -p letsencrypt backups

# Set proper permissions
chmod 600 .env.production
chmod 600 letsencrypt

# Deploy
docker compose -f docker-compose.prod.yml up -d

# Check status
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f
```

### 5. Verify Deployment

```bash
# Test API
curl https://api.yourdomain.com/health

# Test Frontend
curl https://app.yourdomain.com

# View logs
docker logs bokfoering-api
docker logs bokfoering-frontend
```

---

## Hetzner Cloud Deployment

### Option 1: Hetzner Cloud Console (Manual)

#### Step 1: Create Server

1. Log in to [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Create new project (e.g., "bokfoering")
3. Click "Add Server"
4. Configuration:
   - **Location:** Falkenstein (fsn1) or Nuremberg (nbg1)
   - **Image:** Ubuntu 22.04
   - **Type:** CPX31 (4 vCPUs, 8 GB RAM, 160 GB NVMe) - €14.76/month
   - **Networking:** Enable IPv4 & IPv6
   - **Firewalls:** Create new firewall (see below)
   - **SSH Key:** Add your SSH public key
   - **Name:** bokfoering-prod

#### Step 2: Configure Firewall

Create firewall rules:

| Direction | Protocol | Port | Source | Description |
|-----------|----------|------|--------|-------------|
| In | TCP | 22 | Your IP | SSH Access |
| In | TCP | 80 | Any | HTTP |
| In | TCP | 443 | Any | HTTPS |
| Out | Any | Any | Any | All outbound |

#### Step 3: Connect & Deploy

```bash
# SSH to server
ssh root@your-server-ip

# Update system
apt-get update && apt-get upgrade -y

# Install Docker (see Prerequisites section)
# Then follow Docker Deployment steps above
```

### Option 2: Hetzner Cloud API (Automated)

Create deployment script:

```bash
#!/bin/bash
# deploy-hetzner.sh

set -e

# Configuration
HCLOUD_TOKEN=${HCLOUD_TOKEN:-"your-hetzner-api-token"}
SERVER_NAME=${SERVER_NAME:-"bokfoering-prod"}
SERVER_TYPE=${SERVER_TYPE:-"cpx31"}  # 4 vCPUs, 8 GB RAM
LOCATION=${LOCATION:-"fsn1"}  # Falkenstein
SSH_KEY_NAME=${SSH_KEY_NAME:-"your-ssh-key-name"}

# Install hcloud CLI if not present
if ! command -v hcloud &> /dev/null; then
    curl -fsSL https://github.com/hetznercloud/cli/releases/latest/download/hcloud-linux-amd64.tar.gz | tar -xzf - -C /usr/local/bin
fi

# Authenticate
hcloud context create bokfoering

# Create server
echo "Creating server..."
hcloud server create \
    --name "$SERVER_NAME" \
    --type "$SERVER_TYPE" \
    --image ubuntu-22.04 \
    --location "$LOCATION" \
    --ssh-key "$SSH_KEY_NAME" \
    --label environment=production \
    --label app=bokfoering

# Get server IP
SERVER_IP=$(hcloud server ip "$SERVER_NAME")
echo "Server created with IP: $SERVER_IP"

# Wait for server to be ready
sleep 30

# Copy deployment files
echo "Copying deployment files..."
scp -o StrictHostKeyChecking=no -r . root@$SERVER_IP:/root/bokfoering/

# Run deployment
echo "Running deployment..."
ssh -o StrictHostKeyChecking=no root@$SERVER_IP << 'REMOTE_SCRIPT'
cd /root/bokfoering

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Deploy
docker compose -f docker-compose.prod.yml up -d

# Setup firewall (alternative to Hetzner Cloud Firewall)
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

REMOTE_SCRIPT

echo "Deployment complete!"
echo "Frontend: https://app.yourdomain.com"
echo "API: https://api.yourdomain.com"
```

Make executable and run:

```bash
chmod +x deploy-hetzner.sh
export HCLOUD_TOKEN="your-hetzner-api-token"
./deploy-hetzner.sh
```

### Option 3: Terraform (Infrastructure as Code)

Create `main.tf`:

```hcl
terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }
}

variable "hcloud_token" {
  description = "Hetzner Cloud API Token"
  type        = string
  sensitive   = true
}

variable "ssh_public_key" {
  description = "SSH Public Key"
  type        = string
}

provider "hcloud" {
  token = var.hcloud_token
}

# SSH Key
resource "hcloud_ssh_key" "default" {
  name       = "bokfoering-ssh-key"
  public_key = var.ssh_public_key
}

# Firewall
resource "hcloud_firewall" "bokfoering" {
  name = "bokfoering-firewall"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

# Server
resource "hcloud_server" "bokfoering" {
  name        = "bokfoering-prod"
  server_type = "cpx31"  # 4 vCPUs, 8 GB RAM
  image       = "ubuntu-22.04"
  location    = "fsn1"   # Falkenstein
  ssh_keys    = [hcloud_ssh_key.default.id]
  firewall_ids = [hcloud_firewall.bokfoering.id]

  labels = {
    environment = "production"
    app         = "bokfoering"
  }
}

# Volume for data persistence
resource "hcloud_volume" "data" {
  name      = "bokfoering-data"
  size      = 50
  server_id = hcloud_server.bokfoering.id
  format    = "ext4"
}

output "server_ip" {
  value = hcloud_server.bokfoering.ipv4_address
}

output "server_id" {
  value = hcloud_server.bokfoering.id
}
```

Create `variables.tf`:

```hcl
variable "hcloud_token" {}
variable "ssh_public_key" {}
```

Deploy:

```bash
# Initialize
terraform init

# Plan
terraform plan -var="hcloud_token=$HCLOUD_TOKEN" -var="ssh_public_key=$(cat ~/.ssh/id_rsa.pub)"

# Apply
terraform apply -var="hcloud_token=$HCLOUD_TOKEN" -var="ssh_public_key=$(cat ~/.ssh/id_rsa.pub)"

# Get IP
terraform output server_ip
```

---

## SSL/TLS Configuration

### Let's Encrypt (Automatic)

With Traefik (included in docker-compose.prod.yml), SSL certificates are automatically obtained and renewed.

### Custom SSL Certificate

If using your own certificates:

```yaml
# docker-compose.prod.yml modification
  traefik:
    volumes:
      - ./certs:/certs:ro
    command:
      - "--entrypoints.websecure.http.tls.certificates.certFile=/certs/cert.pem"
      - "--entrypoints.websecure.http.tls.certificates.keyFile=/certs/key.pem"
```

Place certificates in `./certs/` directory.

---

## Environment Variables

### Production Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `API_KEY` | API authentication key | `sk-live-xxxxxxxxxxxx` |
| `DATABASE_URL` | SQLite database path | `sqlite:////app/data/bokfoering.db` |
| `DEBUG` | Debug mode | `False` |
| `NEXT_PUBLIC_API_URL` | Backend API URL | `https://api.yourdomain.com` |
| `NEXT_PUBLIC_API_KEY` | Frontend API key | Same as API_KEY |
| `CORS_ORIGINS` | Allowed CORS origins | `https://app.yourdomain.com` |

### Security Checklist

- [ ] Change default API_KEY
- [ ] Enable firewall (only ports 22, 80, 443)
- [ ] Disable SSH password authentication
- [ ] Enable automatic security updates
- [ ] Configure backups
- [ ] Setup monitoring
- [ ] Enable HTTPS only

---

## Monitoring & Logging

### Setup Prometheus + Grafana (Optional)

Add to `docker-compose.prod.yml`:

```yaml
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    ports:
      - "9090:9090"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    volumes:
      - grafana-data:/var/lib/grafana
      - ./monitoring/grafana-dashboards:/etc/grafana/provisioning/dashboards
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
    ports:
      - "3001:3000"
    restart: unless-stopped

volumes:
  prometheus-data:
  grafana-data:
```

### Log Aggregation

```bash
# View all logs
docker compose -f docker-compose.prod.yml logs -f

# View specific service
docker logs -f bokfoering-api

# Save logs to file
docker logs bokfoering-api > api-$(date +%Y%m%d).log 2>&1
```

---

## Backup Strategy

### Automated Backups

The docker-compose.prod.yml includes automated backups to S3-compatible storage.

Configure in `.env.production`:

```bash
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_S3_BUCKET_NAME=bokfoering-backups
AWS_S3_ENDPOINT=s3.eu-central-1.amazonaws.com
```

### Manual Backup

```bash
# Create backup
docker exec bokfoering-api python -c "
import shutil
from datetime import datetime
backup_name = f'/app/backups/bokfoering-{datetime.now().strftime('%Y%m%d_%H%M%S')}.db'
shutil.copy('/app/data/bokfoering.db', backup_name)
print(f'Backup created: {backup_name}')
"

# Copy from container
docker cp bokfoering-api:/app/backups/ ./backups/
```

### Restore from Backup

```bash
# Stop services
docker compose -f docker-compose.prod.yml down

# Restore database
cp /path/to/backup.db ./data/bokfoering.db

# Start services
docker compose -f docker-compose.prod.yml up -d
```

---

## Troubleshooting

### Common Issues

#### 1. Container won't start

```bash
# Check logs
docker logs bokfoering-api

# Check for port conflicts
sudo netstat -tulpn | grep :8000

# Restart service
docker compose -f docker-compose.prod.yml restart api
```

#### 2. SSL Certificate Issues

```bash
# Check Traefik logs
docker logs traefik

# Verify DNS
dig +short api.yourdomain.com

# Force certificate renewal
docker exec traefik rm /letsencrypt/acme.json
docker compose -f docker-compose.prod.yml restart traefik
```

#### 3. Database Locked

```bash
# Check for locks
docker exec bokfoering-api ls -la /app/data/

# Fix permissions
docker exec bokfoering-api chown -R 1000:1000 /app/data/
```

#### 4. Frontend Build Fails

```bash
# Rebuild frontend
docker compose -f docker-compose.prod.yml build --no-cache frontend
docker compose -f docker-compose.prod.yml up -d frontend
```

### Health Checks

```bash
# API health
curl -f https://api.yourdomain.com/health || echo "API unhealthy"

# Frontend health
curl -f https://app.yourdomain.com || echo "Frontend unhealthy"

# Database
docker exec bokfoering-api sqlite3 /app/data/bokfoering.db ".tables"
```

### Performance Tuning

For high-traffic deployments:

```yaml
# Add to docker-compose.prod.yml
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

---

## Maintenance

### Regular Updates

```bash
# Update system packages
apt-get update && apt-get upgrade -y

# Update Docker images
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# Clean up old images
docker system prune -f
```

### SSL Certificate Renewal

With Traefik: Automatic

Manual check:
```bash
openssl s_client -connect api.yourdomain.com:443 -servername api.yourdomain.com < /dev/null 2>/dev/null | openssl x509 -noout -dates
```

---

## Support

For deployment issues:
1. Check logs: `docker logs <container-name>`
2. Review GitHub Issues: https://github.com/e9wikner/bok/issues
3. Hetzner Cloud Docs: https://docs.hetzner.com/
4. Traefik Docs: https://doc.traefik.io/

---

**Last Updated:** 2026-03-22
**Version:** 1.0