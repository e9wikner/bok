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

variable "domain" {
  description = "Domain name for the application"
  type        = string
  default     = "yourdomain.com"
}

variable "server_type" {
  description = "Hetzner server type"
  type        = string
  default     = "cpx31"  # 4 vCPUs, 8 GB RAM
}

variable "location" {
  description = "Hetzner datacenter location"
  type        = string
  default     = "fsn1"  # Falkenstein
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
    description = "SSH"
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
    description = "HTTP"
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
    description = "HTTPS"
  }
}

# Primary Server
resource "hcloud_server" "bokfoering" {
  name        = "bokfoering-prod"
  server_type = var.server_type
  image       = "ubuntu-22.04"
  location    = var.location
  ssh_keys    = [hcloud_ssh_key.default.id]
  firewall_ids = [hcloud_firewall.bokfoering.id]

  labels = {
    environment = "production"
    app         = "bokfoering"
    managed_by  = "terraform"
  }

  # User data for initial setup
  user_data = <<-EOF
    #!/bin/bash
    set -e

    # Update system
    apt-get update
    apt-get upgrade -y

    # Install Docker
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    usermod -aG docker root

    # Install Docker Compose
    apt-get install -y docker-compose-plugin

    # Create app directory
    mkdir -p /opt/bokfoering
    cd /opt/bokfoering

    # Setup completed marker
    touch /opt/bokfoering/.setup-complete

    echo "Server setup completed at $(date)"
  EOF
}

# Volume for data persistence
resource "hcloud_volume" "data" {
  name      = "bokfoering-data"
  size      = 50
  server_id = hcloud_server.bokfoering.id
  format    = "ext4"
  delete_protection = true
}

# Floating IP (optional, for easier DNS management)
resource "hcloud_floating_ip" "main" {
  type      = "ipv4"
  server_id = hcloud_server.bokfoering.id
  name      = "bokfoering-ip"
}

# DNS Records (if using Hetzner DNS)
# resource "hcloud_dns_record" "api" {
#   zone_id = var.dns_zone_id
#   name    = "api"
#   value   = hcloud_floating_ip.main.ip_address
#   type    = "A"
#   ttl     = 3600
# }

# resource "hcloud_dns_record" "app" {
#   zone_id = var.dns_zone_id
#   name    = "app"
#   value   = hcloud_floating_ip.main.ip_address
#   type    = "A"
#   ttl     = 3600
# }

# Outputs
output "server_ip" {
  description = "Server IPv4 address"
  value       = hcloud_server.bokfoering.ipv4_address
}

output "floating_ip" {
  description = "Floating IP address"
  value       = hcloud_floating_ip.main.ip_address
}

output "server_id" {
  description = "Hetzner server ID"
  value       = hcloud_server.bokfoering.id
}

output "volume_id" {
  description = "Data volume ID"
  value       = hcloud_volume.data.id
}

output "ssh_command" {
  description = "SSH command to connect"
  value       = "ssh root@${hcloud_floating_ip.main.ip_address}"
}