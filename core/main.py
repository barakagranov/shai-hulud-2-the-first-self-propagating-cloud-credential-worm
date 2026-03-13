#!/usr/bin/env python3
"""
main.py -- Shai-Hulud 2.0: Supply Chain Worm Simulation Launcher

Step-by-step execution with phase grouping. Each of the 16 steps can be
run independently, or grouped by phase, or all at once.

Modes:
  python main.py              Interactive step-level menu
  python main.py --auto       Full automated attack (skips completed steps)
  python main.py --manual     Print SSH commands for manual execution
  python main.py status       Show lab environment status
  python main.py report       Generate report from last log file

Flags:
  --log            Write structured log to logs/ directory
  --report         Generate Markdown report after attack completes
  --fresh          Clear progress and run from scratch
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Set up imports: core/ and attack/ directories
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "attack"))

from rich.panel import Panel
from rich.prompt import Prompt
from rich import box

from config import AttackConfig
from utils import (
    console,
    clear_progress,
    format_table,
    get_completed_steps,
    init_logging,
    close_logging,
    is_step_complete,
    print_error,
    print_info,
    print_success,
    print_warning,
)

# =============================================================================
# Constants
# =============================================================================

BANNER = r"""
[bright_yellow]  ____  _           _       _   _       _           _   ____    ___
 / ___|| |__   __ _(_)     | | | |_   _| |_   _  __| | |___ \  / _ \
 \___ \| '_ \ / _` | |_____| |_| | | | | | | | |/ _` |   __) || | | |
  ___) | | | | (_| | |_____|  _  | |_| | | |_| | (_| |  / __/ | |_| |
 |____/|_| |_|\__,_|_|     |_| |_|\__,_|_|\__,_|\__,_| |_____(_)___/
[/bright_yellow]
[dim]Supply Chain Worm Simulation | 16 steps across AWS + Azure + GCP + GitHub + npm[/dim]
[dim]Based on the real attack: 796 packages, 25,000 repos, 14,000 secrets[/dim]
"""

TERRAFORM_DIR = str(Path(__file__).resolve().parent.parent / "terraform")


# =============================================================================
# Phase Module Registry
# =============================================================================

def _load_phase_modules():
    """Import all phase modules and build the unified step registry."""
    import phase_0_initial_access as p0
    import phase_1_payload_delivery as p1
    import phase_2_credential_harvest as p2
    import phase_3_self_propagation as p3
    import phase_4_persistence as p4
    import phase_5_dead_mans_switch as p5

    modules = [p0, p1, p2, p3, p4, p5]

    phases = []
    all_steps = []
    step_map = {}  # step_id -> (func, phase_num, step_name, module)

    for mod in modules:
        phase_info = {
            "num": mod.PHASE_NUM,
            "name": mod.PHASE_NAME,
            "description": mod.PHASE_DESCRIPTION,
            "steps": mod.STEPS,
            "independent": getattr(mod, "INDEPENDENT_STEPS", False),
            "module": mod,
        }
        phases.append(phase_info)

        for step_id, step_name, step_func in mod.STEPS:
            step_entry = {
                "id": step_id,
                "name": step_name,
                "func": step_func,
                "phase_num": mod.PHASE_NUM,
                "phase_name": mod.PHASE_NAME,
                "independent": getattr(mod, "INDEPENDENT_STEPS", False),
            }
            all_steps.append(step_entry)
            step_map[step_id] = step_entry

    return phases, all_steps, step_map


# =============================================================================
# Terraform Check
# =============================================================================

def terraform_is_deployed() -> bool:
    """Check if Terraform state exists with resources."""
    tfstate = Path(TERRAFORM_DIR) / "terraform.tfstate"
    if not tfstate.exists():
        return False
    try:
        with open(tfstate) as f:
            state = json.load(f)
        return len(state.get("resources", [])) > 0
    except (json.JSONDecodeError, IOError):
        return False


# =============================================================================
# Menu Display
# =============================================================================

def _step_status(step_id: str) -> str:
    """Return a colored status indicator for a step."""
    if is_step_complete(step_id):
        return "[bright_green]DONE[/bright_green]"
    return "[dim]    [/dim]"


def print_menu(phases):
    """Print the interactive step-level menu."""
    lines = []

    phase_colors = {
        0: "bright_cyan", 1: "bright_yellow", 2: "bright_red",
        3: "bright_green", 4: "bright_magenta", 5: "dim",
    }

    for phase in phases:
        num = phase["num"]
        color = phase_colors.get(num, "white")
        lines.append(
            f"  [{color}]Phase {num}: {phase['name']}[/{color}]"
            f"  [dim]({phase['description']})[/dim]"
        )
        for step_id, step_name, _ in phase["steps"]:
            status = _step_status(step_id)
            lines.append(f"    [{color}]{step_id}[/{color}]  {step_name}  {status}")
        lines.append("")

    lines.append("  [bold bright_white]Commands:[/bold bright_white]")
    lines.append("    [bright_white]2.1[/bright_white]       Run a single step")
    lines.append("    [bright_white]2[/bright_white] or [bright_white]p2[/bright_white]   Run all steps in a phase")
    lines.append("    [bright_white]all[/bright_white]       Run all steps sequentially")
    lines.append("    [bright_white]config[/bright_white]    Show configuration")
    lines.append("    [bright_white]status[/bright_white]    Lab status")
    lines.append("    [bright_white]exit[/bright_white]      Exit")

    console.print(Panel(
        "\n".join(lines),
        title="[bold]Shai-Hulud 2.0[/bold]",
        border_style="bright_yellow",
        box=box.ROUNDED,
    ))


# =============================================================================
# Step Execution
# =============================================================================

def run_step(step_entry: dict, config: AttackConfig) -> dict:
    """Run a single step and return results."""
    step_id = step_entry["id"]
    step_name = step_entry["name"]

    if is_step_complete(step_id):
        print_info(f"Step {step_id} already completed. Re-running...")

    result = step_entry["func"](config)
    return result


def run_phase_steps(phase: dict, config: AttackConfig, skip_completed: bool = False) -> dict:
    """Run all steps in a phase."""
    from utils import print_phase_banner
    print_phase_banner(phase["num"], f"{phase['name'].upper()} -- {phase['description']}")

    results = {}
    for step_id, step_name, step_func in phase["steps"]:
        if skip_completed and is_step_complete(step_id):
            print_info(f"Step {step_id} already completed, skipping")
            continue

        try:
            results[step_id] = step_func(config)
            if not results[step_id] and not phase.get("independent"):
                print_warning(f"Step {step_id} returned empty, stopping phase")
                break
        except RuntimeError as exc:
            print_error(str(exc))
            if not phase.get("independent"):
                break
        except Exception as exc:
            print_error(f"Step {step_id} error: {exc}")
            if not phase.get("independent"):
                break

    return results


def run_all(phases, config: AttackConfig, skip_completed: bool = True) -> dict:
    """Run all phases and steps sequentially."""
    console.print(Panel(
        "[bold bright_red]FULL ATTACK CHAIN[/bold bright_red]\n"
        "[dim]Running all 16 steps across 6 phases...[/dim]",
        border_style="bright_red", box=box.DOUBLE,
    ))

    all_results = {}
    for phase in phases:
        try:
            phase_results = run_phase_steps(phase, config, skip_completed=skip_completed)
            all_results.update(phase_results)
        except Exception as exc:
            print_error(f"Phase {phase['num']} failed: {exc}")

    print_attack_summary(phases)
    return all_results


def print_attack_summary(phases):
    """Print a summary table of all steps."""
    console.print()
    console.print(Panel(
        "[bold bright_green]ATTACK COMPLETE[/bold bright_green]",
        border_style="bright_green", box=box.DOUBLE, expand=True,
    ))

    rows = []
    completed = get_completed_steps()
    for phase in phases:
        for step_id, step_name, _ in phase["steps"]:
            status = "DONE" if completed.get(step_id) else "SKIPPED"
            rows.append([step_id, step_name, status])

    table = format_table(
        "Attack Summary",
        ["Step", "Name", "Status"],
        rows,
        ["bright_cyan", "bright_white", "bright_green"],
    )
    console.print(table)

    total_done = sum(1 for v in completed.values() if v)
    total_steps = sum(len(p["steps"]) for p in phases)
    console.print(f"\n  [bright_white]{total_done}/{total_steps} steps completed[/bright_white]")


# =============================================================================
# Interactive Mode
# =============================================================================

def run_interactive(config: AttackConfig) -> dict:
    """Step-level interactive menu."""
    phases, all_steps, step_map = _load_phase_modules()
    all_results = {}

    while True:
        console.print()
        print_menu(phases)

        try:
            choice = Prompt.ask("\n  [bright_white]>[/bright_white]", default="exit").strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print("\n  Exiting.")
            break

        if choice in ("exit", "quit", "q"):
            break
        elif choice == "config":
            config.print_config_summary()
        elif choice == "status":
            import status as status_mod
            status_mod.run_status()
        elif choice == "all":
            all_results = run_all(phases, config)
        elif choice.startswith("p") and choice[1:].isdigit():
            # Run an entire phase: "p2" syntax
            phase_num = int(choice[1:])
            matching = [p for p in phases if p["num"] == phase_num]
            if matching:
                try:
                    results = run_phase_steps(matching[0], config)
                    all_results.update(results)
                except RuntimeError as exc:
                    print_error(str(exc))
            else:
                print_error(f"Unknown phase: {phase_num}")
        elif choice.isdigit() and 0 <= int(choice) <= 5:
            # Run an entire phase: bare digit "2" syntax
            phase_num = int(choice)
            matching = [p for p in phases if p["num"] == phase_num]
            if matching:
                try:
                    results = run_phase_steps(matching[0], config)
                    all_results.update(results)
                except RuntimeError as exc:
                    print_error(str(exc))
            else:
                print_error(f"Unknown phase: {phase_num}")
        elif choice in step_map:
            # Run a specific step
            try:
                result = run_step(step_map[choice], config)
                all_results[choice] = result
            except RuntimeError as exc:
                print_error(str(exc))
            except Exception as exc:
                print_error(f"Step {choice} failed: {exc}")
        else:
            print_error(f"Unknown command: '{choice}'. Try a step (e.g. 2.1), a phase (e.g. 2 or p2), 'all', or 'exit'.")

    return all_results


# =============================================================================
# Manual Mode
# =============================================================================

def run_manual(config: AttackConfig) -> None:
    """Print configuration and SSH commands for manual execution."""
    console.print(Panel(
        "[bold bright_yellow]MANUAL MODE[/bold bright_yellow]\n"
        "[dim]Follow docs/attack_guide.md for the full walkthrough.[/dim]",
        border_style="bright_yellow", box=box.DOUBLE,
    ))

    config.print_config_summary()
    console.print()
    console.print("[bold]SSH Commands:[/bold]")
    console.print(f"  [cyan]# AWS EC2[/cyan]")
    console.print(f"  ssh -i {config.ssh_key_path} -o StrictHostKeyChecking=no ec2-user@{config.aws_instance_public_ip}")
    console.print(f"  [cyan]# Azure VM (password: {config.azure_vm_password})[/cyan]")
    console.print(f"  ssh -o StrictHostKeyChecking=no azureuser@{config.azure_vm_public_ip}")
    console.print(f"  [cyan]# GCP GCE[/cyan]")
    console.print(f"  gcloud compute ssh {config.gcp_instance_name} --zone={config.gcp_instance_zone}")
    console.print()
    console.print("[dim]Full walkthrough: docs/attack_guide.md[/dim]")


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Shai-Hulud 2.0: Supply Chain Worm Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py                  # Interactive step menu\n"
            "  python main.py --auto           # Full automated attack\n"
            "  python main.py --auto --fresh   # Clean run (clear progress first)\n"
            "  python main.py --auto --log     # Attack with logging\n"
            "  python main.py status           # Check lab state\n"
            "  python main.py report           # Report from last log\n"
        ),
    )
    parser.add_argument("command", nargs="?", default=None, help="Subcommand: status, report")
    parser.add_argument("--auto", action="store_true", help="Run all steps automatically")
    parser.add_argument("--manual", action="store_true", help="Print manual execution commands")
    parser.add_argument("--log", action="store_true", help="Write structured log to logs/")
    parser.add_argument("--report", action="store_true", help="Generate report after attack")
    parser.add_argument("--fresh", action="store_true", help="Clear progress before running")

    args = parser.parse_args()

    # --- Subcommands ---
    if args.command == "status":
        import status as status_mod
        console.print(BANNER)
        status_mod.run_status()
        return

    if args.command == "report":
        import report as report_mod
        log_dir = Path(__file__).resolve().parent.parent / "logs"
        logs = sorted(log_dir.glob("*.jsonl"), reverse=True) if log_dir.exists() else []
        if not logs:
            print_error("No log files found. Run with --log first."); sys.exit(1)
        report_path = report_mod.generate_report_from_log(str(logs[0]))
        if report_path:
            print_success(f"Report: {report_path}")
        return

    # --- Main attack flow ---
    console.print(BANNER)

    log_path = None
    if args.log or args.report:
        log_path = init_logging()
        print_success(f"Logging to: {log_path}")

    if args.fresh:
        clear_progress()
        print_info("Progress cleared (fresh run)")

    if not terraform_is_deployed():
        print_error("Infrastructure not deployed. Run ./setup.sh first.")
        sys.exit(1)

    try:
        config = AttackConfig(terraform_dir=TERRAFORM_DIR)
    except RuntimeError as exc:
        print_error(f"Config load failed: {exc}")
        sys.exit(1)

    all_results = {}
    try:
        if args.manual:
            run_manual(config)
        elif args.auto:
            phases, _, _ = _load_phase_modules()
            all_results = run_all(phases, config, skip_completed=not args.fresh)
        else:
            all_results = run_interactive(config)
    except KeyboardInterrupt:
        console.print("\n\n  [dim]Interrupted.[/dim]")
    except Exception as exc:
        print_error(f"Unexpected error: {exc}")
        raise
    finally:
        close_logging()

    if args.report and all_results:
        import report as report_mod
        rpath = report_mod.generate_report(all_results, config=config, log_file=log_path)
        print_success(f"Report: {rpath}")

    if not args.manual:
        console.print()
        print_warning("Remember to clean up: ./cleanup.sh")


if __name__ == "__main__":
    main()
