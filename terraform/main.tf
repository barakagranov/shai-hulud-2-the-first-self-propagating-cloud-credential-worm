# =============================================================================
# SHAI-HULUD 2.0 LAB -- MAIN INFRASTRUCTURE
# =============================================================================
# Creates intentionally vulnerable infrastructure across AWS, Azure, and GCP.
#
# EACH cloud environment gets:
#   1. A VM with SSH access (for the student to SSH in and steal IMDS creds)
#   2. Overprivileged cloud credentials attached to the VM
#   3. Secrets in the cloud provider's secrets management service
#   4. Seeded fake developer credentials on disk (for TruffleHog to find)
#
# Every misconfiguration is documented with what it enables and how to fix it.
# =============================================================================

# Random suffix ensures globally unique names (S3 buckets, Key Vaults, etc.)
resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  suffix = random_id.suffix.hex
  name   = "${var.project_prefix}-${local.suffix}"
}

# =============================================================================
#                              AWS RESOURCES
# =============================================================================
# Creates:
#   - EC2 instance with IMDSv1 enabled (the critical vulnerability)
#   - IAM role with wildcard Secrets Manager + SSM access
#   - 3 Secrets Manager secrets + 2 SSM parameters
#   - SSH key pair for remote access
#   - Seeded fake credentials on disk for TruffleHog
#
# The attacker will:
#   1. SSH into the EC2 instance
#   2. curl the IMDS endpoint to steal IAM role temporary credentials
#   3. Use those credentials to enumerate and exfiltrate all secrets
# =============================================================================

# --- SSH Key Pair ---
# Terraform generates an ED25519 key pair so the student does not need to
# manage SSH keys manually. The private key is exported as a Terraform output.
resource "tls_private_key" "ssh_key" {
  algorithm = "ED25519"
}

resource "aws_key_pair" "lab_key" {
  key_name   = "${local.name}-key"
  public_key = tls_private_key.ssh_key.public_key_openssh
}

# --- IAM Role for EC2 ---
# This role is INTENTIONALLY OVERPRIVILEGED.
# It has read access to Secrets Manager and SSM across ALL regions with
# Resource: "*" (wildcard). This means any secret in any region is accessible.
#
# ATTACKER EXPLOITS: Steal temporary credentials via IMDS, then use them
#   to call GetSecretValue on every secret in every region.
# SECURE ALTERNATIVE:
#   1. Scope Resource to specific secret ARNs
#   2. Use Condition keys to restrict to specific regions
#   3. Use aws:SourceVpc condition to prevent off-instance usage

resource "aws_iam_role" "ec2_role" {
  name = "${local.name}-ec2-role"

  # The assume_role_policy defines WHO can use this role.
  # "Service": "ec2.amazonaws.com" means only EC2 instances can assume it.
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

# Inline policy granting overprivileged access to secrets
resource "aws_iam_role_policy" "ec2_secrets_policy" {
  name = "${local.name}-secrets-policy"
  role = aws_iam_role.ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # OVERPRIVILEGED: Can read ANY secret in Secrets Manager in ANY region
        # The worm calls ListSecrets + GetSecretValue across 17 regions
        Effect = "Allow"
        Action = [
          "secretsmanager:ListSecrets",
          "secretsmanager:GetSecretValue",
          "secretsmanager:BatchGetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "*" # <-- THIS IS THE PROBLEM: wildcard = all secrets
      },
      {
        # OVERPRIVILEGED: Can read ANY SSM parameter
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
          "ssm:DescribeParameters"
        ]
        Resource = "*" # <-- wildcard again
      },
      {
        # STS GetCallerIdentity requires no permissions, but including it
        # here makes the policy self-documenting
        Effect   = "Allow"
        Action   = ["sts:GetCallerIdentity"]
        Resource = "*"
      }
    ]
  })
}

# Instance profile -- the bridge between an EC2 instance and an IAM role.
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${local.name}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

