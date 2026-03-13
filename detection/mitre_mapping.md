# MITRE ATT&CK Mapping -- Shai-Hulud 2.0

## Supply Chain Worm Simulation (Multi-Cloud)

| Phase | Step | Technique ID | Technique Name | Tactic | Description |
|-------|------|-------------|----------------|--------|-------------|
| 0 | 1-5 | T1195.002 | Supply Chain: Software Supply Chain | Initial Access | pull_request_target exploit to steal npm token |
| 0 | 2 | T1552.008 | Unsecured Credentials: CI/CD Variables | Credential Access | NPM_TOKEN exposed to untrusted workflow code |
| 1 | 6-8 | T1195.002 | Supply Chain: Software Supply Chain | Initial Access | Inject malicious preinstall hook into package |
| 1 | 6 | T1036.004 | Masquerading: Masquerade as Legitimate Application | Defense Evasion | Bun runtime installed as "dev environment setup" |
| 1 | 8 | T1546 | Event Triggered Execution | Persistence | preinstall hook runs on every npm install |
| 2 | 9 | T1552.001 | Unsecured Credentials: Files | Credential Access | Harvest .npmrc, .env, SSH keys from filesystem |
| 2 | 9 | T1082 | System Information Discovery | Discovery | Fingerprint host OS, user, platform |
| 2 | 10 | T1119 | Automated Collection | Collection | TruffleHog scans git history for 800+ credential types |
| 2 | 11 | T1552.005 | Cloud Instance Metadata API | Credential Access | Steal IAM role credentials via AWS IMDS |
| 2 | 11 | T1555.006 | Cloud Secrets Management Stores | Credential Access | Exfiltrate Secrets Manager + SSM Parameter Store |
| 2 | 11 | T1580 | Cloud Infrastructure Discovery | Discovery | Enumerate secrets across AWS regions |
| 2 | 12 | T1528 | Steal Application Access Token | Credential Access | Steal Azure Managed Identity Bearer token via IMDS |
| 2 | 12 | T1555.006 | Cloud Secrets Management Stores | Credential Access | Exfiltrate Key Vault secrets via REST API |
| 2 | 13 | T1552.005 | Cloud Instance Metadata API | Credential Access | Steal GCP SA token from metadata server |
| 2 | 13 | T1555.006 | Cloud Secrets Management Stores | Credential Access | Exfiltrate Secret Manager via REST API |
| 3 | 14 | T1195.002 | Supply Chain: Software Supply Chain | Initial Access | Worm self-propagation across npm packages |
| 3 | 14 | T1127 | Trusted Developer Utilities Proxy Execution | Defense Evasion | Abuse npm publish for automated propagation |
| 3 | 15 | T1546 | Event Triggered Execution | Execution | Cascading preinstall via transitive dependencies |
| 4 | 16 | T1567.001 | Exfiltration to Code Repository | Exfiltration | Upload triple-encoded data to GitHub repo |
| 4 | 16 | T1001 | Data Obfuscation | Command and Control | Triple-Base64 encoding to evade scanning |
| 4 | 17 | T1098 | Account Manipulation | Persistence | Register self-hosted runner on victim's machine |
| 4 | 18 | T1059.009 | Cloud API: Command Execution | Execution | C2 via GitHub Discussions expression injection |
| 4 | 18 | T1102.002 | Web Service: Bidirectional Communication | C2 | GitHub Discussions as bidirectional C2 channel |
| 5 | 19 | T1485 | Data Destruction | Impact | Dead man's switch (documented, not executed) |
| 5 | 19 | T1490 | Inhibit System Recovery | Impact | shred prevents forensic file recovery |

## Technique Count by Tactic

| Tactic | Count | Techniques |
|--------|-------|------------|
| Initial Access | 3 | T1195.002 (x3) |
| Credential Access | 7 | T1552.001, T1552.005 (x2), T1552.008, T1528, T1555.006 (x3) |
| Defense Evasion | 2 | T1036.004, T1127 |
| Discovery | 2 | T1082, T1580 |
| Collection | 1 | T1119 |
| Execution | 2 | T1546, T1059.009 |
| Persistence | 3 | T1546, T1098, T1195.002 |
| Exfiltration | 1 | T1567.001 |
| Command and Control | 2 | T1001, T1102.002 |
| Impact | 2 | T1485, T1490 |

## References

- [MITRE ATT&CK Cloud Matrix](https://attack.mitre.org/matrices/enterprise/cloud/)
- [MITRE ATT&CK Containers Matrix](https://attack.mitre.org/matrices/enterprise/containers/)
- [ATT&CK v14 Release Notes](https://attack.mitre.org/resources/updates/) (includes T1552.008)
