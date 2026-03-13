# =============================================================================
# PROVIDER CONFIGURATION -- AWS + Azure + GCP
# =============================================================================
# Configures Terraform to work with all three major cloud providers.
# Version constraints ensure reproducible deployments across machines.
#
# SCENARIO: Shai-Hulud 2.0 Supply Chain Worm Simulation
# Based on: Real attack wave observed November 24, 2025
# =============================================================================

terraform {
  # Require Terraform 1.11 or newer for stable multi-provider support
  # and write-only attributes
  required_version = ">= 1.11.0"

  required_providers {
    # AWS Provider v6.x -- latest major version with multi-region support
    # Used for: EC2 instance, IAM role, Secrets Manager, SSM Parameter Store
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.36"
    }

    # Azure Provider v4.x -- current stable major version
    # Used for: Linux VM, Managed Identity, Key Vault, VNet, NSG
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.64"
    }

    # GCP Provider v7.x -- current stable major version
    # Used for: Compute Engine instance, Service Account, Secret Manager
    google = {
      source  = "hashicorp/google"
      version = "~> 7.23"
    }

    # Random provider -- generates unique suffixes for globally unique names
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }

    # TLS provider -- generates SSH key pairs for EC2 access
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

# AWS Provider
# Deploys resources in us-east-1 by default.
# default_tags applies tags to EVERY AWS resource automatically.
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project  = "cloud-attack-lab"
      Scenario = "shai-hulud-2"
      Warning  = "INTENTIONALLY-VULNERABLE-LAB-ONLY"
    }
  }
}

# Azure Provider
# The features block is required by azurerm and configures provider behavior.
# We enable purge_soft_delete_on_destroy so Key Vault cleanup is clean.
provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
  subscription_id = var.azure_subscription_id
}

# GCP Provider
# project and region are set at the provider level so individual
# resources do not need to repeat them.
provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}
