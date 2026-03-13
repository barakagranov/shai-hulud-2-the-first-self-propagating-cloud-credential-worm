# CNAPP Detection Mapping -- Shai-Hulud 2.0

## Supply Chain Worm Simulation (Multi-Cloud)

| Step | CNAPP Component | Detection Description | Severity | What SOC Would See | Remediation |
|------|-----------------|----------------------|----------|-------------------|-------------|
| 1-5 | **ASPM** | `pull_request_target` checks out PR head code with secret access | Critical | Workflow executed untrusted code with access to NPM_TOKEN | Remove `ref:` from checkout; use `pull_request` trigger instead |
| 6-8 | **SCA** | Package version updated with new `preinstall` lifecycle script | Critical | @novatech/auth-helpers 2.4.2 adds preinstall hook not in 2.4.1 | Use `--ignore-scripts`; enable npm provenance |
| 6 | **CWP** | `npm install` triggers `curl` to download external binary (Bun) | High | Unexpected binary download during package installation | Sandbox npm installs in containers |
| 9 | **CWP** | Background process reading credential files (.npmrc, .env, .ssh/) | Critical | Process accessing multiple credential paths in rapid succession | EDR monitoring for credential file access patterns |
| 10 | **CWP** | TruffleHog binary downloaded and executed on workload | High | Known security tool used in offensive context | Block unauthorized binary downloads |
| 11 | **CSPM** | EC2 instance with IMDSv1 enabled | Critical | Instance allows unauthenticated metadata access | Set `http_tokens = "required"` (IMDSv2) |
| 11 | **CDR** | Burst of GetSecretValue calls across multiple secrets | Critical | Bulk secret retrieval from EC2 role | Monitor for unusual Secrets Manager access patterns |
| 11 | **CIEM** | IAM role has `Resource: *` on `secretsmanager:GetSecretValue` | High | Overprivileged instance role | Scope to specific secret ARNs |
| 12 | **CDR** | Managed Identity token acquired by unusual process | High | IMDS token request outside normal application pattern | Use User-Assigned Identity with minimal roles |
| 12 | **CDR** | Bulk Key Vault SecretGet operations | Critical | Mass secret retrieval from Managed Identity | Monitor Key Vault audit logs |
| 12 | **CSPM** | Key Vault allows public network access | Medium | Missing private endpoint | Enable private endpoints; disable public access |
| 13 | **CDR** | GCP metadata server token request from unexpected code path | High | SA token theft pattern from compute instance | Enable VPC Service Controls |
| 13 | **CDR** | Bulk Secret Manager AccessSecretVersion calls | Critical | Mass secret access from Compute VM | Grant secretAccessor at secret level, not project |
| 13 | **CIEM** | Service account has project-level secretAccessor role | High | Overprivileged SA binding | Use resource-level IAM bindings |
| 14 | **SCA + ASPM** | Multiple packages updated simultaneously with identical payloads | Critical | Coordinated supply chain modification | Rate-limit publications; require OIDC publishing |
| 15 | **SCA** | Transitive dependency triggers preinstall hooks | High | Cascading lifecycle script execution | Use `npm ci` with locked dependencies |
| 16 | **CDR** | Repository created with known campaign marker description | High | Shai-Hulud IOC match | Monitor for "Sha1-Hulud" in repo descriptions |
| 17 | **ASPM** | Self-hosted runner registered from unrecognized host | Critical | Unauthorized runner "SHA1HULUD" registered | Restrict runner registration to org-managed machines |
| 18 | **ASPM** | Discussion-triggered workflow on self-hosted runner | Critical | Potential expression injection C2 | Audit workflows for `${{ }}` in `run:` commands |
| 19 | **CWP** | shred/cipher commands targeting user home directory | Critical | Destructive wiper activity | EDR detection of bulk file deletion |

## Detection by CNAPP Component

| Component | Detections | Key Capability |
|-----------|-----------|----------------|
| **CSPM** | 3 | Misconfiguration detection (IMDSv1, public KV, overprivileged IAM) |
| **CDR** | 7 | Runtime threat detection (API bursts, token theft, campaign markers) |
| **CWP** | 4 | Workload protection (process monitoring, binary downloads, credential access) |
| **CIEM** | 3 | Identity entitlement management (overprivileged roles/SAs) |
| **SCA** | 3 | Software composition analysis (lifecycle hooks, payload detection) |
| **ASPM** | 4 | Application security posture (CI/CD security, runner management) |
| **DSPM** | 0 | (Secrets are the target, not data classification in this scenario) |

## Cross-Cloud Detection Correlation

A unified CNAPP platform would correlate these signals across all three clouds:

1. **Same credential harvesting pattern** on AWS, Azure, and GCP within minutes
2. **Same payload files** (setup_bun.js, bun_environment.js) across multiple npm packages
3. **Same campaign marker** in GitHub repository descriptions
4. **Same runner name** (SHA1HULUD) registered across victim accounts

This cross-signal correlation is what separates a CNAPP from individual cloud-native security tools.
