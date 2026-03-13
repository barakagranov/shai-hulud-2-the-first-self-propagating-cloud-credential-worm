# The Second Coming: Shai-Hulud 2.0

**Supply Chain Worm Simulation** | **AWS + Azure + GCP** | **Expert** | **Based on a Real Attack**

Recreate the Shai-Hulud 2.0 supply chain worm that compromised 796 npm packages, created 25,000+ GitHub repositories, and stole 14,000 secrets across 487 organizations in November 2025.

---

## Attack Chain

```
     PHASE 0: INITIAL ACCESS
     +----------------------------------------------------------+
     | pull_request_target EXPLOIT                               |
     | Submit PR -> workflow runs attacker code with secrets     |
     | NPM_TOKEN exfiltrated via workflow execution              |
     | MITRE: T1195.002, T1552.008                              |
     +----------------------------+-----------------------------+
                                  |
     PHASE 1: PAYLOAD DELIVERY    v
     +----------------------------------------------------------+
     | MALICIOUS PACKAGE INJECTION                               |
     | preinstall hook -> Bun dropper -> credential harvester   |
     | MITRE: T1195.002, T1036.004, T1546                      |
     +----------------------------+-----------------------------+
                                  |
     PHASE 2: CREDENTIAL          v
     HARVESTING
     +-----------+----------------+-----------------+
     |           |                                  |
     v           v                                  v
     +---------+ +----------+ +----------+
     | AWS     | | AZURE    | | GCP      |
     | IMDSv1  | | IMDS +   | | metadata |
     | no auth | | MI token | | SA token |
     | Secrets | | Key Vault| | Secret   |
     | Manager | | REST API | | Manager  |
     | + SSM   | |          | | REST API |
     +---------+ +----------+ +----------+
     |           |                       |
     +-----------+-----------+-----------+
                             |
     PHASE 3: SELF-          v
     PROPAGATION
     +----------------------------------------------------------+
     | Enumerate victim's packages -> inject -> republish        |
     | Cascading infection through transitive dependencies      |
     | MITRE: T1195.002, T1546                                  |
     +----------------------------+-----------------------------+
                                  |
     PHASE 4: PERSISTENCE         v
     +----------------------------------------------------------+
     | GitHub repo with campaign marker + triple-B64 exfil      |
     | Self-hosted runner "SHA1HULUD" + Discussion-based C2     |
     | MITRE: T1098, T1059.009, T1567.001, T1102.002           |
     +----------------------------+-----------------------------+
                                  |
     PHASE 5: DEAD MAN'S SWITCH   v
     +----------------------------------------------------------+
     | Documented only -- NEVER EXECUTED                         |
     | shred -uvz on Linux / cipher /W on Windows               |
     | MITRE: T1485, T1490                                      |
     +----------------------------------------------------------+
```

---

## Prerequisites

You need **all** of these before running the lab:

