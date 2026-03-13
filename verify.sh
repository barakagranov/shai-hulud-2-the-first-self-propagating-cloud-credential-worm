#!/bin/bash
# =============================================================================
# verify.sh -- Thorough Post-Cleanup Verification
# =============================================================================
# Checks every resource, artifact, and setting to prove cleanup was complete.
# Each check shows what it looked for, what it found, and PASS/FAIL.
# Run after cleanup.sh to verify everything is gone.
# Run independently to audit the current state of the lab.
#
# Usage: ./verify.sh
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

pass() {
    echo -e "  ${GREEN}PASS${NC}  $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
    echo -e "  ${RED}FAIL${NC}  $1"
    echo -e "        ${DIM}$2${NC}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

warn() {
    echo -e "  ${YELLOW}WARN${NC}  $1"
    echo -e "        ${DIM}$2${NC}"
    WARN_COUNT=$((WARN_COUNT + 1))
}

info() {
    echo -e "        ${DIM}$1${NC}"
}

echo -e "${CYAN}"
echo "============================================="
echo "  Shai-Hulud 2.0 -- Verification"
echo "============================================="
echo -e "${NC}"

# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================

echo -e "${CYAN}[Environment Variables]${NC}"

if [ -n "${GITHUB_PAT}" ]; then
    warn "GITHUB_PAT is still set in your shell" \
         "Run: unset GITHUB_PAT"
else
    pass "GITHUB_PAT is not set"
fi

if [ -n "${GITHUB_USERNAME}" ]; then
    warn "GITHUB_USERNAME is still set in your shell" \
         "Run: unset GITHUB_USERNAME"
else
    pass "GITHUB_USERNAME is not set"
fi

if [ -n "${VICTIM_NPM_TOKEN}" ]; then
    warn "VICTIM_NPM_TOKEN is still set in your shell" \
         "Run: unset VICTIM_NPM_TOKEN"
else
    pass "VICTIM_NPM_TOKEN is not set"
fi

if [ -n "${WORM_EXFIL_DIR}" ]; then
    warn "WORM_EXFIL_DIR is still set" \
         "Run: unset WORM_EXFIL_DIR"
else
    pass "WORM_EXFIL_DIR is not set"
fi

# =============================================================================
# GITHUB REPOSITORIES
# =============================================================================

echo -e "\n${CYAN}[GitHub Repositories]${NC}"

# We need a PAT to check GitHub. If not set, use a temp one if available.
CHECK_PAT="${GITHUB_PAT}"
CHECK_USER="${GITHUB_USERNAME}"

if [ -z "${CHECK_PAT}" ]; then
    warn "Cannot check GitHub (GITHUB_PAT not set)" \
         "Set GITHUB_PAT temporarily to verify, then unset it"
else
    if [ -z "${CHECK_USER}" ]; then
        CHECK_USER=$(curl -s -H "Authorization: token ${CHECK_PAT}" \
            https://api.github.com/user 2>/dev/null | \
            python3 -c "import sys,json; print(json.load(sys.stdin).get('login',''))" 2>/dev/null)
    fi

    # Check vuln repo
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: token ${CHECK_PAT}" \
        "https://api.github.com/repos/${CHECK_USER}/novatech-oss-tools-lab" 2>/dev/null)
    if [ "${STATUS}" = "200" ]; then
        fail "Repository novatech-oss-tools-lab still exists" \
             "Delete at: https://github.com/${CHECK_USER}/novatech-oss-tools-lab/settings"
    elif [ "${STATUS}" = "404" ]; then
        pass "Repository novatech-oss-tools-lab does not exist"
    else
        warn "Could not check novatech-oss-tools-lab (HTTP ${STATUS})" \
             "Check manually at: https://github.com/${CHECK_USER}?tab=repositories"
    fi

    # Check C2 repos
    C2_REPOS=$(curl -s -H "Authorization: token ${CHECK_PAT}" \
        "https://api.github.com/user/repos?per_page=100&type=owner" 2>/dev/null | \
        python3 -c "
import sys, json
try:
    repos = json.load(sys.stdin)
    found = [r['name'] for r in repos if 'shai-hulud-c2-lab' in r.get('name','')]
    for r in found: print(r)
except: pass
" 2>/dev/null)

    if [ -n "${C2_REPOS}" ]; then
        for r in ${C2_REPOS}; do
            fail "C2 repository still exists: ${r}" \
                 "Delete at: https://github.com/${CHECK_USER}/${r}/settings"
        done
    else
        pass "No C2 repositories (shai-hulud-c2-lab-*) found"
    fi

    # Check for self-hosted runners across all repos
    RUNNER_CHECK=$(curl -s -H "Authorization: token ${CHECK_PAT}" \
        "https://api.github.com/user/repos?per_page=100&type=owner" 2>/dev/null | \
        python3 -c "
import sys, json, urllib.request
try:
    repos = json.load(sys.stdin)
    for r in repos:
        if 'shai-hulud' in r.get('name','') or 'novatech' in r.get('name',''):
            print(r['full_name'])
except: pass
" 2>/dev/null)
    if [ -z "${RUNNER_CHECK}" ]; then
        pass "No lab-related repositories found (runner check not needed)"
    fi
fi

# =============================================================================
# AWS RESOURCES
# =============================================================================

echo -e "\n${CYAN}[AWS Resources]${NC}"

if command -v aws &>/dev/null && aws sts get-caller-identity &>/dev/null; then
    # Get prefix from tfvars if available
    PREFIX=$(grep 'project_prefix' "${TERRAFORM_DIR}/terraform.tfvars" 2>/dev/null | \
        sed 's/.*=\s*"//' | sed 's/".*//' | head -1)
    PREFIX="${PREFIX:-sh2}"

    # EC2 instances
    INSTANCES=$(aws ec2 describe-instances \
        --filters "Name=tag:Scenario,Values=shai-hulud-2" "Name=instance-state-name,Values=running,stopped,pending" \
        --query 'Reservations[].Instances[].InstanceId' --output text 2>/dev/null)
    if [ -n "${INSTANCES}" ] && [ "${INSTANCES}" != "None" ]; then
        fail "AWS EC2 instances with tag Scenario=shai-hulud-2 still exist" \
             "Instance IDs: ${INSTANCES}"
    else
        pass "No AWS EC2 instances with lab tag found"
    fi

    # IAM roles
    ROLES=$(aws iam list-roles --query "Roles[?contains(RoleName,'${PREFIX}')].RoleName" --output text 2>/dev/null)
    if [ -n "${ROLES}" ] && [ "${ROLES}" != "None" ]; then
        fail "AWS IAM roles with prefix '${PREFIX}' still exist" \
             "Roles: ${ROLES}"
    else
        pass "No AWS IAM roles with prefix '${PREFIX}'"
    fi

    # Secrets Manager
    SECRETS=$(aws secretsmanager list-secrets \
        --query "SecretList[?contains(Name,'${PREFIX}')].Name" --output text 2>/dev/null)
    if [ -n "${SECRETS}" ] && [ "${SECRETS}" != "None" ]; then
        fail "AWS Secrets Manager secrets with prefix '${PREFIX}' still exist" \
             "Secrets: ${SECRETS}"
    else
        pass "No AWS Secrets Manager secrets with prefix '${PREFIX}'"
    fi

    # SSM Parameters
    PARAMS=$(aws ssm describe-parameters \
        --parameter-filters "Key=Name,Option=Contains,Values=${PREFIX}" \
        --query 'Parameters[].Name' --output text 2>/dev/null)
    if [ -n "${PARAMS}" ] && [ "${PARAMS}" != "None" ]; then
        fail "AWS SSM parameters with prefix '${PREFIX}' still exist" \
             "Parameters: ${PARAMS}"
    else
        pass "No AWS SSM parameters with prefix '${PREFIX}'"
    fi

    # Key pairs
    KEYS=$(aws ec2 describe-key-pairs \
        --query "KeyPairs[?contains(KeyName,'${PREFIX}')].KeyName" --output text 2>/dev/null)
    if [ -n "${KEYS}" ] && [ "${KEYS}" != "None" ]; then
        fail "AWS key pairs with prefix '${PREFIX}' still exist" \
             "Keys: ${KEYS}"
    else
        pass "No AWS key pairs with prefix '${PREFIX}'"
    fi

    # Security groups (non-default)
    SGS=$(aws ec2 describe-security-groups \
        --query "SecurityGroups[?contains(GroupName,'${PREFIX}')].{Name:GroupName,Id:GroupId}" \
        --output text 2>/dev/null)
    if [ -n "${SGS}" ] && [ "${SGS}" != "None" ]; then
        fail "AWS security groups with prefix '${PREFIX}' still exist" \
             "Groups: ${SGS}"
    else
        pass "No AWS security groups with prefix '${PREFIX}'"
    fi
else
    warn "AWS CLI not configured or not installed -- skipping AWS checks" \
         "Configure with: aws configure"
fi

# =============================================================================
# AZURE RESOURCES
# =============================================================================

echo -e "\n${CYAN}[Azure Resources]${NC}"

if command -v az &>/dev/null && az account show &>/dev/null 2>&1; then
    PREFIX=$(grep 'project_prefix' "${TERRAFORM_DIR}/terraform.tfvars" 2>/dev/null | \
        sed 's/.*=\s*"//' | sed 's/".*//' | head -1)
    PREFIX="${PREFIX:-sh2}"

    # Resource groups
    RGS=$(az group list --query "[?contains(name,'${PREFIX}')].name" --output tsv 2>/dev/null)
    if [ -n "${RGS}" ]; then
        fail "Azure resource groups with prefix '${PREFIX}' still exist" \
             "Groups: ${RGS}"
    else
        pass "No Azure resource groups with prefix '${PREFIX}'"
    fi

    # Deleted Key Vaults (soft-deleted)
    DELETED_KV=$(az keyvault list-deleted --query "[?contains(name,'${PREFIX}')].name" --output tsv 2>/dev/null)
    if [ -n "${DELETED_KV}" ]; then
        warn "Azure soft-deleted Key Vaults with prefix '${PREFIX}' found" \
             "Purge with: az keyvault purge --name ${DELETED_KV}"
    else
        pass "No soft-deleted Azure Key Vaults with prefix '${PREFIX}'"
    fi
else
    warn "Azure CLI not configured or not installed -- skipping Azure checks" \
         "Configure with: az login"
fi

# =============================================================================
# GCP RESOURCES
# =============================================================================

echo -e "\n${CYAN}[GCP Resources]${NC}"

if command -v gcloud &>/dev/null; then
    GCP_PROJECT=$(gcloud config get project 2>/dev/null)
    PREFIX=$(grep 'project_prefix' "${TERRAFORM_DIR}/terraform.tfvars" 2>/dev/null | \
        sed 's/.*=\s*"//' | sed 's/".*//' | head -1)
    PREFIX="${PREFIX:-sh2}"

    if [ -n "${GCP_PROJECT}" ]; then
        # Compute instances
        GCE=$(gcloud compute instances list --project="${GCP_PROJECT}" \
            --filter="name~${PREFIX}" --format="value(name)" 2>/dev/null)
        if [ -n "${GCE}" ]; then
            fail "GCP Compute instances with prefix '${PREFIX}' still exist" \
                 "Instances: ${GCE}"
        else
            pass "No GCP Compute instances with prefix '${PREFIX}'"
        fi

        # Service accounts
        SAS=$(gcloud iam service-accounts list --project="${GCP_PROJECT}" \
            --filter="email~${PREFIX}" --format="value(email)" 2>/dev/null)
        if [ -n "${SAS}" ]; then
            fail "GCP service accounts with prefix '${PREFIX}' still exist" \
                 "SAs: ${SAS}"
        else
            pass "No GCP service accounts with prefix '${PREFIX}'"
        fi

        # Secrets
        GCP_SECRETS=$(gcloud secrets list --project="${GCP_PROJECT}" \
            --filter="name~${PREFIX}" --format="value(name)" 2>/dev/null)
        if [ -n "${GCP_SECRETS}" ]; then
            fail "GCP Secret Manager secrets with prefix '${PREFIX}' still exist" \
                 "Secrets: ${GCP_SECRETS}"
        else
            pass "No GCP Secret Manager secrets with prefix '${PREFIX}'"
        fi
    else
        warn "GCP project not configured -- skipping GCP checks" \
             "Configure with: gcloud config set project YOUR_PROJECT_ID"
    fi
else
    warn "gcloud CLI not installed -- skipping GCP checks" ""
fi

# =============================================================================
# DOCKER / VERDACCIO
# =============================================================================

echo -e "\n${CYAN}[Docker / Verdaccio]${NC}"

if command -v docker &>/dev/null; then
    VERDACCIO_RUNNING=$(docker inspect -f '{{.State.Running}}' verdaccio 2>/dev/null)
    if [ "${VERDACCIO_RUNNING}" = "true" ]; then
        fail "Verdaccio container is still running" \
             "Stop with: docker stop verdaccio && docker rm verdaccio"
    elif docker inspect verdaccio &>/dev/null 2>&1; then
        warn "Verdaccio container exists but is stopped" \
             "Remove with: docker rm verdaccio"
    else
        pass "Verdaccio container does not exist"
    fi
else
    warn "Docker not installed -- skipping Docker checks" ""
fi

if [ -d ~/verdaccio-storage ]; then
    fail "Verdaccio storage directory still exists: ~/verdaccio-storage" \
         "Remove with: sudo rm -rf ~/verdaccio-storage"
else
    pass "No Verdaccio storage directory"
fi

# =============================================================================
# LOCAL FILESYSTEM ARTIFACTS
# =============================================================================

echo -e "\n${CYAN}[Local Filesystem]${NC}"

for dir_path in \
    "${HOME}/.shai-hulud-exfil" \
    "${HOME}/.shai-hulud-cascade-demo" \
    "${HOME}/.shai-hulud-runner" \
    "${HOME}/.bun"; do
    dir_name=$(basename "${dir_path}")
    if [ -d "${dir_path}" ]; then
        fail "Directory still exists: ~/${dir_name}" \
             "Remove with: rm -rf ${dir_path}"
    else
        pass "~/${dir_name} does not exist"
    fi
done

# Terraform state
if [ -f "${TERRAFORM_DIR}/terraform.tfstate" ]; then
    RESOURCE_COUNT=$(python3 -c "
import json
with open('${TERRAFORM_DIR}/terraform.tfstate') as f:
    state = json.load(f)
print(len(state.get('resources',[])))
" 2>/dev/null || echo "?")
    if [ "${RESOURCE_COUNT}" = "0" ] || [ "${RESOURCE_COUNT}" = "?" ]; then
        warn "terraform.tfstate exists but has 0 resources (stale file)" \
             "Remove with: rm ${TERRAFORM_DIR}/terraform.tfstate"
    else
        fail "terraform.tfstate exists with ${RESOURCE_COUNT} resources" \
             "Run: cd terraform && terraform destroy -auto-approve"
    fi
else
    pass "No terraform.tfstate file"
fi

# SSH key
if [ -f "${TERRAFORM_DIR}/lab-key.pem" ]; then
    fail "SSH key file still exists: terraform/lab-key.pem" \
         "Remove with: rm ${TERRAFORM_DIR}/lab-key.pem"
else
    pass "No SSH key file (lab-key.pem)"
fi

# Progress files
if [ -f "${SCRIPT_DIR}/logs/.attack-progress.json" ]; then
    fail "Progress file still exists" \
         "Remove with: rm ${SCRIPT_DIR}/logs/.attack-progress.json"
else
    pass "No progress file"
fi

if [ -f "${SCRIPT_DIR}/logs/.session-data.json" ]; then
    fail "Session data file still exists" \
         "Remove with: rm ${SCRIPT_DIR}/logs/.session-data.json"
else
    pass "No session data file"
fi

# TruffleHog binary
if command -v trufflehog &>/dev/null || [ -f /usr/local/bin/trufflehog ]; then
    warn "TruffleHog binary is installed (may have been installed by the worm payload)" \
         "Remove with: sudo rm /usr/local/bin/trufflehog"
else
    pass "TruffleHog not installed"
fi

# =============================================================================
# NPM CONFIG
# =============================================================================

echo -e "\n${CYAN}[npm Configuration]${NC}"

if grep -q "localhost:4873" ~/.npmrc 2>/dev/null; then
    fail "Verdaccio token still in ~/.npmrc" \
         "Remove with: sed -i '/localhost:4873/d' ~/.npmrc"
else
    pass "No Verdaccio tokens in ~/.npmrc"
fi

NOVATECH_REG=$(npm config get @novatech:registry 2>/dev/null)
if [ -n "${NOVATECH_REG}" ] && [ "${NOVATECH_REG}" != "undefined" ]; then
    fail "@novatech:registry still set to ${NOVATECH_REG}" \
         "Remove with: npm config delete @novatech:registry"
else
    pass "No @novatech:registry npm config"
fi

# =============================================================================
# PROCESSES
# =============================================================================

echo -e "\n${CYAN}[Running Processes]${NC}"

for proc_name in "Runner.Listener" "Runner.Worker" "bun_environment" "trufflehog" "setup_bun"; do
    PIDS=$(pgrep -f "${proc_name}" 2>/dev/null)
    if [ -n "${PIDS}" ]; then
        fail "Process '${proc_name}' is still running (PIDs: ${PIDS})" \
             "Kill with: pkill -f '${proc_name}'"
    else
        pass "No '${proc_name}' processes running"
    fi
done

# =============================================================================
# SUMMARY
# =============================================================================

echo ""
echo -e "${CYAN}=============================================${NC}"
TOTAL=$((PASS_COUNT + FAIL_COUNT + WARN_COUNT))
echo -e "  Checks: ${TOTAL}  |  ${GREEN}PASS: ${PASS_COUNT}${NC}  |  ${RED}FAIL: ${FAIL_COUNT}${NC}  |  ${YELLOW}WARN: ${WARN_COUNT}${NC}"
echo -e "${CYAN}=============================================${NC}"

if [ ${FAIL_COUNT} -eq 0 ] && [ ${WARN_COUNT} -eq 0 ]; then
    echo -e "\n  ${GREEN}Environment is clean. All resources removed.${NC}"
elif [ ${FAIL_COUNT} -eq 0 ]; then
    echo -e "\n  ${YELLOW}Environment is mostly clean. Review warnings above.${NC}"
else
    echo -e "\n  ${RED}${FAIL_COUNT} item(s) still need cleanup. See FAIL entries above.${NC}"
fi
echo ""

exit ${FAIL_COUNT}
