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

For local development, see [DOCKER.md](DOCKER.md).

---

## Prerequisites

### System Requirements

**Minimum (Development/Test):**
- CPU: 2 cores
- RAM: 4 GB
- Storage: 20 GB SSD
- OS: Ubuntu 22.04 LTS / Debian 12

**Recommended (Production):**
- CPU: 4+ cores
- RAM: 8+ GB
- Storage: 50+ GB SSD
- OS: Ubuntu 24.04 LTS

### Required Software

```bash
# Install prerequisites
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Add Docker's GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Allow running Docker without sudo
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker compose version
```

### Domain & DNS

- Domain name pointed to your server IP
- Subdomains configured:
  - `app.yourdomain.com` → Frontend (primary UI)
  - `api.yourdomain.com` → Backend API

---

## Docker Deployment (On-Premise)

### 1. Configure Firewall

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
sudo ufw status
```

### 2. Clone Repository

```bash
git clone https://github.com/e9wikner/bok.git /opt/bokfoering
cd /opt/bokfoering
```

### 3. Configure Environment

```bash
cp .env.example .env.production
```

Edit `.env.production` with production values:

```bash
# Generate strong secrets
openssl rand -hex 32   # for BOKFOERING_API_KEY
openssl rand -hex 24   # for POSTGRES_PASSWORD
```

```env
# .env.production

# API
BOKFOERING_API_KEY=<your-generated-api-key>
DEBUG=False
LOG_LEVEL=INFO

# Database (PostgreSQL recommended for production)
DATABASE_URL=postgresql://bokfoering:<db-password>@postgres:5432/bokfoering
POSTGRES_DB=bokfoering
POSTGRES_USER=bokfoering
POSTGRES_PASSWORD=<your-generated-db-password>

# Domains
API_DOMAIN=api.yourdomain.com
APP_DOMAIN=app.yourdomain.com
LETSENCRYPT_EMAIL=admin@yourdomain.com

# Frontend
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_API_KEY=<your-generated-api-key>
```

```bash
chmod 600 .env.production
```

### 4. Deploy

```bash
# Create required directories
mkdir -p letsencrypt backups logs

# Deploy (Traefik will automatically obtain SSL certificates)
docker compose -f docker-compose.prod.yml --env-file .env.production up -d

# Check status
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f
```

### 5. Verify Deployment

```bash
# API health check
curl https://api.yourdomain.com/health
# Expected: {"status": "ok", "service": "bokfoering-api", "version": "0.1.0"}

# Frontend
curl -I https://app.yourdomain.com
```

### 6. Auto-Start on Reboot (systemd)

```bash
sudo tee /etc/systemd/system/bokfoering.service > /dev/null <<EOF
[Unit]
Description=Bokföringssystem
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/bokfoering
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml --env-file .env.production up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable bokfoering
```

---

## Hetzner Cloud Deployment

### Option 1: Hetzner Cloud Console (Manual)

#### Step 1: Create Server

1. Log in to [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Create a new project (e.g., `bokfoering-prod`)
3. Go to **Security → SSH Keys → Add SSH Key** and paste your public key
4. Click **Servers → Add Server** with this configuration:
   - **Location:** Falkenstein (`fsn1`) or Helsinki (`hel1`)
   - **Image:** Ubuntu 24.04
   - **Type:** `CX22` (2 vCPU, 4 GB RAM, ~€4/mo) for small deployments; `CX32` (4 vCPU, 8 GB) for production
   - **SSH Key:** Select the key you added
   - **Firewall:** Create new (see below)

#### Step 2: Configure Firewall

| Direction | Protocol | Port | Source | Description |
|-----------|----------|------|--------|-------------|
| Inbound | TCP | 22 | Your IP | SSH |
| Inbound | TCP | 80 | Any | HTTP |
| Inbound | TCP | 443 | Any | HTTPS |
| Outbound | Any | Any | Any | All outbound |

#### Step 3: (Optional) Add a Floating IP

A Floating IP stays stable across server replacements:

1. Go to **Floating IPs → Create Floating IP**
2. Assign it to your server
3. Point your domain's DNS A record to this IP

#### Step 4: (Optional) Add a Hetzner Volume

For production, store database data on a dedicated volume:

1. Go to **Volumes → Create Volume** (20–50 GB)
2. Attach to your server with auto-mount enabled
3. Update `docker-compose.prod.yml` to use the volume path:
   ```yaml
   postgres:
     volumes:
       - /mnt/HC_Volume_<id>/postgres:/var/lib/postgresql/data
   ```

#### Step 5: Connect & Deploy

```bash
# SSH to server
ssh root@<server-ip>

# Update system
apt-get update && apt-get upgrade -y

