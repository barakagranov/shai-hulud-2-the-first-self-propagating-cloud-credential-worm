#!/bin/bash
# =============================================================================
# cleanup.sh -- Complete Cleanup for Shai-Hulud 2.0
# =============================================================================
# Removes ALL resources created during the lab:
#   1. GitHub repositories (attack-created, not managed by Terraform)
#   2. Self-hosted runner files
#   3. Verdaccio Docker container + storage
#   4. Terraform infrastructure (AWS + Azure + GCP)
#   5. Local artifacts (venv, exfil dirs, Bun, npm config)
#
# IMPORTANT: No set -e. Cleanup is best-effort. If one step fails, we
# continue. A half-cleanup is worse than a full attempt.
#
# Usage: ./cleanup.sh
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/terraform"

ERRORS=0

echo -e "${CYAN}"
echo "============================================="
echo "  Shai-Hulud 2.0 -- Cleanup"
echo "============================================="
echo -e "${NC}"

# =============================================================================
# [1/8] DELETE GITHUB REPOSITORIES (attack-created, not Terraform)
# =============================================================================

echo -e "${CYAN}[1/8] Deleting GitHub repositories...${NC}"

if [ -n "${GITHUB_PAT}" ] && [ -n "${GITHUB_USERNAME}" ]; then
    # Delete the vulnerable repo
    for REPO_NAME in "novatech-oss-tools-lab"; do
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "Authorization: token ${GITHUB_PAT}" \
            "https://api.github.com/repos/${GITHUB_USERNAME}/${REPO_NAME}" 2>/dev/null)

        if [ "${STATUS}" = "200" ]; then
            curl -s -X DELETE \
                -H "Authorization: token ${GITHUB_PAT}" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/repos/${GITHUB_USERNAME}/${REPO_NAME}" 2>/dev/null
            echo -e "  ${GREEN}Deleted: ${REPO_NAME}${NC}"
        else
            echo -e "  ${YELLOW}${REPO_NAME} not found (already deleted or never created)${NC}"
        fi
    done

    # Delete C2 repos (name pattern: shai-hulud-c2-lab-*)
    echo "  Searching for C2 repos..."
    C2_REPOS=$(curl -s -H "Authorization: token ${GITHUB_PAT}" \
        "https://api.github.com/user/repos?per_page=100&type=owner" 2>/dev/null | \
        python3 -c "
import sys, json
try:
    repos = json.load(sys.stdin)
    for r in repos:
        if 'shai-hulud-c2-lab' in r.get('name',''):
            print(r['name'])
except: pass
" 2>/dev/null)

    if [ -n "${C2_REPOS}" ]; then
        for REPO_NAME in ${C2_REPOS}; do
            curl -s -X DELETE \
                -H "Authorization: token ${GITHUB_PAT}" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/repos/${GITHUB_USERNAME}/${REPO_NAME}" 2>/dev/null
            echo -e "  ${GREEN}Deleted C2 repo: ${REPO_NAME}${NC}"
        done
    else
        echo -e "  ${YELLOW}No C2 repos found${NC}"
    fi
else
    echo -e "  ${YELLOW}GITHUB_PAT or GITHUB_USERNAME not set. Skipping GitHub cleanup.${NC}"
    echo -e "  ${YELLOW}To clean manually: delete repos starting with 'novatech-oss' and 'shai-hulud-c2'${NC}"
    ERRORS=$((ERRORS + 1))
fi

# =============================================================================
# [2/8] REMOVE SELF-HOSTED RUNNER
# =============================================================================

echo -e "\n${CYAN}[2/8] Removing self-hosted runner...${NC}"

RUNNER_DIR="${HOME}/.shai-hulud-runner"
if [ -d "${RUNNER_DIR}" ]; then
    # Kill the runner process first
    pkill -f "Runner.Listener" 2>/dev/null || true
    pkill -f "Runner.Worker" 2>/dev/null || true
    sleep 2
    echo -e "  ${GREEN}Runner process stopped${NC}"

    # Try to deregister from GitHub (needs a removal token)
    if [ -n "${GITHUB_PAT}" ] && [ -n "${GITHUB_USERNAME}" ] && [ -f "${RUNNER_DIR}/.runner" ]; then
        # Read the repo URL from the runner config
        RUNNER_REPO=$(python3 -c "import json; print(json.load(open('${RUNNER_DIR}/.runner')).get('gitHubUrl',''))" 2>/dev/null)
        if [ -n "${RUNNER_REPO}" ]; then
            # Extract owner/repo from URL
            REPO_PATH=$(echo "${RUNNER_REPO}" | sed 's|https://github.com/||')
            REMOVE_TOKEN=$(curl -s -X POST \
                -H "Authorization: token ${GITHUB_PAT}" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/repos/${REPO_PATH}/actions/runners/remove-token" 2>/dev/null | \
                python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)

            if [ -n "${REMOVE_TOKEN}" ] && [ "${REMOVE_TOKEN}" != "" ]; then
                RUNNER_ALLOW_RUNASROOT=1 "${RUNNER_DIR}/config.sh" remove --token "${REMOVE_TOKEN}" 2>/dev/null && \
                    echo -e "  ${GREEN}Runner deregistered from GitHub${NC}" || \
                    echo -e "  ${YELLOW}Deregistration failed (repo may already be deleted)${NC}"
            fi
        fi
    fi

    rm -rf "${RUNNER_DIR}"
    echo -e "  ${GREEN}Runner files removed${NC}"
else
    echo -e "  ${YELLOW}No runner directory found${NC}"
fi

# =============================================================================
# [3/8] STOP AND REMOVE VERDACCIO
# =============================================================================

echo -e "\n${CYAN}[3/8] Removing Verdaccio...${NC}"

if docker inspect verdaccio &>/dev/null; then
    docker stop verdaccio 2>/dev/null && docker rm verdaccio 2>/dev/null
    echo -e "  ${GREEN}Verdaccio container removed${NC}"
else
    echo -e "  ${YELLOW}Verdaccio container not found${NC}"
fi

if [ -d ~/verdaccio-storage ]; then
    sudo rm -rf ~/verdaccio-storage 2>/dev/null || rm -rf ~/verdaccio-storage 2>/dev/null
    echo -e "  ${GREEN}Verdaccio storage removed${NC}"
fi

# Remove Verdaccio tokens and scope from npmrc
sed -i '/localhost:4873/d' ~/.npmrc 2>/dev/null || true
npm config delete @novatech:registry 2>/dev/null || true
echo -e "  ${GREEN}npm config cleaned${NC}"

# =============================================================================
# [4/8] TERRAFORM DESTROY
# =============================================================================

TF_DESTROY_SUCCESS=false

echo -e "\n${CYAN}[4/8] Running terraform destroy (AWS + Azure + GCP)...${NC}"
echo -e "  ${YELLOW}This removes infrastructure from all three clouds. Takes 3-5 minutes.${NC}"

if [ -f "${TERRAFORM_DIR}/terraform.tfstate" ]; then
    cd "${TERRAFORM_DIR}"
    if terraform destroy -auto-approve -input=false; then
        echo -e "  ${GREEN}Terraform resources destroyed${NC}"
        TF_DESTROY_SUCCESS=true
    else
        echo -e "  ${RED}terraform destroy failed (see errors above)${NC}"
        echo -e "  ${YELLOW}Some resources may still exist. Check all three cloud consoles.${NC}"
        ERRORS=$((ERRORS + 1))
    fi
    cd "${SCRIPT_DIR}"
else
    echo -e "  ${YELLOW}No terraform.tfstate found. Skipping.${NC}"
fi

# =============================================================================
# [5/8] CLEAN UP LOCAL ARTIFACTS
# =============================================================================

echo -e "\n${CYAN}[5/8] Cleaning up local artifacts...${NC}"

# Progress and session files
rm -f "${SCRIPT_DIR}/logs/.attack-progress.json" 2>/dev/null || true
rm -f "${SCRIPT_DIR}/logs/.session-data.json" 2>/dev/null || true

# Terraform internals
rm -rf "${TERRAFORM_DIR}/.terraform" 2>/dev/null && echo -e "  ${GREEN}Removed .terraform/${NC}" || true

# Only delete state files if terraform destroy succeeded
if [ "${TF_DESTROY_SUCCESS}" = true ]; then
    rm -f "${TERRAFORM_DIR}/terraform.tfstate" 2>/dev/null && echo -e "  ${GREEN}Removed terraform.tfstate${NC}" || true
    rm -f "${TERRAFORM_DIR}/terraform.tfstate.backup" 2>/dev/null || true
else
    echo -e "  ${YELLOW}Keeping terraform.tfstate (destroy had errors)${NC}"
fi
rm -f "${TERRAFORM_DIR}/.terraform.lock.hcl" 2>/dev/null || true
rm -f "${TERRAFORM_DIR}/lab-key.pem" 2>/dev/null && echo -e "  ${GREEN}Removed SSH key${NC}" || true

# Python cache
find "${SCRIPT_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo -e "  ${GREEN}Local artifacts cleaned${NC}"

# =============================================================================
# [6/8] CLEAN UP EXFILTRATION AND WORM ARTIFACTS
# =============================================================================

echo -e "\n${CYAN}[6/8] Cleaning worm artifacts...${NC}"

rm -rf ~/.shai-hulud-exfil 2>/dev/null && echo -e "  ${GREEN}Removed ~/.shai-hulud-exfil${NC}" || true
rm -rf ~/.shai-hulud-cascade-demo 2>/dev/null && echo -e "  ${GREEN}Removed cascade demo${NC}" || true
rm -rf ~/.bun 2>/dev/null && echo -e "  ${GREEN}Removed Bun runtime${NC}" || true

# Kill any lingering bun/trufflehog processes
pkill -f "bun_environment" 2>/dev/null || true
pkill -f "trufflehog" 2>/dev/null || true

echo -e "  ${GREEN}Worm artifacts cleaned${NC}"

# =============================================================================
# [7/8] CLEAR ENVIRONMENT VARIABLES
# =============================================================================

echo -e "\n${CYAN}[7/8] Clearing environment variables...${NC}"

# Note: these only affect the current shell session
unset GITHUB_PAT GITHUB_USERNAME VICTIM_NPM_TOKEN 2>/dev/null || true
unset WORM_EXFIL_DIR WORM_DRY_RUN WORM_REGISTRY WORM_NPM_TOKEN 2>/dev/null || true

# Clean AWS CLI attacker profiles
for PROFILE in attacker attacker-admin; do
    aws configure set aws_access_key_id "" --profile "${PROFILE}" 2>/dev/null || true
    aws configure set aws_secret_access_key "" --profile "${PROFILE}" 2>/dev/null || true
done
echo -e "  ${GREEN}Environment cleaned${NC}"

# =============================================================================
# [8/8] VERIFICATION CHECKLIST
# =============================================================================

echo -e "\n${CYAN}[8/8] Verification checklist${NC}"
echo -e "${YELLOW}"
echo "  Verify in each cloud console:"
echo ""
echo "  AWS:"
echo "    [ ] EC2: No instances with your prefix"
echo "    [ ] IAM: No roles/profiles with your prefix"
echo "    [ ] Secrets Manager: No secrets with your prefix"
echo "    [ ] SSM: No parameters with your prefix"
echo "    [ ] Key Pairs: No pairs with your prefix"
echo ""
echo "  Azure:"
echo "    [ ] Resource Groups: Lab RG deleted"
echo "    [ ] Key Vault: Check 'Deleted vaults' and purge if needed"
echo ""
echo "  GCP:"
echo "    [ ] Compute Engine: No instances with your prefix"
echo "    [ ] Service Accounts: No SAs with your prefix"
echo "    [ ] Secret Manager: No secrets with your prefix"
echo ""
echo "  GitHub:"
echo "    [ ] Both lab repos deleted (novatech-oss-tools-lab, shai-hulud-c2-*)"
echo "    [ ] No self-hosted runners (Settings > Actions > Runners)"
echo ""
echo "  Local:"
echo "    [ ] ~/.shai-hulud-* directories removed"
echo "    [ ] ~/.bun directory removed"
echo "    [ ] ~/.npmrc has no Verdaccio tokens"
echo "    [ ] No bun or trufflehog processes: ps aux | grep -E 'bun|trufflehog'"
echo -e "${NC}"

if [ ${ERRORS} -gt 0 ]; then
    echo -e "${YELLOW}=============================================${NC}"
    echo -e "${YELLOW}  Cleanup finished with ${ERRORS} warning(s).${NC}"
    echo -e "${YELLOW}  Check the output above and verify manually.${NC}"
    echo -e "${YELLOW}=============================================${NC}"
else
    echo -e "${GREEN}=============================================${NC}"
    echo -e "${GREEN}  Cleanup Complete!${NC}"
    echo -e "${GREEN}=============================================${NC}"
fi
