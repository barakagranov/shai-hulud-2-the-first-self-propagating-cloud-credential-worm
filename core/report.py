"""
report.py -- Post-attack Markdown report generator for Shai-Hulud 2.0.

Generates a structured report from attack results and/or log files,
including MITRE ATT&CK mappings, CNAPP detections, and timelines.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils import print_error, print_info, print_success


def generate_report(
    results: Dict[str, Any],
    config: Any = None,
    log_file: Optional[str] = None,
) -> str:
    """
    Generate a Markdown report from attack results.

    Args:
        results: Combined results dict from all phases.
        config: AttackConfig instance for infrastructure details.
        log_file: Path to the structured log file.

    Returns:
        Path to the generated report file.
    """
    report_dir = str(Path(__file__).resolve().parent.parent / "reports")
    os.makedirs(report_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = os.path.join(report_dir, f"attack-report-{timestamp}.md")

    lines = []
    lines.append("# Shai-Hulud 2.0 -- Attack Simulation Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Scenario:** Supply Chain Worm Simulation (Multi-Cloud)")
    lines.append("")

    # Infrastructure summary
    if config:
        lines.append("## Infrastructure")
        lines.append("")
        lines.append(f"- **AWS EC2:** {config.aws_instance_public_ip}")
        lines.append(f"- **Azure VM:** {config.azure_vm_public_ip}")
        lines.append(f"- **GCP GCE:** {config.gcp_instance_name}")
        lines.append(f"- **Verdaccio:** localhost:4873")
        lines.append("")

    # Phase results
    lines.append("## Phase Results")
    lines.append("")

    phase_names = {
        0: "Initial Access (pull_request_target)",
        1: "Payload Delivery (npm injection + Bun)",
        2: "Credential Harvesting (multi-cloud IMDS)",
        3: "Self-Propagation (worm + cascading deps)",
        4: "Persistence (GitHub runner + C2)",
        5: "Dead Man's Switch (documented only)",
    }

    for i in range(6):
        key = f"phase{i}"
        name = phase_names.get(i, f"Phase {i}")
        status = "COMPLETE" if key in results else "SKIPPED"
        lines.append(f"### Phase {i}: {name}")
        lines.append(f"**Status:** {status}")
        lines.append("")

        if key in results:
            phase_data = results[key]
            if isinstance(phase_data, dict):
                for k, v in phase_data.items():
                    if isinstance(v, (str, int, float, bool)):
                        lines.append(f"- **{k}:** {v}")
                    elif isinstance(v, list):
                        lines.append(f"- **{k}:** {len(v)} items")
                    elif isinstance(v, dict):
                        lines.append(f"- **{k}:** {len(v)} entries")
            lines.append("")

    # MITRE ATT&CK summary
    lines.append("## MITRE ATT&CK Techniques Used")
    lines.append("")
    lines.append("| Phase | Technique ID | Technique Name | Tactic |")
    lines.append("|-------|-------------|----------------|--------|")
    mitre_rows = [
        ("0", "T1195.002", "Supply Chain Compromise", "Initial Access"),
        ("0", "T1552.008", "Unsecured Credentials: CI/CD", "Credential Access"),
        ("1", "T1195.002", "Supply Chain Compromise", "Initial Access"),
        ("1", "T1036.004", "Masquerading", "Defense Evasion"),
        ("2", "T1552.001", "Credentials in Files", "Credential Access"),
        ("2", "T1552.005", "Cloud Instance Metadata API", "Credential Access"),
        ("2", "T1528", "Steal Application Access Token", "Credential Access"),
        ("2", "T1555.006", "Cloud Secrets Mgmt Stores", "Credential Access"),
        ("3", "T1195.002", "Supply Chain Compromise", "Initial Access"),
        ("4", "T1098", "Account Manipulation", "Persistence"),
        ("4", "T1059.009", "Cloud API Execution", "Execution"),
        ("4", "T1567.001", "Exfil to Code Repository", "Exfiltration"),
        ("5", "T1485", "Data Destruction", "Impact"),
    ]
    for row in mitre_rows:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
    lines.append("")

    # Write report
    try:
        with open(report_path, "w") as f:
            f.write("\n".join(lines))
        return report_path
    except Exception as exc:
        print_error(f"Failed to write report: {exc}")
        return ""


def generate_report_from_log(log_path: str) -> str:
    """Generate a report from a structured log file."""
    try:
        events = []
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # Build results dict from log events
        results = {}
        for event in events:
            phase = event.get("phase")
            if phase is not None:
                key = f"phase{phase}"
                if key not in results:
                    results[key] = {}
                if event.get("level") == "success":
                    results[key][event.get("step", "info")] = event["message"]

        return generate_report(results)
    except Exception as exc:
        print_error(f"Failed to parse log: {exc}")
        return ""
