variable "hcloud_token" {
  description = "Hetzner Cloud API Token - Get from https://console.hetzner.cloud/projects/[PROJECT_ID]/security/tokens"
  type        = string
  sensitive   = true
}

variable "ssh_public_key" {
  description = "Your SSH public key (cat ~/.ssh/id_rsa.pub)"
  type        = string
}

variable "domain" {
  description = "Domain name for the application (e.g., bokfoering.example.com)"
  type        = string
  default     = "yourdomain.com"
}

variable "server_type" {
  description = "Hetzner server type - see https://www.hetzner.com/cloud#pricing"
  type        = string
  default     = "cpx31"
  
  validation {
    condition     = contains(["cx11", "cx21", "cx31", "cx41", "cx51", "cpx11", "cpx21", "cpx31", "cpx41", "cpx51"], var.server_type)
    error_message = "Server type must be a valid Hetzner Cloud server type."
  }
}

variable "location" {
  description = "Hetzner datacenter location"
  type        = string
  default     = "fsn1"
  
  validation {
    condition     = contains(["fsn1", "nbg1", "hel1", "ash"], var.location)
    error_message = "Location must be one of: fsn1 (Falkenstein), nbg1 (Nuremberg), hel1 (Helsinki), ash (Ashburn)."
  }
}