| Tool | Version | Check Command | Install Guide |
|------|---------|---------------|---------------|
| Terraform | >= 1.11.0 | `terraform --version` | [terraform.io](https://developer.hashicorp.com/terraform/install) |
| AWS CLI v2 | 2.x | `aws --version` | [AWS docs](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) |
| Azure CLI | 2.x | `az version` | [MS docs](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) |
| Google Cloud CLI | 4xx+ | `gcloud --version` | [GCP docs](https://cloud.google.com/sdk/docs/install) |
| Docker | any | `docker --version` | [docker.com](https://docs.docker.com/get-docker/) |
| Node.js | >= 20 | `node --version` | [nodejs.org](https://nodejs.org/) |
| npm | >= 10 | `npm --version` | (included with Node.js) |
| Python | >= 3.11 | `python3 --version` | [python.org](https://www.python.org/) |
| jq | any | `jq --version` | `sudo apt install jq` |
| GitHub PAT | classic | [github.com/settings/tokens](https://github.com/settings/tokens) | Scopes: `repo`, `workflow`, `delete_repo` |

**Dedicated lab accounts on all three clouds.** NEVER use production accounts.

### GitHub Personal Access Token (PAT)

The lab needs a **classic** GitHub PAT for the pull_request_target exploit (Phase 0), persistence (Phase 4), and cleanup (deleting lab repos). Create one at [github.com/settings/tokens](https://github.com/settings/tokens):

1. Click **"Generate new token"** > **"Generate new token (classic)"**
2. Set a note like "Shai-Hulud 2.0 Lab"
3. Set expiration to 7 days (or shorter -- you only need it for the lab)
4. Select these scopes:
   - **`repo`** -- Full control of private repositories (create repos, manage secrets, configure runners)
   - **`workflow`** -- Update GitHub Action workflows (create workflow files via API)
   - **`delete_repo`** -- Delete repositories (needed for cleanup.sh to remove lab repos)
5. Click **"Generate token"** and copy the value (starts with `ghp_`)

Verify it works:

```bash
export GITHUB_PAT="ghp_your_token_here"
curl -s -H "Authorization: token ${GITHUB_PAT}" https://api.github.com/user | jq '.login'
```

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/BarakAgranov/shai-hulud-2.git
cd shai-hulud-2

# One-command setup (checks prereqs, starts Verdaccio, deploys to 3 clouds)
./setup.sh

# Set GitHub and npm credentials
source .venv/bin/activate
export GITHUB_PAT="ghp_..."
export GITHUB_USERNAME="your-username"
export VICTIM_NPM_TOKEN="<from setup.sh output>"

# Run the attack
cd core
python main.py --auto          # Full automated attack chain
```

The `setup.sh` script handles: prerequisite checks across 10+ tools, cloud credential validation, Verdaccio startup, victim package publishing, Python venv creation, dependency installation, Terraform configuration auto-fill, and multi-cloud infrastructure deployment. Safe to re-run.

---

## Usage

### Execution Modes

```bash
cd core

python main.py                 # Interactive step-level menu
python main.py --auto          # Full automated attack chain
python main.py --auto --fresh  # Clear progress and run from scratch
python main.py --manual        # Print SSH commands for manual execution
python main.py --auto --log    # Attack with structured logging
python main.py status          # Check lab environment health
python main.py report          # Generate report from last log
```

In interactive mode, you can run individual steps (`2.1`), entire phases (`2` or `p2`), or everything (`all`). Steps marked DONE are tracked across restarts.

---

## Cleanup & Reset

### Re-run the attack (keep infrastructure)

```bash
# Soft reset: deletes GitHub repos, resets Verdaccio, clears progress (~15 seconds)
./reset.sh

# Then re-run
source .venv/bin/activate
export GITHUB_PAT="ghp_..."  # reset.sh prints the exact commands
export GITHUB_USERNAME="..."
export VICTIM_NPM_TOKEN="..."  # new token printed by reset.sh
cd core && python main.py
```

`reset.sh` keeps Terraform VMs running (saves 5-10 minutes of redeploy). It resets Verdaccio to clean packages, deletes GitHub repos, stops the runner, and clears all worm artifacts.

### Full teardown

```bash
# Remove everything: GitHub repos + runner + Verdaccio + Terraform + local artifacts
./cleanup.sh

# Then verify nothing is left
./verify.sh

# Finally, clear env vars in your shell (cleanup.sh cannot do this for you)
unset GITHUB_PAT GITHUB_USERNAME VICTIM_NPM_TOKEN WORM_EXFIL_DIR WORM_DRY_RUN
```

`cleanup.sh` takes 5-10 minutes (Azure Key Vault soft-delete/purge is slow). It deletes all cloud resources, GitHub repos, the runner, Verdaccio container and storage, and local artifacts.

`verify.sh` checks ~30 items across all three clouds, GitHub, Docker, local filesystem, npm config, processes, and environment variables. Each check shows PASS/FAIL/WARN with the actual finding and the fix command.

---

## MITRE ATT&CK Mapping

| Phase | Technique | ID | Tactic |
|-------|-----------|-----|--------|
| 0 | Supply Chain Compromise | T1195.002 | Initial Access |
| 0 | Unsecured Credentials: CI/CD | T1552.008 | Credential Access |
| 1 | Masquerading (Bun) | T1036.004 | Defense Evasion |
| 1 | Event Triggered Execution | T1546 | Persistence |
| 2 | Cloud Instance Metadata API | T1552.005 | Credential Access |
| 2 | Steal Application Access Token | T1528 | Credential Access |
| 2 | Cloud Secrets Mgmt Stores | T1555.006 | Credential Access |
| 3 | Supply Chain Compromise | T1195.002 | Initial Access |
| 4 | Account Manipulation | T1098 | Persistence |
| 4 | Exfil to Code Repository | T1567.001 | Exfiltration |
| 4 | Discussion C2 | T1102.002 | Command & Control |
| 5 | Data Destruction | T1485 | Impact |

Full mapping: [detection/mitre_mapping.md](detection/mitre_mapping.md)

## CNAPP Detection Mapping

| Step | Component | Detection | Severity |
|------|-----------|-----------|----------|
| pull_request_target | **ASPM** | Untrusted code with secret access | Critical |
| preinstall hook | **SCA** | New lifecycle script in package update | Critical |
| IMDSv1 enabled | **CSPM** | Instance allows unauthenticated metadata | Critical |
| IMDS credential theft | **CDR** | Bulk GetSecretValue from EC2 role | Critical |
| Managed Identity theft | **CDR** | Bulk Key Vault SecretGet operations | Critical |
| GCP token theft | **CDR** | Burst AccessSecretVersion from GCE | Critical |
| Worm propagation | **SCA** | Identical payloads across packages | Critical |
| Runner registration | **ASPM** | Unauthorized "SHA1HULUD" runner | Critical |

Full mapping: [detection/cnapp_mapping.md](detection/cnapp_mapping.md)

---

## Cost Estimate

| Resource | Hourly Cost | Notes |
|----------|-------------|-------|
| AWS EC2 t3.micro | ~$0.01 | Free-tier eligible |
| AWS Secrets Manager (3) | ~$0.04 | $0.40/secret/month |
| AWS SSM Parameters | Free | Standard tier |
| Azure VM Standard_B1s | ~$0.01 | |
| Azure Key Vault | ~$0.01 | Standard tier |
| GCP e2-micro | Free | Free-tier eligible |
| GCP Secret Manager | < $0.01 | |
| Docker (Verdaccio) | Free | Local container |
| **Total** | **~$0.08/hr** | **~$1.90/day** |

---

## Project Structure

```
shai-hulud-2/
+-- README.md                        # This file
+-- setup.sh                         # One-command multi-cloud setup
+-- cleanup.sh                       # Complete multi-cloud teardown
+-- reset.sh                         # Soft reset (keep infra, re-run attack)
+-- verify.sh                        # Post-cleanup verification (~30 checks)
+-- requirements.txt                 # Python dependencies
+-- terraform/                       # Infrastructure as code (3 clouds)
|   +-- providers.tf                 # AWS + Azure + GCP provider config
|   +-- variables.tf                 # Input variables
|   +-- main.tf                      # All cloud resources
|   +-- outputs.tf                   # Values for attack scripts
|   +-- terraform.tfvars.example     # Documented example values
+-- core/                            # Lab management tooling
|   +-- main.py                      # Entry point (interactive/auto/manual)
|   +-- config.py                    # Terraform output bridge
|   +-- utils.py                     # Output formatting, logging, retry
|   +-- status.py                    # Multi-cloud lab status checker
|   +-- report.py                    # Post-attack report generator
+-- attack/                          # Attack phase scripts
|   +-- phase_0_initial_access.py    # pull_request_target exploit
|   +-- phase_1_payload_delivery.py  # npm injection + Bun dropper
|   +-- phase_2_credential_harvest.py # Multi-cloud IMDS exploitation
|   +-- phase_3_self_propagation.py  # Worm propagation + cascading
|   +-- phase_4_persistence.py       # GitHub runner + Discussion C2
|   +-- phase_5_dead_mans_switch.py  # Documentation only
|   +-- payloads/                    # Injected into npm packages
|       +-- setup_bun.js             # Bun dropper (real worm code)
|       +-- bun_environment.js       # Credential harvester
+-- detection/                       # Detection mapping
|   +-- mitre_mapping.md             # MITRE ATT&CK technique mapping
|   +-- cnapp_mapping.md             # CNAPP component detection mapping
+-- docs/                            # Educational documentation
|   +-- attack_guide.md              # Full 4,700-line manual walkthrough
|   +-- concepts.md                  # Cloud concepts explained
|   +-- attack_narrative.md          # Incident report timeline
|   +-- real_world_examples.md       # 9 real breaches, same techniques
+-- logs/                            # Runtime logs
+-- reports/                         # Generated reports
```

---

## Lessons from the Real Attack

1. **A single npm token was the master key.** One stolen automation token enabled infection of 796 packages across the entire organization.
2. **`pull_request_target` is a footgun.** The naming is misleading, and checking out PR head code with secret access is always exploitable.
3. **IMDS credential theft works on all three clouds.** AWS, Azure, and GCP all expose temporary credentials via metadata endpoints accessible from VMs.
4. **Supply chain worms create exponential propagation.** Self-replicating malware through transitive dependencies makes manual incident response impossible.
5. **GitHub Actions runners provide persistent C2.** Legitimate HTTPS traffic to github.com is indistinguishable from normal developer activity.
6. **Dead man's switches create hostage dynamics.** Mass token revocation during incident response risks triggering destructive failsafes.

---

## Educational Resources

- [docs/attack_guide.md](docs/attack_guide.md) -- Complete 4,700-line educational walkthrough with flag-by-flag explanations
- [docs/concepts.md](docs/concepts.md) -- Every cloud and supply chain concept explained from scratch
- [docs/attack_narrative.md](docs/attack_narrative.md) -- The attack told as an incident report with timeline
- [docs/real_world_examples.md](docs/real_world_examples.md) -- 9 real breaches using similar techniques
- [Datadog: Shai-Hulud 2.0 Analysis](https://securitylabs.datadoghq.com) -- Original research
- [Wiz: npm Supply Chain Worm](https://wiz.io/blog) -- Cross-cloud impact analysis
- [MITRE ATT&CK Cloud Matrix](https://attack.mitre.org/matrices/enterprise/cloud/)
