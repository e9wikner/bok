# Terraform Deployment for Hetzner Cloud

Infrastructure as Code (IaC) deployment for Bokföringssystem on Hetzner Cloud.

## Prerequisites

1. **Terraform** (v1.0+)
   ```bash
   # macOS
   brew install terraform
   
   # Linux
   wget https://releases.hashicorp.com/terraform/1.7.0/terraform_1.7.0_linux_amd64.zip
   unzip terraform_1.7.0_linux_amd64.zip
   sudo mv terraform /usr/local/bin/
   ```

2. **Hetzner Cloud Account**
   - Sign up at https://console.hetzner.cloud/
   - Create a project
   - Generate API token: Project → Security → API Tokens

3. **SSH Key**
   ```bash
   ssh-keygen -t rsa -b 4096 -C "your-email@example.com"
   cat ~/.ssh/id_rsa.pub
   ```

## Quick Start

### 1. Configure Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
nano terraform.tfvars
```

### 2. Initialize Terraform

```bash
terraform init
```

### 3. Plan Deployment

```bash
terraform plan
```

Review the changes before applying.

### 4. Deploy Infrastructure

```bash
terraform apply
```

Type `yes` to confirm.

### 5. Get Server Details

```bash
terraform output
```

Example output:
```
floating_ip = "78.46.xxx.xxx"
server_id = "12345678"
server_ip = "78.46.xxx.xxx"
ssh_command = "ssh root@78.46.xxx.xxx"
```

### 6. Deploy Application

Wait ~2 minutes for cloud-init to complete, then:

```bash
# SSH to server
ssh root@$(terraform output -raw floating_ip)

# Clone repository
git clone https://github.com/e9wikner/bok.git
cd bok

# Create production config
cat > .env.production << 'EOF'
API_KEY=your-secure-production-key
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
NEXT_PUBLIC_API_KEY=your-secure-production-key
EOF

# Deploy with Docker
docker compose -f docker-compose.prod.yml up -d
```

## Server Types

| Type | vCPUs | RAM | Storage | Price/Month | Use Case |
|------|-------|-----|---------|-------------|----------|
| cx21 | 2 | 4 GB | 40 GB | €6.72 | Small teams, testing |
| cpx21 | 2 | 4 GB | 80 GB NVMe | €8.22 | Small production |
| **cpx31** | **4** | **8 GB** | **160 GB NVMe** | **€14.76** | **Recommended** |
| cpx41 | 8 | 16 GB | 240 GB NVMe | €29.52 | Large production |

## Locations

- `fsn1` - Falkenstein, Germany (recommended for EU)
- `nbg1` - Nuremberg, Germany
- `hel1` - Helsinki, Finland
- `ash` - Ashburn, Virginia, USA

## Commands Reference

```bash
# Show current state
terraform show

# Refresh state
terraform refresh

# Destroy infrastructure (DANGER!)
terraform destroy

# Taint resource (force recreation)
terraform taint hcloud_server.bokfoering
terraform apply

# View outputs
terraform output
terraform output -raw server_ip
```

## Updating Infrastructure

### Scale Up/Down

Edit `terraform.tfvars`:
```hcl
server_type = "cpx41"  # Upgrade from cpx31
```

Then apply:
```bash
terraform apply
```

**Note:** This will cause a brief downtime (~1-2 minutes).

### Add More Resources

Edit `main.tf` to add:
- Additional servers (load balancing)
- More volumes
- Load balancers
- Private networks

## State Management

### Local State (Default)

State stored in `terraform.tfstate`. **Never commit this file!**

Add to `.gitignore`:
```
terraform.tfstate
terraform.tfstate.*
.terraform/
terraform.tfvars
```

### Remote State (Recommended for Teams)

Use S3-compatible storage:

```hcl
terraform {
  backend "s3" {
    bucket = "your-terraform-state-bucket"
    key    = "bokfoering/terraform.tfstate"
    region = "eu-central-1"
    
    # For non-AWS S3 (like Hetzner Object Storage)
    endpoints = {
      s3 = "https://nbg1.your-objectstorage.com"
    }
  }
}
```

## Security

### Firewall Rules

The Terraform configuration creates a firewall with these rules:

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Any | SSH access |
| 80 | TCP | Any | HTTP (redirects to HTTPS) |
| 443 | TCP | Any | HTTPS (app traffic) |

### Best Practices

1. **Restrict SSH Access**
   Edit `main.tf`:
   ```hcl
   rule {
     direction  = "in"
     protocol   = "tcp"
     port       = "22"
     source_ips = ["YOUR_HOME_IP/32"]  # Restrict to your IP
   }
   ```

2. **Use SSH Keys Only**
   - Password authentication is disabled by cloud-init
   - Only SSH keys configured in Hetzner Console work

3. **Enable Backups**
   Add to server resource:
   ```hcl
   backup_window = "22:00-02:00"
   ```

## Troubleshooting

### SSH Connection Refused

Wait for cloud-init to complete (~2 minutes):
```bash
ssh root@$(terraform output -raw floating_ip) 'cat /opt/bokfoering/.setup-complete'
```

### Terraform Apply Fails

1. Check API token:
   ```bash
   export HCLOUD_TOKEN="your-token"
   ```

2. Verify SSH key format:
   ```bash
   ssh-keygen -l -f ~/.ssh/id_rsa.pub
   ```

### Server Not Accessible

1. Check firewall rules in Hetzner Console
2. Verify cloud-init completed:
   ```bash
   ssh root@IP 'tail -f /var/log/cloud-init-output.log'
   ```

## Cost Estimation

Monthly costs (Hetzner Cloud):

| Component | Cost |
|-----------|------|
| Server (cpx31) | €14.76 |
| Volume (50 GB) | €2.50 |
| Floating IP | €1.00 |
| **Total** | **~€18.26/month** |

Traffic:
- 20 TB outbound included
- €1.00/TB after that

## Migration from Existing Server

1. Backup data from old server:
   ```bash
   docker exec bokfoering-api sqlite3 /app/data/bokfoering.db ".backup '/app/data/backup.db'"
   docker cp bokfoering-api:/app/data/backup.db ./
   ```

2. Deploy new infrastructure with Terraform

3. Restore data:
   ```bash
   docker cp backup.db bokfoering-api:/app/data/bokfoering.db
   ```

## Support

- Hetzner Cloud Docs: https://docs.hetzner.cloud/
- Terraform Hetzner Provider: https://registry.terraform.io/providers/hetznercloud/hcloud/latest/docs
- GitHub Issues: https://github.com/e9wikner/bok/issues