"""
utils.py -- Shared utilities for the Shai-Hulud 2.0 attack simulation.

Provides colored terminal output, structured JSON logging, retry logic,
table formatting, and progress tracking used across all phases.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

# =============================================================================
# Structured Logging
# =============================================================================
# When enabled, every significant event is written to a JSON-lines file.
# Each line is a self-contained JSON object with:
#   timestamp, level, phase, step, message, data (optional)

_log_file = None
_log_start_time = None

_LOGS_DIR = str(Path(__file__).resolve().parent.parent / "logs")
_PROGRESS_FILE = os.path.join(_LOGS_DIR, ".attack-progress.json")
_SESSION_FILE = os.path.join(_LOGS_DIR, ".session-data.json")


# =============================================================================
# Step-Level Progress Tracking
# =============================================================================
# Each step is identified by a string like "0.1", "2.3", "4.1".
# Progress is stored as {"0.1": true, "0.2": true, ...}


def mark_step_complete(step_id: str) -> None:
    """Record that a step has been completed."""
    progress = get_completed_steps()
    progress[step_id] = True
    try:
        os.makedirs(_LOGS_DIR, exist_ok=True)
        with open(_PROGRESS_FILE, "w") as f:
            json.dump(progress, f)
    except Exception:
        pass  # Never let progress tracking break the attack


def is_step_complete(step_id: str) -> bool:
    """Check if a specific step has been completed."""
    return get_completed_steps().get(step_id, False)


def get_completed_steps() -> dict:
    """Read which steps have been completed."""
    if os.path.exists(_PROGRESS_FILE):
        try:
            with open(_PROGRESS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def clear_progress() -> None:
    """Clear all progress (for new runs)."""
    for f in (_PROGRESS_FILE, _SESSION_FILE):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


def is_phase_complete(phase_num: int, step_ids: List[str]) -> bool:
    """Check if all steps in a phase are complete."""
    completed = get_completed_steps()
    return all(completed.get(sid, False) for sid in step_ids)


# =============================================================================
# Session Data (persists state between steps across restarts)
# =============================================================================
# Used for values that step N produces and step N+1 needs,
# e.g., the C2 repo name from step 16 needed by steps 17-18.


def save_session_data(key: str, value: Any) -> None:
    """Save a key-value pair to the session file."""
    data = load_all_session_data()
    data[key] = value
    try:
        os.makedirs(_LOGS_DIR, exist_ok=True)
        with open(_SESSION_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def load_session_data(key: str, default: Any = None) -> Any:
    """Load a value from the session file."""
    return load_all_session_data().get(key, default)


def load_all_session_data() -> dict:
    """Load all session data."""
    if os.path.exists(_SESSION_FILE):
        try:
            with open(_SESSION_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


# Legacy alias for backward compatibility
def mark_phase_complete(phase: int) -> None:
    """Legacy: mark all steps in a phase as complete."""
    pass  # Now handled at step level


def get_completed_phases() -> dict:
    """Legacy: return phase completion status derived from step completion."""
    return get_completed_steps()


def init_logging(log_dir: Optional[str] = None) -> str:
    """
    Initialize the structured log file.

    Returns:
        The path to the log file.
    """
    global _log_file, _log_start_time

    if log_dir is None:
        log_dir = str(Path(__file__).resolve().parent.parent / "logs")

    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(log_dir, f"attack-run-{timestamp}.jsonl")

    try:
        _log_file = open(log_path, "w")
        _log_start_time = time.time()
        log_event("system", "Logging initialized", data={"log_file": log_path})
    except Exception:
        pass  # Logging is optional; never block on failure

    return log_path


def log_event(
    level: str,
    message: str,
    phase: Optional[int] = None,
    step: Optional[int] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Write a structured event to the log file (if logging is enabled)."""
    if _log_file is None:
        return

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.time() - _log_start_time, 2)
        if _log_start_time
        else 0,
        "level": level,
        "message": message,
    }
    if phase is not None:
        entry["phase"] = phase
    if step is not None:
        entry["step"] = step
    if data is not None:
        entry["data"] = _truncate_data(data)

    try:
        _log_file.write(json.dumps(entry, default=str) + "\n")
        _log_file.flush()
    except Exception:
        pass  # Never let logging break the attack


def close_logging() -> None:
    """Close the log file."""
    global _log_file
    if _log_file is not None:
        try:
            log_event("system", "Logging closed")
            _log_file.close()
        except Exception:
            pass
        _log_file = None


def _truncate_data(data: Any, max_str_len: int = 500) -> Any:
    """Recursively truncate long string values in log data."""
    if isinstance(data, str):
        return data[:max_str_len] + "..." if len(data) > max_str_len else data
    if isinstance(data, dict):
        return {k: _truncate_data(v, max_str_len) for k, v in data.items()}
    if isinstance(data, list):
        return [_truncate_data(v, max_str_len) for v in data[:20]]
    return data


# =============================================================================
# Current Phase Tracking
# =============================================================================

_current_phase: Optional[int] = None
_current_step: Optional[str] = None


# =============================================================================
# Output Formatting (with integrated logging)
# =============================================================================