# --- Networking ---
# Using the default VPC for simplicity.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Security group allowing SSH from anywhere
# ATTACKER EXPLOITS: Allows the student to SSH in from their workstation
# SECURE ALTERNATIVE: Restrict to your IP, or use SSM Session Manager
resource "aws_security_group" "lab_sg" {
  name        = "${local.name}-sg"
  description = "SSH access for Shai-Hulud lab"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH from anywhere (lab only - restrict in production)"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound (needed for package installs)"
  }
}

# --- EC2 Instance ---
# Amazon Linux 2023, t3.micro (free-tier eligible)
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
  filter {
    name   = "state"
    values = ["available"]
  }
}

resource "aws_instance" "lab_instance" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = "t3.micro"
  key_name               = aws_key_pair.lab_key.key_name
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.lab_sg.id]

  # ===================================================================
  # CRITICAL MISCONFIGURATION: IMDSv1 ENABLED
  # ===================================================================
  # http_tokens = "optional" means IMDSv1 is allowed.
  # IMDSv1: Any process on the instance can GET http://169.254.169.254/...
  #         and receive IAM role temporary credentials. No auth needed.
  # IMDSv2: Requires a PUT request first to obtain a session token,
  #         which must be included in subsequent requests as a header.
  #
  # ATTACKER EXPLOITS: curl to IMDS returns credentials with zero auth
  # SECURE ALTERNATIVE: http_tokens = "required" (forces IMDSv2)
  # ===================================================================
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "optional" # IMDSv1 allowed (THE VULNERABILITY)
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "enabled"
  }

  # User data script that installs tools and seeds fake credentials
  user_data = <<USERDATA
#!/bin/bash
set -x

# Install Node.js 20.x and git (needed for the worm payload)
dnf install -y nodejs git jq 2>/dev/null || yum install -y nodejs git jq 2>/dev/null

# Create a "developer" user with a realistic home directory
useradd -m -s /bin/bash developer 2>/dev/null || true
HOME_DIR="/home/developer"

# --- Seed fake credentials that TruffleHog will discover ---

# 1. Fake .npmrc with npm tokens
cat > $HOME_DIR/.npmrc << 'NPMRC'
//registry.npmjs.org/:_authToken=npm_NvTcH2025pRd4aBcDeFgHiJkLmNoPqRsTuVwXy
@novatech:registry=http://internal-registry.novatech.dev:4873/
//internal-registry.novatech.dev:4873/:_authToken=npm_NvTcHiNt2025xYzAbCdEfGhIjKlMnOpQrStUv
NPMRC

# 2. Fake .env with secrets
cat > $HOME_DIR/.env << 'DOTENV'
DATABASE_URL=postgresql://novatech_admin:S3cretP@ss2025!@prod-db.novatech.internal:5432/production
REDIS_URL=redis://:r3d1sP@ss!@cache.novatech.internal:6379/0
STRIPE_SECRET_KEY=sk_live_51NvTcH2025aBcDeFgHiJkLm
SENDGRID_API_KEY=SG.NvTcH2025aBcDeFgHiJkLm.xYzAbCdEfGhIjKlMnOpQrStUvWxYz0123456789ab
JWT_SECRET=SIMULATED-jwt-hmac-secret-NovaTech-HS256-production
GITHUB_TOKEN=ghp_NvTcH2025aBcDeFgHiJkLmNoPqRsTuVwXyZa
DOTENV

# 3. SSH key (auto-generated)
mkdir -p $HOME_DIR/.ssh
ssh-keygen -t ed25519 -f $HOME_DIR/.ssh/id_ed25519 -N "" -C "alex@novatech.dev" -q 2>/dev/null

# 4. Git repo with "accidentally committed" credentials in history
mkdir -p $HOME_DIR/projects/internal-api
cd $HOME_DIR/projects/internal-api
git init -q
git config user.email "alex@novatech.dev"
git config user.name "Alex Chen"

