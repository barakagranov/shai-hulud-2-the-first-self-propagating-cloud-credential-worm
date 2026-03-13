"""
config.py -- Configuration bridge between Terraform outputs and attack scripts.

Reads Terraform outputs to get infrastructure details (IPs, names, keys)
across AWS, Azure, and GCP. Manages SSH connections and cloud SDK sessions.

Unlike the reference lab which uses boto3 sessions, this scenario operates
primarily through SSH into VMs and direct HTTP calls to metadata endpoints.
The config provides connection parameters rather than SDK sessions.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from utils import print_error, print_info, print_success, print_warning


class AttackConfig:
    """
    Manages configuration for the multi-cloud Shai-Hulud 2.0 attack.

    Reads Terraform outputs to discover infrastructure details and provides
    accessor properties for each value the attack scripts need.
    """

    def __init__(self, terraform_dir: Optional[str] = None) -> None:
        """
        Initialize the config by reading Terraform outputs.

        Args:
            terraform_dir: Path to the terraform/ directory. Defaults to
                           ../terraform relative to this script.
        """
        if terraform_dir is None:
            terraform_dir = str(
                Path(__file__).resolve().parent.parent / "terraform"
            )
        self.terraform_dir = terraform_dir
        self._tf_outputs: Dict[str, Any] = {}
        self._ssh_key_path: Optional[str] = None
        self._github_pat: Optional[str] = None
        self._github_username: Optional[str] = None
        self._npm_token: Optional[str] = None
        self._load_terraform_outputs()

    # =========================================================================
    # Terraform Output Loading
    # =========================================================================

    def _load_terraform_outputs(self) -> None:
        """Read Terraform outputs via subprocess and parse the JSON result."""
        try:
            result = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                print_error(
                    f"Terraform output failed: {result.stderr.strip()}"
                )
                print_info(
                    "Make sure you have run 'terraform apply' in the "
                    "terraform/ directory first."
                )
                raise RuntimeError("Terraform outputs not available")

            raw = json.loads(result.stdout)
            # terraform output -json wraps each value in {"value":..., "type":...}
            self._tf_outputs = {k: v.get("value") for k, v in raw.items()}
        except FileNotFoundError:
            raise RuntimeError(
                "Terraform CLI not found. Install Terraform >= 1.11.0."
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Failed to parse Terraform output: {exc}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Terraform output timed out after 30 seconds.")

    # =========================================================================
    # AWS Properties
    # =========================================================================

    @property
    def aws_region(self) -> str:
        return self._tf_outputs.get("aws_region", "us-east-1")

    @property
    def aws_instance_id(self) -> str:
        return self._tf_outputs.get("aws_instance_id", "")

    @property
    def aws_instance_public_ip(self) -> str:
        return self._tf_outputs.get("aws_instance_public_ip", "")

    @property
    def aws_iam_role_arn(self) -> str:
        return self._tf_outputs.get("aws_iam_role_arn", "")

    @property
    def aws_secrets_prefix(self) -> str:
        return self._tf_outputs.get("aws_secrets_prefix", "")

    @property
    def aws_ssm_prefix(self) -> str:
        return self._tf_outputs.get("aws_ssm_prefix", "")

    # =========================================================================
    # Azure Properties
    # =========================================================================

    @property
    def azure_vm_public_ip(self) -> str:
        return self._tf_outputs.get("azure_vm_public_ip", "")

    @property
    def azure_vm_password(self) -> str:
        return self._tf_outputs.get("azure_vm_password", "P@ssw0rd!NovaTech2025Lab")

    @property
    def azure_resource_group(self) -> str:
        return self._tf_outputs.get("azure_resource_group", "")

    @property
    def azure_keyvault_name(self) -> str:
        return self._tf_outputs.get("azure_keyvault_name", "")

    @property
    def azure_keyvault_uri(self) -> str:
        return self._tf_outputs.get("azure_keyvault_uri", "")

    # =========================================================================
    # GCP Properties
    # =========================================================================

    @property
    def gcp_instance_name(self) -> str:
        return self._tf_outputs.get("gcp_instance_name", "")

    @property
    def gcp_instance_zone(self) -> str:
        return self._tf_outputs.get("gcp_instance_zone", "")

    @property
    def gcp_service_account_email(self) -> str:
        return self._tf_outputs.get("gcp_service_account_email", "")

    @property
    def gcp_project_id(self) -> str:
        return self._tf_outputs.get("gcp_project_id", "")

    @property
    def gcp_secret_prefix(self) -> str:
        return self._tf_outputs.get("gcp_secret_prefix", "")

    @property
    def gcp_secret_suffix(self) -> str:
        return self._tf_outputs.get("gcp_secret_suffix", "")

    # =========================================================================
    # Common Properties
    # =========================================================================

    @property
    def resource_prefix(self) -> str:
        return self._tf_outputs.get("resource_prefix", "")

    # =========================================================================
    # SSH Key Management
    # =========================================================================

    @property
    def ssh_key_path(self) -> str:
        """
        Path to the SSH private key for AWS EC2 access.
        Writes the key from Terraform outputs to a file on first access.
        """
        if self._ssh_key_path is not None:
            return self._ssh_key_path

        key_path = Path(self.terraform_dir).resolve() / "lab-key.pem"
        if not key_path.exists():
            # Write the key from terraform output
            try:
                result = subprocess.run(
                    ["terraform", "output", "-raw", "aws_ssh_private_key"],
                    cwd=self.terraform_dir,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0 and result.stdout.strip():
                    key_path.write_text(result.stdout)
                    os.chmod(str(key_path), 0o600)
                    print_info(f"SSH key written to {key_path}")
                else:
                    print_warning("Could not extract SSH key from Terraform outputs")
            except Exception as exc:
                print_warning(f"SSH key extraction failed: {exc}")

        self._ssh_key_path = str(key_path)
        return self._ssh_key_path

    # =========================================================================
    # GitHub and npm Token Management
    # =========================================================================

    @property
    def github_pat(self) -> str:
        """GitHub Personal Access Token from environment."""
        if self._github_pat is None:
            self._github_pat = os.environ.get("GITHUB_PAT", "")
        return self._github_pat

    @property
    def github_username(self) -> str:
        """GitHub username from environment."""
        if self._github_username is None:
            self._github_username = os.environ.get("GITHUB_USERNAME", "")
        return self._github_username

    @property
    def npm_token(self) -> str:
        """Victim npm token from environment."""
        if self._npm_token is None:
            self._npm_token = os.environ.get("VICTIM_NPM_TOKEN", "")
        return self._npm_token

    def require_github_credentials(self) -> None:
        """Raise RuntimeError if GitHub credentials are not set."""
        if not self.github_pat or not self.github_username:
            raise RuntimeError(
                "GitHub credentials not set. Export GITHUB_PAT and "
                "GITHUB_USERNAME environment variables first."
            )

    def require_npm_token(self) -> None:
        """Raise RuntimeError if npm token is not set."""
        if not self.npm_token:
            raise RuntimeError(
                "npm token not set. Export VICTIM_NPM_TOKEN environment "
                "variable first (see attack guide Step 2)."
            )

    def require_verdaccio(self) -> None:
        """Raise RuntimeError if Verdaccio is not running."""
        import requests

        try:
            resp = requests.get(
                "http://localhost:4873/-/ping", timeout=5
            )
            if resp.status_code != 200:
                raise RuntimeError("Verdaccio returned non-200")
        except Exception:
            raise RuntimeError(
                "Verdaccio is not running on localhost:4873. "
                "Start it with: docker run -d --name verdaccio -p 4873:4873 "
                "verdaccio/verdaccio:latest"
            )

    # =========================================================================
    # Summary
    # =========================================================================

    def print_config_summary(self) -> None:
        """Print a summary of the current configuration."""
        from rich.table import Table
        from rich import box

        table = Table(
            title="Attack Configuration",
            box=box.ROUNDED,
            show_lines=False,
        )
        table.add_column("Parameter", style="bright_cyan")
        table.add_column("Value", style="white")

        # AWS
        table.add_row("AWS EC2 IP", self.aws_instance_public_ip or "N/A")
        table.add_row("AWS IAM Role", self.aws_iam_role_arn or "N/A")
        table.add_row("AWS Region", self.aws_region)

        # Azure
        table.add_row("Azure VM IP", self.azure_vm_public_ip or "N/A")
        table.add_row("Azure Key Vault", self.azure_keyvault_name or "N/A")

        # GCP
        table.add_row("GCP Instance", self.gcp_instance_name or "N/A")
        table.add_row("GCP Project", self.gcp_project_id or "N/A")

        # External
        table.add_row(
            "GitHub PAT",
            f"{self.github_pat[:8]}..." if self.github_pat else "Not set",
        )
        table.add_row(
            "npm Token",
            f"{self.npm_token[:8]}..." if self.npm_token else "Not set",
        )
        table.add_row(
            "Verdaccio",
            "Check with require_verdaccio()",
        )

        from utils import console

        console.print(table)
