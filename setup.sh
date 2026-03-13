#!/bin/bash
# =============================================================================
# setup.sh -- One-Command Setup for Shai-Hulud 2.0
# =============================================================================
# Checks 10+ prerequisites across AWS/Azure/GCP/Docker/Node/Python/GitHub,
# starts Verdaccio, publishes victim packages, creates the Python venv,
# installs dependencies, and deploys multi-cloud infrastructure with Terraform.
#
# Usage: ./setup.sh
# Safe to re-run: detects partial state and picks up where it left off.
# =============================================================================

# No set -e. Every error is caught explicitly with helpful messages.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"
VENV_DIR="${SCRIPT_DIR}/.venv"

echo -e "${CYAN}"
echo "============================================="
echo "  Shai-Hulud 2.0 -- Lab Setup"
echo "  Supply Chain Worm Simulation"
echo "============================================="
echo -e "${NC}"

# =============================================================================
# [1/12] PRE-FLIGHT CHECKS -- Core Tools
# =============================================================================

echo -e "${CYAN}[1/12] Checking core tools...${NC}"

# Terraform
if ! command -v terraform &> /dev/null; then
    echo -e "${RED}ERROR: Terraform not found. Install Terraform >= 1.11.0${NC}"
    echo "  https://developer.hashicorp.com/terraform/install"
    exit 1
fi
TF_VERSION=$(terraform version 2>/dev/null | head -1 | sed 's/[^0-9.]//g')
echo -e "  Terraform: ${GREEN}${TF_VERSION}${NC}"

# Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: Python 3 not found. Install Python >= 3.11${NC}"
    exit 1
fi
PY_VERSION=$(python3 --version 2>/dev/null | cut -d' ' -f2)
PY_MINOR=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
echo -e "  Python: ${GREEN}${PY_VERSION}${NC}"

# Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker not found. Install Docker.${NC}"
    echo "  https://docs.docker.com/get-docker/"
    exit 1
fi
if ! docker info &>/dev/null; then
    echo -e "${RED}ERROR: Docker daemon not running. Start Docker first.${NC}"
    exit 1
fi
echo -e "  Docker: ${GREEN}running${NC}"

# Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}ERROR: Node.js not found. Install Node.js >= 20${NC}"
    echo "  https://nodejs.org/"
    exit 1
fi
NODE_VERSION=$(node --version 2>/dev/null)
echo -e "  Node.js: ${GREEN}${NODE_VERSION}${NC}"

# npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}ERROR: npm not found. Install npm >= 10${NC}"
    exit 1
fi
NPM_VERSION=$(npm --version 2>/dev/null)
echo -e "  npm: ${GREEN}${NPM_VERSION}${NC}"

# jq
if ! command -v jq &> /dev/null; then
    echo -e "${YELLOW}WARNING: jq not found. Some verification commands may not work.${NC}"
    echo "  Install with: sudo apt install jq"
fi

# curl
if ! command -v curl &> /dev/null; then
    echo -e "${RED}ERROR: curl not found.${NC}"
    exit 1
fi

# =============================================================================
# [2/12] PRE-FLIGHT CHECKS -- Cloud CLIs
# =============================================================================

echo -e "\n${CYAN}[2/12] Checking cloud CLIs...${NC}"

# AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}ERROR: AWS CLI not found. Install AWS CLI v2${NC}"
    echo "  https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
    exit 1
fi
AWS_VERSION=$(aws --version 2>&1 | cut -d/ -f2 | cut -d' ' -f1)
echo -e "  AWS CLI: ${GREEN}${AWS_VERSION}${NC}"

# Azure CLI
if ! command -v az &> /dev/null; then
    echo -e "${RED}ERROR: Azure CLI not found. Install az CLI${NC}"
    echo "  https://learn.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi
AZ_VERSION=$(az version 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('azure-cli','unknown'))" 2>/dev/null || echo "unknown")
echo -e "  Azure CLI: ${GREEN}${AZ_VERSION}${NC}"

# Google Cloud CLI
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}ERROR: gcloud CLI not found. Install Google Cloud SDK${NC}"
    echo "  https://cloud.google.com/sdk/docs/install"
    exit 1
fi
GCLOUD_VERSION=$(gcloud version 2>/dev/null | head -1 | sed 's/[^0-9.]//g')
echo -e "  gcloud: ${GREEN}${GCLOUD_VERSION}${NC}"

