# Attack Narrative -- Shai-Hulud 2.0 Incident Report

## Timeline of a Supply Chain Worm

### Background

NovaTech is a mid-sized SaaS company building developer tools. Their engineering team maintains 12 internal npm packages published to a private Verdaccio registry. CI/CD runs on GitHub Actions. Infrastructure spans AWS (product APIs), Azure (identity and enterprise), and GCP (data analytics). A single npm automation token, created two years ago with no expiration or IP restrictions, authenticates all package publications.

### Day 0, T-5 days: Reconnaissance

The attacker identifies NovaTech's open-source repositories on GitHub. They notice a `pull_request_target` workflow in the `novatech-oss-tools-lab` repository that checks out PR head commits and passes `NPM_TOKEN` to the executed script. This is the exact vulnerability pattern documented in GitHub's "pwn request" advisory.

### Day 0, T+0:00: Initial Access

The attacker creates a GitHub account and opens a pull request against NovaTech's repository. The PR modifies `scripts/assign-reviewers.js` to read `process.env.NPM_TOKEN` and exfiltrate it. The pull_request_target workflow triggers automatically, running the attacker's code in the base repository's trusted context with full secret access.

Within 60 seconds: PR opened, workflow ran, token stolen, PR deleted.

### Day 5, T+0:00: Payload Injection

Using the stolen npm automation token, the attacker downloads `@novatech/auth-helpers` from the private registry. They inject two files: `setup_bun.js` (the dropper) and `bun_environment.js` (the credential harvester). The `preinstall` lifecycle hook is added to `package.json`. The version is bumped from 2.4.1 to 2.4.2. The infected package is republished.

### Day 5, T+0:02: First Victim

A NovaTech developer runs `npm install` in their project. Semver resolution picks up `@novatech/auth-helpers@2.4.2`. The preinstall hook fires before the package finishes installing. The dropper installs the Bun runtime (evading Node.js monitoring) and launches the credential harvester as a detached background process.

The harvester scans `.npmrc` (finds more npm tokens), `.env` (finds database passwords, API keys), `.ssh/` (finds private keys), and `.aws/credentials` (finds AWS access keys). TruffleHog is downloaded and scans git repositories, finding credentials that were "deleted" from commit history.

### Day 5, T+0:05: Cloud Credential Theft

On AWS, the harvester queries the IMDS endpoint at 169.254.169.254 (no authentication needed with IMDSv1) and steals IAM role temporary credentials. It uses these to call Secrets Manager across 17 regions and SSM Parameter Store, exfiltrating database passwords, API keys, and OAuth secrets.

On Azure, it requests a Managed Identity Bearer token from the IMDS (with the mandatory `Metadata: true` header) scoped to Key Vault. It calls the Key Vault REST API directly, listing and downloading all secrets.

On GCP, it queries the metadata server (with `Metadata-Flavor: Google` header) for the service account's OAuth2 token. It accesses Secret Manager via the REST API, retrieving all secrets with base64-decoded payloads.

### Day 5, T+0:08: Self-Propagation

The worm uses the stolen npm token to enumerate all packages owned by the victim maintainer. For each package, it downloads the tarball, injects the same payload, bumps the version, and republishes. This automated cycle infects 5 packages in under 30 seconds.

Each infected package becomes a new propagation vector. Any developer who depends on any of these packages will be infected on their next `npm install`. Transitive dependencies amplify the spread: a single meta-package installation can trigger the payload multiple times through the dependency tree.

### Day 5, T+0:10: Persistence

The worm creates a GitHub repository under the victim's account with the description "Sha1-Hulud: The Second Coming." (the campaign marker). Stolen credentials are triple-Base64 encoded and uploaded as a file.

A self-hosted GitHub Actions runner named "SHA1HULUD" is registered on the victim's machine. A Discussion-triggered workflow is deployed that enables persistent remote command execution through legitimate GitHub HTTPS traffic.

### Day 5, T+0:12: Dead Man's Switch Armed

The worm checks if all authentication paths are available. If they are, it continues normal operation. If all tokens are revoked simultaneously, the destructive failsafe triggers: `shred -uvz -n 1` on all writable files in the user's home directory, making forensic recovery impossible.

### Impact Assessment

In the real Shai-Hulud 2.0 attack (November 24, 2025):

- 796 npm packages compromised across 1,092 versions
- 25,000+ GitHub exfiltration repositories created
- Approximately 14,000 secrets exposed across 487 organizations
- Companies affected: Zapier, PostHog, Postman, AsyncAPI, ENS Domains, Trigger.dev
- npm revoked all classic automation tokens on December 9, 2025
- CISA, Microsoft, AWS, and GitHub all issued emergency advisories

### Lessons

1. A single npm automation token was the master key to the entire supply chain
2. `pull_request_target` with PR head checkout is always exploitable
3. IMDS credential theft works identically across all three major clouds
4. Self-propagation through npm makes manual incident response impossible
5. The dead man's switch created a hostage dynamic that complicated coordinated response
6. Cross-cloud attacks require cross-cloud detection and response