def print_phase_banner(phase_number: int, title: str) -> None:
    """Print a prominent colored banner marking the start of an attack phase."""
    global _current_phase, _current_step
    _current_phase = phase_number
    _current_step = None

    banner_colors = {
        0: "bright_cyan",
        1: "bright_yellow",
        2: "bright_red",
        3: "bright_green",
        4: "bright_magenta",
        5: "dim",
    }
    color = banner_colors.get(phase_number, "bright_white")
    console.print()
    console.print(
        Panel(
            f"[bold {color}]PHASE {phase_number}: {title}[/bold {color}]",
            border_style=color,
            box=box.DOUBLE,
            expand=True,
            padding=(1, 2),
        )
    )
    console.print()
    log_event("phase", f"Phase {phase_number}: {title}", phase=phase_number)


def print_step(step_id: str, description: str) -> None:
    """Print a step indicator using the step ID (e.g., '2.1')."""
    global _current_step
    _current_step = step_id

    console.print(
        f"\n  [bold bright_white][Step {step_id}][/bold bright_white] "
        f"[white]{description}[/white]"
    )
    log_event("step", description, phase=_current_phase, step=step_id)


def print_link(label: str, url: str) -> None:
    """Print a clickable verification link."""
    console.print(f"  [dim]  --> {label}:[/dim] [bright_cyan]{url}[/bright_cyan]")
    log_event("info", f"{label}: {url}", phase=_current_phase, step=_current_step)


def print_value(label: str, value: str) -> None:
    """Print a key-value result (for showing stolen data, IDs, etc)."""
    console.print(f"      [dim]{label}:[/dim] [bright_white]{value}[/bright_white]")
    log_event("info", f"{label}: {value}", phase=_current_phase, step=_current_step)


def print_detection(cnapp_component: str, description: str) -> None:
    """Print what a CNAPP platform would detect at this point."""
    component_colors = {
        "CSPM": "bright_blue",
        "CDR": "bright_red",
        "CWP": "bright_green",
        "CIEM": "bright_yellow",
        "DSPM": "bright_magenta",
        "ASPM": "bright_cyan",
        "SCA": "bright_white",
    }
    color = component_colors.get(cnapp_component, "white")
    console.print(
        f"    [dim]>> CNAPP[/dim] [{color}]{cnapp_component}[/{color}] "
        f"[dim]{description}[/dim]"
    )
    log_event(
        "detection",
        f"[{cnapp_component}] {description}",
        phase=_current_phase,
        step=_current_step,
    )


def print_success(message: str) -> None:
    """Print a success message in green."""
    console.print(f"  [bold bright_green][+][/bold bright_green] {message}")
    log_event("success", message, phase=_current_phase, step=_current_step)


def print_error(message: str) -> None:
    """Print an error message in red."""
    console.print(f"  [bold bright_red][-][/bold bright_red] {message}")
    log_event("error", message, phase=_current_phase, step=_current_step)


def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    console.print(
        f"  [bold bright_yellow][!][/bold bright_yellow] {message}"
    )
    log_event("warning", message, phase=_current_phase, step=_current_step)


def print_info(message: str) -> None:
    """Print an informational message in dim white."""
    console.print(f"  [dim][*][/dim] {message}")
    log_event("info", message, phase=_current_phase, step=_current_step)


# =============================================================================
# Table Formatting
# =============================================================================


def format_table(
    title: str,
    headers: List[str],
    rows: List[List[str]],
    styles: Optional[List[str]] = None,
) -> Table:
    """Create a formatted rich Table."""
    table = Table(title=title, box=box.ROUNDED, show_lines=True)
    if styles is None:
        styles = ["bright_white"] * len(headers)
    for header, style in zip(headers, styles):
        table.add_column(header, style=style)
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    return table


# =============================================================================
# Retry Logic
# =============================================================================


def safe_api_call(
    func: Callable,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    non_retryable: Optional[List[str]] = None,
    **kwargs: Any,
) -> Any:
    """
    Wrapper with retry logic and error handling for cloud API calls.

    Works with boto3, azure-sdk, and google-cloud-python clients.
    Returns the result on success, raises the last error on failure.
    """
    if non_retryable is None:
        non_retryable = [
            "AccessDeniedException",
            "AccessDenied",
            "UnauthorizedAccess",
            "ResourceNotFoundException",
            "ValidationException",
            "InvalidParameterValueException",
            "AuthorizationError",
            "Forbidden",
        ]

    last_error = None
    for attempt in range(max_retries):
        try:
            return func(**kwargs)
        except Exception as exc:
            # Check for non-retryable errors across cloud SDKs
            error_code = _extract_error_code(exc)
            if error_code and error_code in non_retryable:
                raise

            last_error = exc
            if attempt < max_retries - 1:
                delay = retry_delay * (2**attempt)
                print_warning(
                    f"API call failed ({error_code or type(exc).__name__}), "
                    f"retrying in {delay:.0f}s... "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
    raise last_error


def _extract_error_code(exc: Exception) -> Optional[str]:
    """Extract an error code from various cloud SDK exception types."""
    # boto3 / botocore
    if hasattr(exc, "response"):
        return exc.response.get("Error", {}).get("Code")
    # azure-sdk
    if hasattr(exc, "error"):
        err = getattr(exc, "error", None)
        if hasattr(err, "code"):
            return err.code
    # google-cloud
    if hasattr(exc, "code"):
        return str(exc.code)
    return None


# =============================================================================
# SSH Helpers
# =============================================================================


def wait_for_ssh(
    host: str,
    port: int = 22,
    max_wait: int = 120,
    poll_interval: int = 10,
) -> bool:
    """Poll until SSH port is accepting connections."""
    import socket

    start = time.time()
    while time.time() - start < max_wait:
        try:
            sock = socket.create_connection((host, port), timeout=5)
            sock.close()
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            time.sleep(poll_interval)
    return False
