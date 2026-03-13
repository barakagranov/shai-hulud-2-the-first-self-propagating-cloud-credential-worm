"""
status.py -- Lab environment status checker for Shai-Hulud 2.0.

Shows the current state of the lab across all three clouds, Docker,
GitHub, and npm. Useful for debugging and knowing what cleanup is needed.
"""
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from utils import (
    console,
    get_completed_phases,
    print_error,
    print_info,
    print_success,
    print_warning,
)

TERRAFORM_DIR = str(Path(__file__).resolve().parent.parent / "terraform")


def _check_mark(ok: bool) -> str:
    return "[bright_green]OK[/bright_green]" if ok else "[bright_red]--[/bright_red]"


def check_infrastructure() -> Dict[str, Any]:
    """Check if Terraform infrastructure is deployed."""
    result = {"deployed": False, "resource_count": 0, "deploy_time": None}

    tfstate_path = Path(TERRAFORM_DIR) / "terraform.tfstate"
    if not tfstate_path.exists():
        return result

    try:
        with open(tfstate_path) as f:
            state = json.load(f)
        resources = state.get("resources", [])
        result["deployed"] = len(resources) > 0
        result["resource_count"] = len(resources)

        mtime = os.path.getmtime(str(tfstate_path))
        result["deploy_time"] = datetime.fromtimestamp(mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        result["hours_running"] = round((time.time() - mtime) / 3600, 1)
        # 3 VMs across 3 clouds: ~$0.08/hr combined
        result["estimated_cost"] = f"${result['hours_running'] * 0.08:.2f}"
    except (json.JSONDecodeError, IOError):
        pass

    return result


def check_cloud_credentials() -> Dict[str, Any]:
    """Check if cloud CLI credentials are configured."""
    result = {"aws": False, "azure": False, "gcp": False}

    # AWS
    try:
        r = subprocess.run(
            ["aws", "sts", "get-caller-identity"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            result["aws"] = True
            result["aws_account"] = data.get("Account", "")
            result["aws_arn"] = data.get("Arn", "")
    except Exception:
        pass

    # Azure
    try:
        r = subprocess.run(
            ["az", "account", "show", "--query", "id", "--output", "tsv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            result["azure"] = True
            result["azure_subscription"] = r.stdout.strip()
    except Exception:
        pass

    # GCP
    try:
        r = subprocess.run(
            ["gcloud", "config", "get", "project"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            result["gcp"] = True
            result["gcp_project"] = r.stdout.strip()
    except Exception:
        pass

    return result


def check_docker() -> Dict[str, Any]:
    """Check if Docker is running and Verdaccio is available."""
    result = {"docker_running": False, "verdaccio_running": False}

    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        result["docker_running"] = r.returncode == 0
    except Exception:
        pass

    if result["docker_running"]:
        try:
            r = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", "verdaccio"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            result["verdaccio_running"] = r.stdout.strip() == "true"
        except Exception:
            pass

    return result


def check_github() -> Dict[str, Any]:
    """Check if GitHub credentials are set."""
    result = {
        "pat_set": bool(os.environ.get("GITHUB_PAT")),
        "username_set": bool(os.environ.get("GITHUB_USERNAME")),
    }
    return result


def check_python_env() -> Dict[str, Any]:
    """Check Python environment health."""
    import sys

    result = {
        "python_version": sys.version.split()[0],
        "in_venv": sys.prefix != sys.base_prefix,
    }

    for pkg in ["boto3", "rich", "paramiko", "requests"]:
        try:
            mod = __import__(pkg)
            result[f"{pkg}_version"] = getattr(mod, "__version__", "installed")
        except ImportError:
            result[f"{pkg}_version"] = "MISSING"

    return result


def run_status() -> Dict[str, Any]:
    """Run all status checks and display results."""
    from rich.table import Table
    from rich import box

    console.print()
    console.print(
        "[bold bright_white]Shai-Hulud 2.0 -- Lab Status[/bold bright_white]",
        style="underline",
    )
    console.print()

    all_status = {}

    # --- Cloud Credentials ---
    creds = check_cloud_credentials()
    all_status["cloud_credentials"] = creds

    # --- Infrastructure ---
    infra = check_infrastructure()
    all_status["infrastructure"] = infra

    # --- Docker / Verdaccio ---
    docker = check_docker()
    all_status["docker"] = docker

    # --- GitHub ---
    github = check_github()
    all_status["github"] = github

    # --- Python Environment ---
    pyenv = check_python_env()
    all_status["python_env"] = pyenv

    # --- Attack Progress ---
    progress = get_completed_phases()
    all_status["attack_progress"] = progress

    # --- Display ---
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Check", style="bright_cyan", width=28)
    table.add_column("Status", style="white")

    # Cloud creds
    table.add_row(
        "AWS Credentials",
        f"{_check_mark(creds['aws'])}  {creds.get('aws_arn', 'Not configured')}",
    )
    table.add_row(
        "Azure Credentials",
        f"{_check_mark(creds['azure'])}  {creds.get('azure_subscription', 'Not configured')[:20]}",
    )
    table.add_row(
        "GCP Credentials",
        f"{_check_mark(creds['gcp'])}  {creds.get('gcp_project', 'Not configured')}",
    )

    # Infrastructure
    table.add_row(
        "Infrastructure",
        f"{_check_mark(infra['deployed'])}  "
        + (
            f"{infra['resource_count']} resources"
            if infra["deployed"]
            else "Not deployed"
        ),
    )
    if infra.get("hours_running"):
        table.add_row(
            "Running Since",
            f"{infra['deploy_time']}  ({infra['hours_running']}h, ~{infra['estimated_cost']})",
        )

    # Docker / Verdaccio
    table.add_row(
        "Docker",
        f"{_check_mark(docker['docker_running'])}  "
        + ("Running" if docker["docker_running"] else "Not running"),
    )
    table.add_row(
        "Verdaccio Registry",
        f"{_check_mark(docker['verdaccio_running'])}  "
        + (
            "Running on :4873"
            if docker["verdaccio_running"]
            else "Not running"
        ),
    )

    # GitHub
    table.add_row(
        "GitHub PAT",
        f"{_check_mark(github['pat_set'])}  "
        + ("Set" if github["pat_set"] else "GITHUB_PAT not exported"),
    )
    table.add_row(
        "GitHub Username",
        f"{_check_mark(github['username_set'])}  "
        + (
            os.environ.get("GITHUB_USERNAME", "")
            if github["username_set"]
            else "GITHUB_USERNAME not exported"
        ),
    )

    # Attack Progress
    phase_names = {
        0: "Initial Access",
        1: "Payload Delivery",
        2: "Credential Harvest",
        3: "Self-Propagation",
        4: "Persistence",
        5: "Dead Man's Switch",
    }
    if progress:
        phase_str = "  ".join(
            f"[bright_green]P{i}[/bright_green]"
            if progress.get(f"phase{i}")
            else f"[dim]P{i}[/dim]"
            for i in range(6)
        )
        table.add_row("Attack Progress", phase_str)

    # Python
    venv_str = "Active" if pyenv["in_venv"] else "[bright_red]Not in venv[/bright_red]"
    table.add_row(
        "Python Environment",
        f"{_check_mark(pyenv['in_venv'])}  Python {pyenv['python_version']}  ({venv_str})",
    )

    console.print(table)
    console.print()

    return all_status