# Commit 1: Developer accidentally commits credentials
cat > config.py << 'PYCONFIG'
# NovaTech Internal API Configuration
AWS_ACCESS_KEY_ID = "AKIANVTCHPROD8X2QLJY"
AWS_SECRET_ACCESS_KEY = "R9fKb3zG7hLp2vXwN4mQ8cYdA1eT6uJ5sO0iWrBt"
DATABASE_PASSWORD = "NovaTech-Prod-DB-P@ssw0rd-2025!"
PYCONFIG
git add -A && git commit -q -m "Initial API configuration"

# Commit 2: Developer "removes" the credentials
cat > config.py << 'PYCONFIG2'
# NovaTech Internal API Configuration
# Credentials moved to environment variables (see .env.example)
import os
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD")
PYCONFIG2
git add -A && git commit -q -m "fix: move credentials to environment variables"

# 5. Fake AWS credentials file
mkdir -p $HOME_DIR/.aws
cat > $HOME_DIR/.aws/credentials << 'AWSCREDS'
[default]
aws_access_key_id = AKIANVTCHPROD8X2QLJY
aws_secret_access_key = R9fKb3zG7hLp2vXwN4mQ8cYdA1eT6uJ5sO0iWrBt

[novatech-prod]
aws_access_key_id = AKIANVTCHDEV93M7XKPW
aws_secret_access_key = T4kLm8nP2qR5vW7xY9zA3cE6fH1jN4oS8uB0dG2i
AWSCREDS

# Fix ownership
chown -R developer:developer $HOME_DIR
echo "=== AWS EC2 credential seeding complete ==="
USERDATA

  tags = {
    Name = "${local.name}-victim-ec2"
  }
}

# --- AWS Secrets Manager Secrets ---
# These are the high-value secrets the worm will exfiltrate.
# recovery_window_in_days = 0 allows immediate deletion for lab cleanup.

resource "aws_secretsmanager_secret" "db_creds" {
  name                    = "${local.name}/prod/database/credentials"
  description             = "Production PostgreSQL database credentials"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db_creds" {
  secret_id = aws_secretsmanager_secret.db_creds.id
  secret_string = jsonencode({
    username = "novatech_admin"
    password = "N0v4T3ch!Pr0d#2025"
    host     = "prod-db.cluster-abc123.us-east-1.rds.amazonaws.com"
    port     = 5432
    database = "novatech_production"
  })
}