# =============================================================================
# [3/12] VERIFY CLOUD CREDENTIALS
# =============================================================================

echo -e "\n${CYAN}[3/12] Verifying cloud credentials...${NC}"

# AWS
AWS_IDENTITY=$(aws sts get-caller-identity 2>&1) || true
if echo "${AWS_IDENTITY}" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    AWS_ACCOUNT=$(echo "${AWS_IDENTITY}" | python3 -c "import sys,json; print(json.load(sys.stdin)['Account'])")
    AWS_ARN=$(echo "${AWS_IDENTITY}" | python3 -c "import sys,json; print(json.load(sys.stdin)['Arn'])")
    echo -e "  AWS Account: ${GREEN}${AWS_ACCOUNT}${NC}"
    echo -e "  AWS Identity: ${GREEN}${AWS_ARN}${NC}"
else
    echo -e "${RED}ERROR: AWS credentials not configured or invalid${NC}"
    echo -e "  Raw output: ${AWS_IDENTITY}"
    echo "  Fix: run 'aws configure' with your lab account credentials"
    exit 1
fi

# Azure
AZ_SUB=$(az account show --query '{id:id,name:name}' --output json 2>/dev/null) || true
if [ -n "${AZ_SUB}" ] && echo "${AZ_SUB}" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    AZ_SUB_ID=$(echo "${AZ_SUB}" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
    AZ_SUB_NAME=$(echo "${AZ_SUB}" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
    echo -e "  Azure Sub: ${GREEN}${AZ_SUB_ID}${NC} (${AZ_SUB_NAME})"
else
    echo -e "${RED}ERROR: Azure CLI not logged in${NC}"
    echo "  Fix: run 'az login'"
    exit 1
fi

# GCP
GCP_PROJECT=$(gcloud config get project 2>/dev/null)
if [ -n "${GCP_PROJECT}" ]; then
    echo -e "  GCP Project: ${GREEN}${GCP_PROJECT}${NC}"
else
    echo -e "${RED}ERROR: GCP project not configured${NC}"
    echo "  Fix: run 'gcloud auth login' then 'gcloud config set project YOUR_PROJECT_ID'"
    exit 1
fi

echo -e "${YELLOW}  WARNING: Verify ALL THREE are LAB accounts, not production!${NC}"

# =============================================================================
# [4/12] CHECK GITHUB CREDENTIALS
# =============================================================================

echo -e "\n${CYAN}[4/12] Checking GitHub credentials...${NC}"

if [ -z "${GITHUB_PAT}" ]; then
    echo -e "${YELLOW}  GITHUB_PAT not set. Phase 0 (pull_request_target) and Phase 4 (persistence)${NC}"
    echo -e "${YELLOW}  will not work without it. Set with: export GITHUB_PAT=ghp_...${NC}"
    echo -e "${YELLOW}  Continuing setup -- you can set it before running the attack.${NC}"
else
    # Validate the PAT
    GH_USER=$(curl -s -H "Authorization: token ${GITHUB_PAT}" https://api.github.com/user 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('login','INVALID'))" 2>/dev/null)
    if [ "${GH_USER}" = "INVALID" ] || [ -z "${GH_USER}" ]; then
        echo -e "${YELLOW}  GITHUB_PAT is set but appears invalid. Check your token.${NC}"
    else
        echo -e "  GitHub user: ${GREEN}${GH_USER}${NC}"
        if [ -z "${GITHUB_USERNAME}" ]; then
            export GITHUB_USERNAME="${GH_USER}"
            echo -e "  Auto-set GITHUB_USERNAME=${GH_USER}"
        fi
    fi
fi

# =============================================================================
# [5/12] START VERDACCIO (Private npm Registry)
# =============================================================================

echo -e "\n${CYAN}[5/12] Starting Verdaccio private npm registry...${NC}"

# Check if already running
if docker inspect -f '{{.State.Running}}' verdaccio 2>/dev/null | grep -q true; then
    echo -e "  Verdaccio already running"
else
    # Remove any stopped container with the same name
    docker rm -f verdaccio 2>/dev/null || true

    # Create storage directory
    mkdir -p ~/verdaccio-storage
    sudo chown 10001:65533 ~/verdaccio-storage 2>/dev/null || true

    if docker run -d \
        --name verdaccio \
        -p 4873:4873 \
        -v ~/verdaccio-storage:/verdaccio/storage \
        verdaccio/verdaccio:latest 2>/dev/null; then
        echo -e "  ${GREEN}Verdaccio started on port 4873${NC}"
        echo "  Waiting for startup..."
        sleep 5
    else
        echo -e "${RED}ERROR: Failed to start Verdaccio container${NC}"
        echo "  Check: docker logs verdaccio"
        exit 1
    fi
fi

# Verify Verdaccio is responding
if curl -sf http://localhost:4873/-/ping &>/dev/null; then
    echo -e "  ${GREEN}Verdaccio is healthy${NC}"
else
    echo -e "${RED}ERROR: Verdaccio not responding on port 4873${NC}"
    echo "  Check: docker logs verdaccio"
    exit 1
fi

# =============================================================================
# [6/12] PUBLISH VICTIM PACKAGES TO VERDACCIO
# =============================================================================

echo -e "\n${CYAN}[6/12] Publishing victim npm packages...${NC}"

# Check if packages already exist
PKG_COUNT=$(curl -s "http://localhost:4873/-/v1/search?text=novatech&size=20" 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('objects',[])))" 2>/dev/null || echo "0")

if [ "${PKG_COUNT}" -ge 5 ] 2>/dev/null; then
    echo -e "  ${GREEN}${PKG_COUNT} packages already published (previous run)${NC}"
else
    # Register the victim npm user
    # Check if user already exists by trying whoami
    EXISTING_TOKEN=$(grep "localhost:4873" ~/.npmrc 2>/dev/null | sed 's/.*_authToken=//' | sed 's/"//g')
    if [ -n "${EXISTING_TOKEN}" ]; then
        WHOAMI=$(curl -s -H "Authorization: Bearer ${EXISTING_TOKEN}" http://localhost:4873/-/whoami 2>/dev/null)
        if echo "${WHOAMI}" | grep -q "novatech-bot"; then
            echo -e "  Verdaccio user novatech-bot already registered"
        else
            EXISTING_TOKEN=""
        fi
    fi

    if [ -z "${EXISTING_TOKEN}" ]; then
        echo "  Registering npm user novatech-bot on Verdaccio..."
        echo "  When prompted: username=novatech-bot, password=novatech123, email=bot@novatech.dev"
        npm adduser --registry http://localhost:4873 || {
            echo -e "${RED}ERROR: npm adduser failed${NC}"
            echo "  Try manually: npm adduser --registry http://localhost:4873"
            exit 1
        }
    fi

    # Configure @novatech scope to use Verdaccio
    npm config set @novatech:registry http://localhost:4873

    # Create and publish packages
    TEMP_PKG_DIR=$(mktemp -d)
    for pkg_info in \
        "auth-helpers:2.4.1:NovaTech authentication helper utilities" \
        "db-connector:1.8.3:NovaTech database connection pool manager" \
        "logger:3.1.0:NovaTech structured logging library" \
        "config-loader:1.2.0:NovaTech configuration loader with environment support" \
        "api-client:4.0.2:NovaTech internal API client SDK"; do

        IFS=':' read -r name version desc <<< "${pkg_info}"
        dir="${TEMP_PKG_DIR}/novatech-${name}"
        mkdir -p "${dir}"

        cat > "${dir}/package.json" << PKGJSON
{
  "name": "@novatech/${name}",
  "version": "${version}",
  "description": "${desc}",
  "main": "index.js",
  "scripts": {},
  "author": "NovaTech Platform Team",
  "license": "MIT"
}
PKGJSON

        cat > "${dir}/index.js" << INDEXJS
// ${desc} v${version}
module.exports = {
  ping: () => "pong from @novatech/${name}@${version}",
  version: "${version}"
};
INDEXJS

        npm publish "${dir}" --registry http://localhost:4873 2>/dev/null && \
            echo -e "  ${GREEN}Published @novatech/${name}@${version}${NC}" || \
            echo -e "  ${YELLOW}@novatech/${name} already exists${NC}"
    done
    rm -rf "${TEMP_PKG_DIR}"

    # Store the npm token for the attack
    NPM_TOKEN=$(grep "localhost:4873" ~/.npmrc 2>/dev/null | sed 's/.*_authToken=//' | sed 's/"//g')
    if [ -n "${NPM_TOKEN}" ]; then
        export VICTIM_NPM_TOKEN="${NPM_TOKEN}"
        echo -e "  ${GREEN}npm token saved to VICTIM_NPM_TOKEN${NC}"
    fi
fi

# =============================================================================
# [7/12] PYTHON VIRTUAL ENVIRONMENT
# =============================================================================

echo -e "\n${CYAN}[7/12] Creating Python virtual environment...${NC}"

# Auto-fix: broken venv from a previous failed run
if [ -d "${VENV_DIR}" ] && [ ! -f "${VENV_DIR}/bin/activate" ]; then
    echo -e "${YELLOW}  Broken .venv detected. Cleaning up and recreating...${NC}"
    rm -rf "${VENV_DIR}"
fi

if [ -d "${VENV_DIR}" ] && [ -f "${VENV_DIR}/bin/activate" ]; then
    echo -e "  Virtual environment already exists"
else
    VENV_OUTPUT=$(python3 -m venv "${VENV_DIR}" 2>&1) || true

    if [ ! -f "${VENV_DIR}/bin/activate" ]; then
        if echo "${VENV_OUTPUT}" | grep -qi "ensurepip"; then
            echo -e "${YELLOW}  python${PY_MINOR}-venv package is missing.${NC}"
            read -p "  Install it now? (requires sudo) [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                if sudo apt install -y "python${PY_MINOR}-venv"; then
                    rm -rf "${VENV_DIR}"
                    if python3 -m venv "${VENV_DIR}"; then
                        echo -e "  ${GREEN}Created: ${VENV_DIR}${NC}"
                    else
                        echo -e "${RED}ERROR: venv creation still failing${NC}"
                        exit 1
                    fi
                else
                    echo -e "${RED}ERROR: Failed to install python${PY_MINOR}-venv${NC}"
                    exit 1
                fi
            else
                echo -e "${RED}Cannot continue without a virtual environment.${NC}"
                exit 1
            fi
        else
            echo -e "${RED}ERROR: Failed to create virtual environment${NC}"
            echo -e "${RED}  ${VENV_OUTPUT}${NC}"
            exit 1
        fi
    else
        echo -e "  ${GREEN}Created: ${VENV_DIR}${NC}"
    fi
fi

source "${VENV_DIR}/bin/activate"
echo -e "  ${GREEN}Activated virtual environment${NC}"

# =============================================================================
# [8/12] INSTALL PYTHON DEPENDENCIES
# =============================================================================

echo -e "\n${CYAN}[8/12] Installing Python dependencies...${NC}"

pip install --quiet --upgrade pip 2>/dev/null || true

if pip install -r "${SCRIPT_DIR}/requirements.txt" 2>&1 | tail -3; then
    echo -e "  ${GREEN}Dependencies installed${NC}"
else
    echo -e "${YELLOW}  Some packages failed. Trying fallback (core packages only)...${NC}"
    if pip install boto3 rich paramiko requests PyNaCl 2>&1 | tail -3; then
        echo -e "  ${GREEN}Fallback install succeeded${NC}"
    else
        echo -e "${RED}ERROR: Could not install core dependencies.${NC}"
        exit 1
    fi
fi

# =============================================================================
# [9/12] TERRAFORM CONFIGURATION
# =============================================================================

echo -e "\n${CYAN}[9/12] Configuring Terraform...${NC}"
if [ ! -f "${TERRAFORM_DIR}/terraform.tfvars" ]; then
    if [ -f "${TERRAFORM_DIR}/terraform.tfvars.example" ]; then
        cp "${TERRAFORM_DIR}/terraform.tfvars.example" "${TERRAFORM_DIR}/terraform.tfvars"

        # Auto-fill Azure subscription ID and GCP project ID
        if [ -n "${AZ_SUB_ID}" ]; then
            sed -i "s/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/${AZ_SUB_ID}/" "${TERRAFORM_DIR}/terraform.tfvars"
            echo -e "  ${GREEN}Auto-filled Azure subscription ID${NC}"
        fi
        if [ -n "${GCP_PROJECT}" ]; then
            sed -i "s/your-gcp-project-id/${GCP_PROJECT}/" "${TERRAFORM_DIR}/terraform.tfvars"
            echo -e "  ${GREEN}Auto-filled GCP project ID${NC}"
        fi

        echo -e "  ${GREEN}Created terraform.tfvars from example${NC}"
        echo -e "  ${YELLOW}Review terraform/terraform.tfvars before continuing${NC}"
    else
        echo -e "${RED}ERROR: No terraform.tfvars.example found${NC}"
        exit 1
    fi
else
    echo -e "  terraform.tfvars already exists"
fi

# =============================================================================
# [10/12] TERRAFORM INIT
# =============================================================================

echo -e "\n${CYAN}[10/12] Running terraform init...${NC}"
cd "${TERRAFORM_DIR}"

if ! terraform init -input=false; then
    echo ""
    echo -e "${RED}ERROR: terraform init failed${NC}"
    echo ""
    echo "  Common causes:"
    echo "    - No internet (Terraform downloads providers on first init)"
    echo "    - Corrupt state (fix: rm -rf .terraform .terraform.lock.hcl)"
    exit 1
fi
echo -e "  ${GREEN}Terraform initialized${NC}"

# =============================================================================
# [11/12] TERRAFORM APPLY
# =============================================================================

echo -e "\n${CYAN}[11/12] Deploying multi-cloud infrastructure (terraform apply)...${NC}"
echo -e "  ${YELLOW}This creates resources on AWS + Azure + GCP. Takes 3-5 minutes.${NC}"

if ! terraform apply -auto-approve -input=false; then
    echo ""
    echo -e "${RED}ERROR: terraform apply failed${NC}"
    echo ""
    echo "  Common causes:"
    echo "    - Insufficient IAM permissions on one of the clouds"
    echo "    - Resource name collision (change project_prefix in terraform.tfvars)"
    echo "    - Resources from a previous run (run ./cleanup.sh first)"
    echo "    - GCP APIs not enabled (Secret Manager, Compute Engine)"
    echo ""
    echo "  Check the error output above."
    exit 1
fi
echo -e "  ${GREEN}Infrastructure deployed!${NC}"

# =============================================================================
# [12/12] SAVE SSH KEY + SUMMARY
# =============================================================================

echo -e "\n${CYAN}[12/12] Saving SSH key and printing summary...${NC}"

terraform output -raw aws_ssh_private_key > "${TERRAFORM_DIR}/lab-key.pem" 2>/dev/null
chmod 600 "${TERRAFORM_DIR}/lab-key.pem" 2>/dev/null
echo -e "  ${GREEN}SSH key saved to terraform/lab-key.pem${NC}"

cd "${SCRIPT_DIR}"

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
AWS_IP=$(cd "${TERRAFORM_DIR}" && terraform output -raw aws_instance_public_ip 2>/dev/null || echo "?")
AZURE_IP=$(cd "${TERRAFORM_DIR}" && terraform output -raw azure_vm_public_ip 2>/dev/null || echo "?")
GCP_NAME=$(cd "${TERRAFORM_DIR}" && terraform output -raw gcp_instance_name 2>/dev/null || echo "?")
KV_NAME=$(cd "${TERRAFORM_DIR}" && terraform output -raw azure_keyvault_name 2>/dev/null || echo "?")

echo -e "  AWS EC2:        ${CYAN}${AWS_IP}${NC}"
echo -e "  Azure VM:       ${CYAN}${AZURE_IP}${NC}"
echo -e "  GCP GCE:        ${CYAN}${GCP_NAME}${NC}"
echo -e "  Key Vault:      ${CYAN}${KV_NAME}${NC}"
echo -e "  Verdaccio:      ${CYAN}http://localhost:4873${NC}"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  ${CYAN}source .venv/bin/activate${NC}"
echo -e "  ${CYAN}export GITHUB_PAT=ghp_...${NC}          # Classic PAT with repo+workflow scopes"
echo -e "  ${CYAN}export GITHUB_USERNAME=...${NC}          # Your GitHub username"
echo -e "  ${CYAN}export VICTIM_NPM_TOKEN=$(grep 'localhost:4873' ~/.npmrc 2>/dev/null | sed 's/.*_authToken=//' | sed 's/\"//g' | head -1)${NC}"
echo ""
echo -e "  ${CYAN}cd core${NC}"
echo -e "  ${CYAN}python main.py --auto       ${NC}# Full automated attack"
echo -e "  ${CYAN}python main.py --manual     ${NC}# Manual step-by-step"
echo -e "  ${CYAN}python main.py              ${NC}# Interactive menu"
echo ""
echo -e "  ${YELLOW}VMs need 3-5 minutes for startup scripts to complete.${NC}"
echo -e "  ${YELLOW}Wait before running Phase 2 (IMDS credential theft).${NC}"
echo ""
echo -e "  ${YELLOW}When done, clean up with:${NC} ${CYAN}./cleanup.sh${NC}"
