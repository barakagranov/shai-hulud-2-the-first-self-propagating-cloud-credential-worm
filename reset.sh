#!/bin/bash
# =============================================================================
# reset.sh -- Soft Reset for Re-Running the Attack
# =============================================================================
# Cleans everything the ATTACK created, but keeps infrastructure alive:
#   - Terraform VMs (AWS/Azure/GCP) stay running
#   - Verdaccio container stays running (packages reset to clean versions)
#   - Python venv stays intact
#   - Cloud CLI credentials stay configured
#
# After running this, you can immediately do: cd core && python main.py
# No need to re-run setup.sh (saves 5+ minutes of Terraform deploy).
#
# Usage: ./reset.sh
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${CYAN}"
echo "============================================="
echo "  Shai-Hulud 2.0 -- Soft Reset"
echo "  (keeps infrastructure, resets attack state)"
echo "============================================="
echo -e "${NC}"

# =============================================================================
# [1/7] STOP RUNNER PROCESS
# =============================================================================

echo -e "${CYAN}[1/7] Stopping self-hosted runner...${NC}"

RUNNER_DIR="${HOME}/.shai-hulud-runner"
if [ -d "${RUNNER_DIR}" ]; then
    pkill -f "Runner.Listener" 2>/dev/null || true
    pkill -f "Runner.Worker" 2>/dev/null || true
    sleep 1

    # Deregister if possible
    if [ -n "${GITHUB_PAT}" ] && [ -f "${RUNNER_DIR}/.runner" ]; then
        RUNNER_REPO=$(python3 -c "import json; print(json.load(open('${RUNNER_DIR}/.runner')).get('gitHubUrl',''))" 2>/dev/null)
        if [ -n "${RUNNER_REPO}" ]; then
            REPO_PATH=$(echo "${RUNNER_REPO}" | sed 's|https://github.com/||')
            REMOVE_TOKEN=$(curl -s -X POST \
                -H "Authorization: token ${GITHUB_PAT}" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/repos/${REPO_PATH}/actions/runners/remove-token" 2>/dev/null | \
                python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
            if [ -n "${REMOVE_TOKEN}" ]; then
                RUNNER_ALLOW_RUNASROOT=1 "${RUNNER_DIR}/config.sh" remove --token "${REMOVE_TOKEN}" 2>/dev/null && \
                    echo -e "  ${GREEN}Runner deregistered${NC}" || true
            fi
        fi
    fi
    rm -rf "${RUNNER_DIR}"
    echo -e "  ${GREEN}Runner removed${NC}"
else
    echo -e "  ${YELLOW}No runner found${NC}"
fi

# =============================================================================
# [2/7] DELETE GITHUB REPOSITORIES
# =============================================================================

echo -e "\n${CYAN}[2/7] Deleting GitHub lab repositories...${NC}"

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
            echo -e "  ${YELLOW}${REPO_NAME} not found${NC}"
        fi
    done

    # Delete C2 repos
    C2_REPOS=$(curl -s -H "Authorization: token ${GITHUB_PAT}" \
        "https://api.github.com/user/repos?per_page=100&type=owner" 2>/dev/null | \
        python3 -c "
import sys, json
try:
    for r in json.load(sys.stdin):
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
    echo -e "  ${YELLOW}GITHUB_PAT or GITHUB_USERNAME not set -- cannot clean GitHub repos${NC}"
    echo -e "  ${YELLOW}Delete manually: repos starting with 'novatech-oss' and 'shai-hulud-c2'${NC}"
fi

# =============================================================================
# [3/7] RESET VERDACCIO PACKAGES
# =============================================================================

echo -e "\n${CYAN}[3/7] Resetting Verdaccio packages to clean versions...${NC}"

# Check if Verdaccio is running
if ! curl -sf http://localhost:4873/-/ping &>/dev/null; then
    echo -e "  ${YELLOW}Verdaccio not running -- skipping package reset${NC}"
else
    # Restart Verdaccio with fresh storage to remove all infected packages
    echo -e "  Stopping Verdaccio..."
    docker stop verdaccio 2>/dev/null && docker rm verdaccio 2>/dev/null

    # Clear storage
    sudo rm -rf ~/verdaccio-storage 2>/dev/null || rm -rf ~/verdaccio-storage 2>/dev/null
    mkdir -p ~/verdaccio-storage
    sudo chown 10001:65533 ~/verdaccio-storage 2>/dev/null || true

    # Restart
    docker run -d --name verdaccio -p 4873:4873 \
        -v ~/verdaccio-storage:/verdaccio/storage \
        verdaccio/verdaccio:latest 2>/dev/null
    echo -e "  Waiting for Verdaccio startup..."
    sleep 5

    if curl -sf http://localhost:4873/-/ping &>/dev/null; then
        echo -e "  ${GREEN}Verdaccio restarted with fresh storage${NC}"

        # Re-register user via Verdaccio REST API (npm adduser is interactive in npm 10+)
        echo -e "  Re-registering npm user (novatech-bot)..."
        sed -i '/localhost:4873/d' ~/.npmrc 2>/dev/null || true

        AUTH_RESPONSE=$(curl -s -X PUT \
            -H "Content-Type: application/json" \
            -d '{"name":"novatech-bot","password":"novatech123","email":"bot@novatech.dev"}' \
            "http://localhost:4873/-/user/org.couchdb.user:novatech-bot" 2>/dev/null)

        NEW_NPM_TOKEN=$(echo "${AUTH_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)

        if [ -n "${NEW_NPM_TOKEN}" ] && [ "${NEW_NPM_TOKEN}" != "" ]; then
            echo "//localhost:4873/:_authToken=\"${NEW_NPM_TOKEN}\"" >> ~/.npmrc
            npm config set @novatech:registry http://localhost:4873
            echo -e "  ${GREEN}Verdaccio user registered and token saved${NC}"
        else
            echo -e "  ${RED}Failed to register Verdaccio user. Try manually: npm adduser --registry http://localhost:4873${NC}"
        fi

        # Republish clean packages
        TEMP_DIR=$(mktemp -d)
        for pkg_info in \
            "auth-helpers:2.4.1:NovaTech authentication helper utilities" \
            "db-connector:1.8.3:NovaTech database connection pool manager" \
            "logger:3.1.0:NovaTech structured logging library" \
            "config-loader:1.2.0:NovaTech configuration loader with environment support" \
            "api-client:4.0.2:NovaTech internal API client SDK"; do

            IFS=':' read -r name version desc <<< "${pkg_info}"
            dir="${TEMP_DIR}/novatech-${name}"
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
            echo "module.exports = { ping: () => 'pong from @novatech/${name}@${version}' };" > "${dir}/index.js"
            npm publish "${dir}" --registry http://localhost:4873 2>/dev/null && \
                echo -e "  ${GREEN}Published clean @novatech/${name}@${version}${NC}" || \
                echo -e "  ${YELLOW}@novatech/${name} publish issue${NC}"
        done
        rm -rf "${TEMP_DIR}"

        # Update VICTIM_NPM_TOKEN
        NEW_TOKEN=$(grep "localhost:4873" ~/.npmrc 2>/dev/null | grep "_authToken" | sed 's/.*_authToken=//' | sed 's/"//g')
        if [ -n "${NEW_TOKEN}" ]; then
            echo -e "  ${GREEN}New npm token available${NC}"
            echo -e "  ${YELLOW}Run: export VICTIM_NPM_TOKEN=${NEW_TOKEN}${NC}"
        fi
    else
        echo -e "  ${RED}Verdaccio failed to restart${NC}"
    fi
fi

# =============================================================================
# [4/7] CLEAN WORM ARTIFACTS
# =============================================================================

echo -e "\n${CYAN}[4/7] Cleaning worm artifacts...${NC}"

rm -rf ~/.shai-hulud-exfil 2>/dev/null && echo -e "  ${GREEN}Removed ~/.shai-hulud-exfil${NC}" || true
rm -rf ~/.shai-hulud-cascade-demo 2>/dev/null && echo -e "  ${GREEN}Removed cascade demo dir${NC}" || true
rm -rf ~/.bun 2>/dev/null && echo -e "  ${GREEN}Removed ~/.bun (Bun runtime)${NC}" || true

# Kill lingering processes
pkill -f "bun_environment" 2>/dev/null || true
pkill -f "trufflehog" 2>/dev/null || true
echo -e "  ${GREEN}Killed lingering processes${NC}"

# =============================================================================
# [5/7] CLEAR PROGRESS AND SESSION FILES
# =============================================================================

echo -e "\n${CYAN}[5/7] Clearing progress and session data...${NC}"

rm -f "${SCRIPT_DIR}/logs/.attack-progress.json" 2>/dev/null
rm -f "${SCRIPT_DIR}/logs/.session-data.json" 2>/dev/null
echo -e "  ${GREEN}Progress and session files cleared${NC}"

# =============================================================================
# [6/7] CLEAN AWS CLI ATTACKER PROFILES
# =============================================================================

echo -e "\n${CYAN}[6/7] Cleaning AWS CLI attacker profiles...${NC}"
for PROFILE in attacker attacker-admin; do
    aws configure set aws_access_key_id "" --profile "${PROFILE}" 2>/dev/null || true
    aws configure set aws_secret_access_key "" --profile "${PROFILE}" 2>/dev/null || true
done
echo -e "  ${GREEN}Cleared attacker profiles${NC}"

# =============================================================================
# [7/7] SUMMARY
# =============================================================================

echo ""
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN}  Soft Reset Complete!${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo -e "  ${YELLOW}What was reset:${NC}"
echo "    - GitHub repos (vuln + C2) deleted"
echo "    - Verdaccio packages restored to clean versions"
echo "    - Runner stopped and removed"
echo "    - Worm artifacts (~/.bun, ~/.shai-hulud-*) deleted"
echo "    - Progress tracking cleared"
echo ""
echo -e "  ${YELLOW}What was kept:${NC}"
echo "    - Terraform infrastructure (AWS/Azure/GCP VMs still running)"
echo "    - Python venv and dependencies"
echo "    - Cloud CLI credentials"
echo "    - Verdaccio container (restarted with clean packages)"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  ${CYAN}source .venv/bin/activate${NC}"
echo -e "  ${CYAN}export GITHUB_PAT=${GITHUB_PAT}${NC}"
echo -e "  ${CYAN}export GITHUB_USERNAME=${GITHUB_USERNAME}${NC}"
NEW_TOKEN=$(grep "localhost:4873" ~/.npmrc 2>/dev/null | grep "_authToken" | sed 's/.*_authToken=//' | sed 's/"//g')
echo -e "  ${CYAN}export VICTIM_NPM_TOKEN=${NEW_TOKEN}${NC}"
echo -e "  ${CYAN}cd core && python main.py${NC}"