# Install Docker (see Prerequisites section above)
# Then follow Docker Deployment steps above
```

---

### Option 2: Hetzner Cloud API (Automated)

```bash
#!/bin/bash
# deploy-hetzner.sh
set -e

HCLOUD_TOKEN=${HCLOUD_TOKEN:-"your-hetzner-api-token"}
SERVER_NAME=${SERVER_NAME:-"bokfoering-prod"}
SERVER_TYPE=${SERVER_TYPE:-"cx32"}
LOCATION=${LOCATION:-"fsn1"}
SSH_KEY_NAME=${SSH_KEY_NAME:-"your-ssh-key-name"}

# Install hcloud CLI if not present
if ! command -v hcloud &> /dev/null; then
    curl -fsSL https://github.com/hetznercloud/cli/releases/latest/download/hcloud-linux-amd64.tar.gz \
      | tar -xzf - -C /usr/local/bin
fi

hcloud context create bokfoering

# Create server
hcloud server create \
    --name "$SERVER_NAME" \
    --type "$SERVER_TYPE" \
    --image ubuntu-24.04 \
    --location "$LOCATION" \
    --ssh-key "$SSH_KEY_NAME" \
    --label environment=production \
    --label app=bokfoering

SERVER_IP=$(hcloud server ip "$SERVER_NAME")
echo "Server created with IP: $SERVER_IP"

sleep 30

# Copy repo and deploy
scp -o StrictHostKeyChecking=no -r . root@$SERVER_IP:/opt/bokfoering/
ssh -o StrictHostKeyChecking=no root@$SERVER_IP << 'REMOTE'
cd /opt/bokfoering

# Install Docker
curl -fsSL https://get.docker.com | sh

# Firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Deploy
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
REMOTE

echo "Deployment complete!"
echo "Frontend: https://$APP_DOMAIN"
echo "API:      https://$API_DOMAIN"
```

```bash
chmod +x deploy-hetzner.sh
export HCLOUD_TOKEN="your-hetzner-api-token"
./deploy-hetzner.sh
```

---

### Option 3: Terraform (Infrastructure as Code)

See [`terraform/`](terraform/) for the full Terraform configuration. Quick start:

```bash
cd terraform

# Initialize
terraform init

# Plan
terraform plan \
  -var="hcloud_token=$HCLOUD_TOKEN" \
  -var="ssh_public_key=$(cat ~/.ssh/id_ed25519.pub)"

# Apply
terraform apply \
  -var="hcloud_token=$HCLOUD_TOKEN" \
  -var="ssh_public_key=$(cat ~/.ssh/id_ed25519.pub)"

# Get server IP
terraform output server_ip
```

---

## SSL/TLS Configuration

SSL certificates are **automatically obtained and renewed** by Traefik using Let's Encrypt. No manual steps are needed as long as:
- Your domain's DNS A record points to the server IP
- Ports 80 and 443 are open
- `LETSENCRYPT_EMAIL` is set in `.env.production`

### Check Certificate Status

```bash
openssl s_client -connect api.yourdomain.com:443 -servername api.yourdomain.com \
  < /dev/null 2>/dev/null | openssl x509 -noout -dates
```

### Custom SSL Certificate

If using your own certificate instead of Let's Encrypt, place the files in `./certs/` and update the Traefik config in `docker-compose.prod.yml`:

```yaml
traefik:
  volumes:
    - ./certs:/certs:ro
  command:
    - "--entrypoints.websecure.http.tls.certificates.certFile=/certs/cert.pem"
    - "--entrypoints.websecure.http.tls.certificates.keyFile=/certs/key.pem"
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOKFOERING_API_KEY` | Yes | API auth key. Generate: `openssl rand -hex 32` |
| `DEBUG` | No | Always `False` in production |
| `DATABASE_URL` | Yes | PostgreSQL: `postgresql://user:pass@postgres:5432/db` |
| `POSTGRES_DB` | Yes | Database name (default: `bokfoering`) |
| `POSTGRES_USER` | Yes | Database user (default: `bokfoering`) |
| `POSTGRES_PASSWORD` | Yes | Database password. Generate: `openssl rand -hex 24` |
| `API_DOMAIN` | Yes | API subdomain (e.g., `api.yourdomain.com`) |
| `APP_DOMAIN` | Yes | Frontend subdomain (e.g., `app.yourdomain.com`) |
| `LETSENCRYPT_EMAIL` | Yes | Email for Let's Encrypt notifications |
| `NEXT_PUBLIC_API_URL` | Yes | Full API URL used by frontend |
| `NEXT_PUBLIC_API_KEY` | Yes | Same as `BOKFOERING_API_KEY` |
| `LOG_LEVEL` | No | `INFO` (default), `DEBUG`, `WARNING`, `ERROR` |
| `ENABLE_VAT_REPORTING` | No | Default: `True` |
| `ENABLE_K2_EXPORT` | No | Default: `True` |

