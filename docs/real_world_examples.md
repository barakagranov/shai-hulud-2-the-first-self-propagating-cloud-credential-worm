# Real-World Examples -- Shai-Hulud 2.0

Breaches and research using the same techniques demonstrated in this lab.

## 1. Shai-Hulud 2.0 (November 2025)

**This is the attack this lab recreates.** First self-propagating supply chain worm targeting all three major cloud providers simultaneously. Compromised 796 npm packages, created 25,000+ GitHub repositories, and exposed approximately 14,000 secrets across 487 organizations including Zapier, PostHog, Postman, and AsyncAPI.

- **Researchers:** Datadog Security Labs (Christophe Tafani-Dereeper), Wiz Research, Unit 42, Trend Micro, Check Point, Netskope
- **Techniques used:** T1195.002, T1552.005, T1528, T1555.006, T1098, T1485
- **Source:** securitylabs.datadoghq.com, wiz.io/blog

## 2. Shai-Hulud v1 (September 2025)

The predecessor worm. Phished npm maintainer Josh Junon via a spoofed npmjs.help domain, compromising the `chalk` and `debug` packages with 2.6 billion combined weekly downloads. Used `postinstall` instead of `preinstall`, which gave security tools a brief window to detect it.

- **Techniques used:** T1195.002, T1552.001
- **Key difference from v2:** Used postinstall (v2 switched to preinstall to evade scanners)

## 3. PostHog Compromise (November 2025)

Patient zero for Shai-Hulud 2.0. GitHub user `brwjbowkevj` exploited a `pull_request_target` workflow in PostHog's `assign-reviewers` workflow. The PR opened at 17:40 UTC, the workflow ran, the npm token was exfiltrated, and the PR was deleted within 60 seconds.

- **Techniques used:** T1195.002, T1552.008
- **Source:** PostHog published a detailed post-mortem

## 4. Capital One (2019)

SSRF exploit used IMDSv1 to steal IAM role credentials from an EC2 instance behind a misconfigured WAF. The attacker accessed over 100 million customer records in S3. This breach was the catalyst for AWS creating IMDSv2.

- **Techniques used:** T1552.005, T1530
- **Relevance to this lab:** Same IMDS credential theft technique demonstrated in Phase 2

## 5. SCARLETEEL (2023)

Sysdig TRT documented an attack where adversaries accessed IMDS from compromised Kubernetes containers, stole IAM role credentials, and used them to access S3 buckets containing Terraform state files (which contained additional credentials).

- **Researchers:** Sysdig Threat Research Team
- **Techniques used:** T1552.005, T1530, T1580
- **Source:** sysdig.com/blog

## 6. event-stream (2018)

Social engineering gave an attacker publish access to the `event-stream` npm package (2 million downloads/week). Malicious code injected via a dependency targeted a specific Bitcoin wallet application (Copay). The attack was discovered when the malicious dependency was analyzed by a curious developer.

- **Techniques used:** T1195.002
- **Relevance:** First high-profile npm supply chain attack; demonstrated the risk of npm lifecycle hooks

## 7. ua-parser-js (2021)

Maintainer's npm account compromised via credential stuffing. A cryptominer was injected into a package with 8 million weekly downloads. The `preinstall` hook downloaded and executed platform-specific malware binaries.

- **Techniques used:** T1195.002, T1546
- **Relevance:** Same preinstall hook technique used by Shai-Hulud 2.0

## 8. Codecov (2021)

CI/CD credential theft via a compromised bash uploader script. The modified script exfiltrated environment variables (including tokens) during CI builds. Affected thousands of repositories across GitHub, GitLab, and Bitbucket.

- **Techniques used:** T1552.008, T1567
- **Relevance:** CI/CD environment variable theft, similar to the pull_request_target exploit

## 9. SolarWinds (2020)

Build pipeline compromise injected a backdoor (SUNBURST) into signed software updates distributed to 18,000 organizations. The attacker had access to the build system for months before the malicious update was pushed.

- **Techniques used:** T1195.002
- **Relevance:** Supply chain compromise at build time; CodeBreach (January 2026) showed that Shai-Hulud 2.0's supply chain access could have been even more impactful than SolarWinds

## Common Patterns Across All Breaches

1. **Identity is always the pivot point**: Every attack chain involves stealing or abusing credentials
2. **IMDS is a persistent target**: IMDSv1 credential theft appears in attacks from 2019 through 2025
3. **npm lifecycle hooks are weaponizable**: preinstall/postinstall hooks execute arbitrary code with the installer's privileges
4. **CI/CD secrets are high-value targets**: Tokens stored in GitHub Actions, Jenkins, and other CI systems enable supply chain attacks
5. **Cross-service trust creates blast radius**: Compromising one service routinely gives access to three or more others
