# =============================================================================
# OUTPUTS -- Values needed by the attack scripts
# =============================================================================
# These outputs provide all the information needed to execute the attack.
# The core/config.py file reads these via `terraform output -json`.
# =============================================================================

# --- SSH Key for AWS ---
output "aws_ssh_private_key" {
  description = "SSH private key for EC2 access"
  value       = tls_private_key.ssh_key.private_key_openssh
  sensitive   = true
}

# --- AWS ---
output "aws_instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.lab_instance.id
}

output "aws_instance_public_ip" {
  description = "EC2 instance public IP for SSH access"
  value       = aws_instance.lab_instance.public_ip
}

output "aws_iam_role_arn" {
  description = "IAM role ARN attached to the EC2 instance"
  value       = aws_iam_role.ec2_role.arn
}

output "aws_secrets_prefix" {
  description = "Prefix for Secrets Manager secret names"
  value       = local.name
}

output "aws_ssm_prefix" {
  description = "Prefix for SSM Parameter Store parameter names"
  value       = "/${local.name}"
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

# --- Azure ---
output "azure_vm_public_ip" {
  description = "Azure VM public IP for SSH access"
  value       = azurerm_public_ip.lab.ip_address
}

output "azure_vm_password" {
  description = "Azure VM SSH password"
  value       = "P@ssw0rd!NovaTech2025Lab"
  sensitive   = true
}

output "azure_resource_group" {
  description = "Azure resource group name"
  value       = azurerm_resource_group.lab.name
}

output "azure_keyvault_name" {
  description = "Azure Key Vault name"
  value       = azurerm_key_vault.lab.name
}

output "azure_keyvault_uri" {
  description = "Azure Key Vault URI"
  value       = azurerm_key_vault.lab.vault_uri
}

output "azure_managed_identity_id" {
  description = "Azure VM Managed Identity principal ID"
  value       = azurerm_linux_virtual_machine.lab.identity[0].principal_id
}

# --- GCP ---
output "gcp_instance_name" {
  description = "GCP Compute Engine instance name"
  value       = google_compute_instance.lab_instance.name
}

output "gcp_instance_zone" {
  description = "GCP zone where the instance runs"
  value       = var.gcp_zone
}

output "gcp_service_account_email" {
  description = "GCP service account email attached to the instance"
  value       = google_service_account.lab_sa.email
}

output "gcp_project_id" {
  description = "GCP project ID"
  value       = var.gcp_project_id
}

output "gcp_secret_prefix" {
  description = "Prefix for GCP Secret Manager secret names"
  value       = var.project_prefix
}

output "gcp_secret_suffix" {
  description = "Suffix for GCP Secret Manager secret names"
  value       = local.suffix
}

# --- Resource Name Prefix ---
output "resource_prefix" {
  description = "Common resource name prefix (project_prefix-suffix)"
  value       = local.name
}