resource "aws_secretsmanager_secret" "stripe_key" {
  name                    = "${local.name}/prod/api/stripe-key"
  description             = "Stripe API secret key for payment processing"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "stripe_key" {
  secret_id     = aws_secretsmanager_secret.stripe_key.id
  secret_string = "sk_live_SIMULATED_51O4xKy3dBz3LkNovaTech2025xYz"
}

resource "aws_secretsmanager_secret" "oauth_secret" {
  name                    = "${local.name}/prod/oauth/client-secret"
  description             = "OAuth2 client secret for SSO integration"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "oauth_secret" {
  secret_id     = aws_secretsmanager_secret.oauth_secret.id
  secret_string = "SIMULATED-oauth-client-secret-NovaTech-2025-xyz789"
}

# --- AWS SSM Parameter Store ---
resource "aws_ssm_parameter" "db_conn" {
  name        = "/${local.name}/prod/database/connection-string"
  description = "Production database connection string"
  type        = "SecureString"
  value       = "postgresql://novatech_admin:N0v4T3ch!@prod-db.abc123.rds.amazonaws.com:5432/novatech"
}

resource "aws_ssm_parameter" "jwt" {
  name        = "/${local.name}/prod/app/jwt-secret"
  description = "JWT HMAC signing secret for API authentication"
  type        = "SecureString"
  value       = "SIMULATED-jwt-hmac-secret-NovaTech-HS256-production-2025"
}


# =============================================================================
#                             AZURE RESOURCES
# =============================================================================
# Creates:
#   - Resource Group containing all Azure resources
#   - Linux VM with System-Assigned Managed Identity and SSH access
#   - Key Vault with 3 secrets
#   - Access policy granting the VM's identity access to Key Vault
#   - VNet, Subnet, NSG, Public IP, NIC
#   - Seeded fake credentials on disk
#
# The attacker will:
#   1. SSH into the Azure VM
#   2. curl the Azure IMDS to steal a Managed Identity Bearer token
#   3. Use that token to call the Key Vault REST API directly with curl
# =============================================================================

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "lab" {
  name     = "${local.name}-rg"
  location = var.azure_location
  tags = {
    Project  = "cloud-attack-lab"
    Scenario = "shai-hulud-2"
    Warning  = "INTENTIONALLY-VULNERABLE-LAB-ONLY"
  }
}

# --- Azure Key Vault ---
# public_network_access_enabled = true is an intentional misconfiguration.
# ATTACKER EXPLOITS: Key Vault is accessible from any network
# SECURE ALTERNATIVE: Use private endpoints and disable public access

resource "azurerm_key_vault" "lab" {
  name                          = "${var.project_prefix}kv${local.suffix}"
  location                      = azurerm_resource_group.lab.location
  resource_group_name           = azurerm_resource_group.lab.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  public_network_access_enabled = true  # MISCONFIGURATION
  purge_protection_enabled      = false # Allows clean lab teardown

  # Access policy for the Terraform deployer (you)
  access_policy {
    tenant_id          = data.azurerm_client_config.current.tenant_id
    object_id          = data.azurerm_client_config.current.object_id
    secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover"]
  }
}

resource "azurerm_key_vault_secret" "cosmos_conn" {
  name         = "cosmos-db-connection-string"
  value        = "AccountEndpoint=https://novatech-prod.documents.azure.com:443/;AccountKey=SIMULATED-cosmos-primary-key-NovaTech2025base64encoded=="
  key_vault_id = azurerm_key_vault.lab.id
}

resource "azurerm_key_vault_secret" "sendgrid" {
  name         = "sendgrid-api-key"
  value        = "SG.SIMULATED.NovaTech2025-sendgrid-api-key-for-email-delivery"
  key_vault_id = azurerm_key_vault.lab.id
}

resource "azurerm_key_vault_secret" "storage_key" {
  name         = "storage-account-key"
  value        = "SIMULATED-azure-storage-account-primary-access-key-NovaTech2025+base64=="
  key_vault_id = azurerm_key_vault.lab.id
}

# --- Azure Networking ---
resource "azurerm_virtual_network" "lab" {
  name                = "${local.name}-vnet"
  address_space       = ["10.1.0.0/16"]
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
}

resource "azurerm_subnet" "lab" {
  name                 = "${local.name}-subnet"
  resource_group_name  = azurerm_resource_group.lab.name
  virtual_network_name = azurerm_virtual_network.lab.name
  address_prefixes     = ["10.1.1.0/24"]
}

resource "azurerm_public_ip" "lab" {
  name                = "${local.name}-pip"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_security_group" "lab" {
  name                = "${local.name}-nsg"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name

  security_rule {
    name                       = "AllowSSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "lab" {
  name                = "${local.name}-nic"
  location            = azurerm_resource_group.lab.location
  resource_group_name = azurerm_resource_group.lab.name

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.lab.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.lab.id
  }
}

resource "azurerm_network_interface_security_group_association" "lab" {
  network_interface_id      = azurerm_network_interface.lab.id
  network_security_group_id = azurerm_network_security_group.lab.id
}

# --- Azure Linux VM ---
# Ubuntu 24.04 LTS with System-Assigned Managed Identity.
# ATTACKER EXPLOITS: curl to 169.254.169.254 with Metadata:true header
#   returns a Bearer token for the Managed Identity
# SECURE ALTERNATIVE: Use User-Assigned Identity with minimal IAM bindings

resource "azurerm_linux_virtual_machine" "lab" {
  name                            = "${local.name}-vm"
  resource_group_name             = azurerm_resource_group.lab.name
  location                        = azurerm_resource_group.lab.location
  size                            = "Standard_B1s"
  admin_username                  = "azureuser"
  admin_password                  = "P@ssw0rd!NovaTech2025Lab"
  disable_password_authentication = false
  network_interface_ids           = [azurerm_network_interface.lab.id]

  identity {
    type = "SystemAssigned"
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  custom_data = base64encode(<<CUSTOMDATA
#!/bin/bash
set -x
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs git jq curl

useradd -m -s /bin/bash developer 2>/dev/null || true
HOME_DIR="/home/developer"

cat > $HOME_DIR/.npmrc << 'NPMRC'
//registry.npmjs.org/:_authToken=npm_NvTcHazr2025aBcDeFgHiJkLmNoPqRsTuVw
NPMRC

cat > $HOME_DIR/.env << 'DOTENV'
DATABASE_URL=postgresql://admin:S3cretP@ss!@prod-db.novatech.internal:5432/prod
AZURE_CLIENT_SECRET=NvT~azr~2025~cLiEnTsEcReTvAlUe1234
GITHUB_TOKEN=ghp_NvTcHazr2025xYzAbCdEfGhIjKlMnOpQrStU
DOTENV

mkdir -p $HOME_DIR/.ssh
ssh-keygen -t ed25519 -f $HOME_DIR/.ssh/id_ed25519 -N "" -C "alex@novatech.dev" -q 2>/dev/null

mkdir -p $HOME_DIR/projects/internal-api
cd $HOME_DIR/projects/internal-api
git init -q && git config user.email "alex@novatech.dev" && git config user.name "Alex Chen"
printf 'AZURE_CLIENT_SECRET = "NvT~azr~2025~cLiEnTsEcReTvAlUe1234"\nAZURE_STORAGE_KEY = "NvTcHaZrStOrAgEkEy2025Base64EnCoDeDvAlUe=="\n' > config.py
git add -A && git commit -q -m "Initial config with Azure credentials"
printf 'import os\nAZURE_CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]\n' > config.py
git add -A && git commit -q -m "fix: remove hardcoded Azure secrets"

mkdir -p $HOME_DIR/.azure
echo '{"subscriptions":[{"id":"00000000-0000-0000-0000-000000000000","name":"NovaTech-Prod"}]}' > $HOME_DIR/.azure/azureProfile.json

chown -R developer:developer $HOME_DIR
echo "=== Azure VM credential seeding complete ==="
CUSTOMDATA
  )
}

# Grant the VM's Managed Identity access to Key Vault
# OVERPRIVILEGED: Get + List on ALL secrets in the vault
resource "azurerm_key_vault_access_policy" "vm_identity" {
  key_vault_id       = azurerm_key_vault.lab.id
  tenant_id          = data.azurerm_client_config.current.tenant_id
  object_id          = azurerm_linux_virtual_machine.lab.identity[0].principal_id
  secret_permissions = ["Get", "List"]
}


# =============================================================================
#                              GCP RESOURCES
# =============================================================================
# Creates:
#   - Service Account with project-level Secret Manager access
#   - Compute Engine instance with the SA attached
#   - 3 Secret Manager secrets
#   - Seeded fake credentials on disk
#
# The attacker will:
#   1. SSH into the GCE instance via gcloud compute ssh
#   2. curl the GCP metadata server to steal the SA's OAuth2 token
#   3. Use that token to call the Secret Manager REST API directly
# =============================================================================

# Service Account -- overprivileged with project-wide Secret Manager access
resource "google_service_account" "lab_sa" {
  account_id   = "${var.project_prefix}-lab-sa-${local.suffix}"
  display_name = "Shai-Hulud Lab Service Account"
  description  = "Intentionally overprivileged SA for the supply chain worm lab"
}

# Project-level IAM bindings (too broad!)
resource "google_project_iam_member" "sa_secret_accessor" {
  project = var.gcp_project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.lab_sa.email}"
}

resource "google_project_iam_member" "sa_secret_viewer" {
  project = var.gcp_project_id
  role    = "roles/secretmanager.viewer"
  member  = "serviceAccount:${google_service_account.lab_sa.email}"
}

# --- GCP Secret Manager Secrets ---
resource "google_secret_manager_secret" "bigquery_key" {
  secret_id = "${var.project_prefix}-bigquery-key-${local.suffix}"
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_version" "bigquery_key" {
  secret      = google_secret_manager_secret.bigquery_key.id
  secret_data = "SIMULATED-bigquery-service-account-key-json-NovaTech-2025"
}

resource "google_secret_manager_secret" "pubsub_creds" {
  secret_id = "${var.project_prefix}-pubsub-creds-${local.suffix}"
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_version" "pubsub_creds" {
  secret      = google_secret_manager_secret.pubsub_creds.id
  secret_data = "SIMULATED-pubsub-api-credentials-NovaTech-analytics-pipeline-2025"
}

resource "google_secret_manager_secret" "firebase_key" {
  secret_id = "${var.project_prefix}-firebase-key-${local.suffix}"
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_version" "firebase_key" {
  secret      = google_secret_manager_secret.firebase_key.id
  secret_data = "SIMULATED-firebase-admin-sdk-private-key-NovaTech-2025"
}

# --- GCP Compute Engine Instance ---
resource "google_compute_instance" "lab_instance" {
  name         = "${var.project_prefix}-lab-vm-${local.suffix}"
  machine_type = "e2-micro"
  zone         = var.gcp_zone

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    network = "default"
    access_config {} # Assigns a public IP
  }

  # Attach the overprivileged service account
  # scopes = ["cloud-platform"] is the broadest scope
  service_account {
    email  = google_service_account.lab_sa.email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = <<STARTUP
#!/bin/bash
set -x
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs git jq curl

useradd -m -s /bin/bash developer 2>/dev/null || true
HOME_DIR="/home/developer"

cat > $HOME_DIR/.npmrc << 'NPMRC'
//registry.npmjs.org/:_authToken=npm_NvTcHgcp2025aBcDeFgHiJkLmNoPqRsTuVw
NPMRC

cat > $HOME_DIR/.env << 'DOTENV'
GCP_API_KEY=AIzaSyNvTcH2025GcPaPiKeYaBcDeFgHiJkLmNo
GITHUB_TOKEN=ghp_NvTcHgcp2025xYzAbCdEfGhIjKlMnOpQrStU
FIREBASE_ADMIN_SDK_KEY=SIMULATED-firebase-admin-key-data
DOTENV

mkdir -p $HOME_DIR/.ssh
ssh-keygen -t ed25519 -f $HOME_DIR/.ssh/id_ed25519 -N "" -q 2>/dev/null

mkdir -p $HOME_DIR/projects/analytics-pipeline
cd $HOME_DIR/projects/analytics-pipeline
git init -q && git config user.email "alex@novatech.dev" && git config user.name "Alex Chen"
printf 'GCP_PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----\\nSIMULATED_KEY\\n-----END RSA PRIVATE KEY-----"\nBIGQUERY_CREDENTIALS = {"type":"service_account","project_id":"novatech-prod","private_key":"SIMULATED"}\n' > config.py
git add -A && git commit -q -m "Add GCP service credentials for analytics"
printf 'import os\nGCP_PRIVATE_KEY = os.environ["GCP_PRIVATE_KEY"]\n' > config.py
git add -A && git commit -q -m "refactor: use environment variables for credentials"

mkdir -p $HOME_DIR/.config/gcloud
printf '{"type":"authorized_user","client_id":"SIMULATED.apps.googleusercontent.com","client_secret":"SIMULATED-gcp-secret","refresh_token":"SIMULATED-refresh-token-NovaTech"}\n' > $HOME_DIR/.config/gcloud/application_default_credentials.json

chown -R developer:developer $HOME_DIR
echo "=== GCP GCE credential seeding complete ==="
STARTUP

  allow_stopping_for_update = true
}
