# =============================================================================
# INPUT VARIABLES
# =============================================================================
# These variables configure the lab environment across all three clouds.
# Copy terraform.tfvars.example to terraform.tfvars and fill in your values.
# =============================================================================

# --- General ---

variable "project_prefix" {
  description = "Short prefix for all resource names. Use your initials or a short identifier to avoid name collisions."
  type        = string
  default     = "sh2"
}

# --- AWS ---

variable "aws_region" {
  description = "AWS region for deploying resources. us-east-1 is recommended (cheapest, most services)."
  type        = string
  default     = "us-east-1"
}

# --- Azure ---

variable "azure_subscription_id" {
  description = "Azure subscription ID. Find with: az account show --query id --output tsv"
  type        = string
}

variable "azure_location" {
  description = "Azure region for deploying resources. eastus is recommended (cheapest)."
  type        = string
  default     = "eastus"
}

# --- GCP ---

variable "gcp_project_id" {
  description = "GCP project ID. Find with: gcloud config get project"
  type        = string
}

variable "gcp_region" {
  description = "GCP region for deploying resources."
  type        = string
  default     = "us-central1"
}

variable "gcp_zone" {
  description = "GCP zone for Compute Engine instances."
  type        = string
  default     = "us-central1-a"
}