### Security Checklist

- [ ] Generate unique `BOKFOERING_API_KEY` (never use the default)
- [ ] Generate unique `POSTGRES_PASSWORD`
- [ ] Set `DEBUG=False`
- [ ] Enable firewall (ports 22, 80, 443 only)
- [ ] Disable SSH password authentication (`PasswordAuthentication no` in `/etc/ssh/sshd_config`)
- [ ] Enable automatic OS security updates
- [ ] Configure automated backups (see below)
- [ ] Set up uptime monitoring

---

## Monitoring & Logging

### View Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# API only
docker compose -f docker-compose.prod.yml logs -f api

# Save logs to file
docker logs bokfoering-api > api-$(date +%Y%m%d).log 2>&1
```

### Health Check Endpoint

```bash
curl https://api.yourdomain.com/health
# {"status": "ok", "service": "bokfoering-api", "version": "0.1.0"}
```

### Uptime Monitoring

Use a free service like [UptimeRobot](https://uptimerobot.com) or [Freshping](https://www.freshworks.com/website-monitoring/) pointing at `https://api.yourdomain.com/health` with a 5-minute interval.

### Prometheus + Grafana (Optional)

Uncomment the `prometheus` and `grafana` sections in `docker-compose.prod.yml` and add a `monitoring/prometheus.yml` config.

---

## Backup Strategy

> **BFL compliance:** Swedish bookkeeping law (Bokföringslagen) requires accounting records to be retained for **7 years**. Ensure backups are configured accordingly.

### Automated Backups (Included)

The `backup` service in `docker-compose.prod.yml` runs daily at 2 AM and stores archives in `./backups/`. To configure off-site storage (Hetzner Object Storage, AWS S3, etc.), uncomment and set the `AWS_*` variables in `.env.production`.

### PostgreSQL Dump Script

```bash
sudo tee /opt/bokfoering/scripts/pg-backup.sh > /dev/null <<'EOF'
#!/bin/bash
set -e
BACKUP_DIR="/opt/bokfoering/backups"
DATE=$(date +%Y-%m-%d_%H-%M-%S)
mkdir -p "$BACKUP_DIR"

docker exec bokfoering-postgres pg_dump \
  -U bokfoering bokfoering | gzip > "$BACKUP_DIR/bokfoering_$DATE.sql.gz"

echo "Backup saved: bokfoering_$DATE.sql.gz"

# Retain 7 years (2555 days) — required by BFL
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +2555 -delete
EOF
chmod +x /opt/bokfoering/scripts/pg-backup.sh

# Add daily cron job
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/bokfoering/scripts/pg-backup.sh >> /var/log/bokfoering-backup.log 2>&1") | crontab -
```

### Restore from Backup

```bash
# Stop services
docker compose -f docker-compose.prod.yml down

# Restore PostgreSQL
gunzip -c /path/to/bokfoering_<date>.sql.gz | \
  docker exec -i bokfoering-postgres psql -U bokfoering bokfoering

# Start services
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

### Hetzner Snapshots

In addition to database backups, take full-server snapshots before major changes:

1. Hetzner Console → **Servers → your server → Snapshots → Create Snapshot**
2. Or enable **Automatic Backups** (daily, last 7 retained, 20% of server price)

---

## Troubleshooting

### Container won't start

```bash
docker logs bokfoering-api
sudo ss -tlnp | grep -E ':80|:443'  # Check for port conflicts
docker compose -f docker-compose.prod.yml restart api
```

### SSL Certificate Issues

```bash
# Check Traefik logs
docker logs traefik

# Verify DNS resolves to your server
dig +short api.yourdomain.com

# Force certificate renewal
docker exec traefik rm /letsencrypt/acme.json
docker compose -f docker-compose.prod.yml restart traefik
```

### API returns 502 Bad Gateway

The API may still be initializing (up to 40 seconds on first start with DB migration):

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs api
```

### Database Connection Refused

```bash
docker compose -f docker-compose.prod.yml logs postgres
```

Wait for `database system is ready to accept connections` before the API starts.

### Out of Disk Space

```bash
df -h
docker system prune -f
```

---

## Maintenance

### Updating

```bash
cd /opt/bokfoering
git pull origin main

docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

# Clean up old images
docker system prune -f
```

### OS Security Updates

```bash
apt-get update && apt-get upgrade -y
```

---

## Support

- GitHub Issues: https://github.com/e9wikner/bok/issues
- Hetzner Cloud Docs: https://docs.hetzner.com/
- Traefik Docs: https://doc.traefik.io/
- Docker Docs: https://docs.docker.com/
