# Cloud & Supply Chain Concepts -- Shai-Hulud 2.0

Every concept in this scenario explained from scratch, assuming no prior cloud security knowledge.

## npm and the JavaScript Ecosystem

**npm** (Node Package Manager) is the world's largest software registry with over 2 million packages. When a developer runs `npm install express`, npm downloads the `express` package and all its dependencies from the registry (npmjs.com by default).

**Lifecycle hooks** are scripts defined in `package.json` that npm runs automatically during package operations. The three most important are `preinstall` (runs BEFORE installation), `install` (during), and `postinstall` (after). Shai-Hulud 2.0 used `preinstall` because it fires before security scanning tools can inspect the installed package.

**Automation tokens** are npm credentials that allow publishing packages without 2FA. They were designed for CI/CD pipelines. The Shai-Hulud 2.0 worm specifically targeted these tokens because they bypass all human verification.

**Private registries** (Verdaccio, Artifactory, GitHub Packages) are self-hosted npm registries where organizations publish internal packages. They use the same API as npmjs.com, which is why the worm works identically against all of them.

## GitHub Actions Security

**GitHub Actions** is GitHub's CI/CD platform. Workflows are YAML files in `.github/workflows/` that automate tasks like building, testing, and deploying code.

**`pull_request` vs `pull_request_target`**: The `pull_request` trigger runs workflow code from the fork/PR branch in an isolated context with NO access to repository secrets. The `pull_request_target` trigger runs in the BASE repository's context with FULL secret access. The danger: if a `pull_request_target` workflow checks out the PR's head commit (`ref: github.event.pull_request.head.sha`), it runs the attacker's code with access to all secrets.

**Repository secrets** are encrypted values stored in a repository's settings, exposed to workflows as environment variables. They use libsodium sealed boxes for encryption at rest. The `NPM_TOKEN` secret is commonly used to allow workflows to publish npm packages.

**Self-hosted runners** are machines registered to a GitHub repository that execute workflow jobs. Unlike GitHub-hosted runners (ephemeral VMs), self-hosted runners persist between jobs and can be any machine the repository owner controls. The Shai-Hulud 2.0 worm registered victims' machines as runners for persistent remote access.

**Expression injection** occurs when `${{ }}` expressions in workflow `run:` commands get interpolated directly into shell commands. For example, `run: echo ${{ github.event.discussion.body }}` allows the Discussion body to contain shell metacharacters that execute arbitrary commands.

## AWS Instance Metadata Service (IMDS)

**IMDS** is a virtual HTTP API available at `http://169.254.169.254` from within any EC2 instance. It provides instance information, network configuration, and most critically, temporary IAM role credentials.

**IMDSv1** allows simple HTTP GET requests with no authentication. Any process on the instance can call `curl http://169.254.169.254/latest/meta-data/iam/security-credentials/<role-name>` and receive working AWS credentials.

**IMDSv2** requires a two-step process: first a PUT request to obtain a session token, then that token must be included as a header in all subsequent requests. This prevents many SSRF-based credential theft attacks because most SSRF vulnerabilities cannot send PUT requests or add custom headers.

**IAM roles for EC2** provide temporary credentials (AccessKeyId, SecretAccessKey, SessionToken) that rotate automatically. These credentials start with `ASIA` (temporary) rather than `AKIA` (long-lived).

## Azure Managed Identity and IMDS

**Managed Identity** is Azure's equivalent of AWS IAM roles for EC2. A System-Assigned Managed Identity creates a service principal in Entra ID (formerly Azure AD) that is tied to the VM's lifecycle.

**Azure IMDS** uses the same IP (169.254.169.254) but requires the `Metadata: true` HTTP header on all requests. This header requirement prevents some SSRF attacks but does NOT prevent direct access from code running on the VM.

**Bearer tokens** from Azure IMDS are OAuth2 tokens scoped to a specific resource (e.g., `https://vault.azure.net` for Key Vault access). The token is a JWT that can be used directly in REST API calls.

**Azure Key Vault** stores secrets, keys, and certificates. Access is controlled via access policies (legacy) or RBAC role assignments (recommended). The worm steals the Managed Identity token and calls the Key Vault REST API directly with `curl`.

## GCP Metadata Server and Service Accounts

**GCP's metadata server** is accessible at `http://metadata.google.internal` (which resolves to 169.254.169.254). It requires the `Metadata-Flavor: Google` header on all requests.

**Service Accounts** are GCP's identity system for workloads. When a Compute Engine instance has a service account attached, any code on the instance can request an OAuth2 access token from the metadata server.

**GCP Secret Manager** stores secrets as versioned resources. Access is controlled via IAM roles like `roles/secretmanager.secretAccessor`. The worm queries the Secret Manager REST API using the stolen service account token. Note that GCP returns secret data as base64-encoded payloads, unlike AWS which returns raw strings.

## AWS Secrets Manager and SSM Parameter Store

**Secrets Manager** stores secrets (database passwords, API keys) with automatic rotation support. Access is controlled via IAM policies. The worm uses `ListSecrets` to enumerate and `GetSecretValue` to exfiltrate.

**SSM Parameter Store** stores configuration data and secrets as parameters. `SecureString` parameters are encrypted with KMS. The `--with-decryption` flag is needed to read them. The worm uses `DescribeParameters` to enumerate and `GetParameter` with decryption to exfiltrate.

## TruffleHog

**TruffleHog** is an open-source secret scanner by Truffle Security that detects 800+ credential patterns including AWS keys, GitHub tokens, database passwords, and API keys. Its key advantage: it scans git history, finding credentials that were committed and then "deleted" in subsequent commits. The real Shai-Hulud 2.0 worm downloaded TruffleHog to `~/.truffler-cache/` and weaponized it for offensive credential harvesting.

## Bun Runtime

**Bun** is an alternative JavaScript runtime (like Node.js) built on JavaScriptCore instead of V8. The worm installed Bun for detection evasion: security tools monitoring for `node` processes miss `bun` processes entirely. EDR rules matching `node ./suspicious-script.js` do not fire when the same script runs under `bun`.

## Supply Chain Worm Mechanics

A **worm** is malware that self-propagates without human interaction. Shai-Hulud 2.0 is a supply chain worm because it spreads through the software supply chain (npm packages). The propagation cycle: steal npm token -> enumerate victim's packages -> inject payload into each -> republish -> any developer who installs the infected package becomes a new victim whose token enables further propagation.

**Transitive dependencies** create exponential propagation. If Package A depends on Package B which depends on infected Package C, installing Package A triggers the payload through the dependency chain. A single `npm install` can trigger the payload dozens of times through different dependency paths.

## CNAPP Components

**CSPM** (Cloud Security Posture Management): Detects misconfigurations like IMDSv1 enabled, public Key Vault, overprivileged IAM roles.

**CDR** (Cloud Detection and Response): Detects runtime threats like unusual API call patterns, credential theft, bulk secret access.

**CWP** (Cloud Workload Protection): Monitors processes running on cloud workloads for anomalous behavior.

**CIEM** (Cloud Infrastructure Entitlement Management): Analyzes IAM permissions to identify excessive access.

**SCA** (Software Composition Analysis): Scans software dependencies for vulnerabilities and malicious code.

**ASPM** (Application Security Posture Management): Secures the software development lifecycle including CI/CD pipelines and code repositories.
