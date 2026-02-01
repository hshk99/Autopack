"""Execute fix handler for phase corrections.

Extracted from autonomous_executor.py as part of PR-EXE-13.
Handles execution of fix recommendations from diagnostics or Doctor.
"""

import logging
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from autopack.debug_journal import log_error, log_fix
from autopack.executor.run_checkpoint import create_execute_fix_checkpoint

if TYPE_CHECKING:
    from ..autonomous_executor import AutonomousExecutor
    from ..doctor.doctor_response import DoctorResponse

logger = logging.getLogger(__name__)

# Constants for fix validation
MAX_EXECUTE_FIX_PER_PHASE = 1  # Maximum execute_fix attempts per phase

ALLOWED_FIX_TYPES = {"git", "file", "python"}

# Command whitelists by fix_type (regex patterns)
# Patterns are strict to prevent bypass attempts with spacing variations, escaped chars, etc.
ALLOWED_FIX_COMMANDS = {
    "git": [
        r"^git\s+checkout\s+[^\s;|&$`\(\)]+(\s+[^\s;|&$`\(\)]+)*$",  # git checkout <file>/<branch>
        r"^git\s+reset\s+--hard\s+HEAD$",  # git reset --hard HEAD (exact)
        r"^git\s+stash$",  # git stash (no args)
        r"^git\s+stash\s+pop$",  # git stash pop (exact)
        r"^git\s+clean\s+-fd$",  # git clean -fd (exact flags)
        r"^git\s+merge\s+--abort$",  # git merge --abort (exact)
        r"^git\s+rebase\s+--abort$",  # git rebase --abort (exact)
        r"^git\s+status\s+--porcelain$",  # git status --porcelain (exact)
        r"^git\s+diff\s+--name-only$",  # git diff --name-only (exact)
        r"^git\s+diff\s+--cached$",  # git diff --cached (exact)
    ],
    "file": [
        r"^rm\s+-f\s+[^\s;|&$`\(\)]+(\s+[^\s;|&$`\(\)]+)*$",  # rm -f <file>
        r"^mkdir\s+-p\s+[^\s;|&$`\(\)]+(\s+[^\s;|&$`\(\)]+)*$",  # mkdir -p <dir>
        r"^mv\s+[^\s;|&$`\(\)]+(\s+[^\s;|&$`\(\)]+)*$",  # mv <src> <dst>
        r"^cp\s+[^\s;|&$`\(\)]+(\s+[^\s;|&$`\(\)]+)*$",  # cp <src> <dst>
    ],
    "python": [
        r"^pip\s+install\s+[^\s;|&$`\(\)]+(\s+[^\s;|&$`\(\)]+)*$",  # pip install <package>
        r"^pip\s+uninstall\s+-y\s+[^\s;|&$`\(\)]+(\s+[^\s;|&$`\(\)]+)*$",  # pip uninstall -y <package>
        r"^python\s+-m\s+pip\s+install\s+[^\s;|&$`\(\)]+(\s+[^\s;|&$`\(\)]+)*$",  # python -m pip install
    ],
}

# Banned metacharacters (security: prevent command injection)
BANNED_METACHARACTERS = [
    ";",
    "&&",
    "||",
    "`",
    "$(",
    "${",
    ">",
    ">>",
    "<",
    "|",
    "\n",
    "\r",
]

# Banned command prefixes (never execute)
BANNED_COMMAND_PREFIXES = [
    "sudo",
    "su ",
    "rm -rf /",
    "dd if=",
    "chmod 777",
    "mkfs",
    ":(){ :",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    "init 0",
    "init 6",
]


def normalize_command(cmd: str) -> str:
    """Normalize command string to prevent bypass attempts.

    Normalization steps:
    1. Strip leading/trailing whitespace
    2. Convert multiple spaces to single spaces
    3. Normalize path separators (prevent ./cmd vs cmd variations)
    4. Remove escaped quotes if present (already handled by shlex)

    Args:
        cmd: Raw command string

    Returns:
        Normalized command string
    """
    # Strip leading/trailing whitespace
    cmd = cmd.strip()

    # Replace multiple spaces with single space
    cmd = re.sub(r"\s+", " ", cmd)

    # Normalize path separators (convert ../ and ./ to prevent obfuscation)
    # This helps catch patterns like "./rm" vs "rm"
    cmd = re.sub(r"\.[\\/]+", "", cmd)

    return cmd


def detect_path_bypass_attempts(cmd: str) -> bool:
    """Detect attempts to bypass command checks using path variations.

    Detects patterns like:
    - /full/path/to/rm vs rm
    - ./rm vs rm
    - .//rm vs rm
    - Relative paths with .. or .

    Args:
        cmd: Normalized command string

    Returns:
        True if bypass attempt detected, False otherwise
    """
    # Check for full paths (e.g., /usr/bin/rm instead of rm)
    # For allowed simple commands, we expect the command name directly
    command_start = cmd.split()[0] if cmd else ""

    # If command starts with /, ./, ../, or contains path separators before the base command
    if "/" in command_start or "\\" in command_start:
        # This could be a full path bypass attempt
        # For security, we don't allow full paths - always use simple command names
        return True

    return False


@dataclass
class FixExecutionResult:
    """Result of fix execution."""

    action_taken: Optional[str]
    should_continue_retry: bool


class ExecuteFixHandler:
    """Handles execution of automated fixes.

    Responsibilities:
    1. Execute fix recommendations
    2. Validate fix application
    3. Roll back failed fixes
    4. Record fix history
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor

    def execute_fix(
        self,
        phase: Dict,
        response: "DoctorResponse",
    ) -> FixExecutionResult:
        """Execute automated fix for phase issue.

        Handle Doctor's execute_fix action - direct infrastructure fixes.

        Per GPT_RESPONSE9:
        - One execute_fix attempt per phase
        - Validate commands against whitelist
        - Create git checkpoint before execution
        - Execute commands via subprocess
        - Run verify_command if provided

        Args:
            phase: Phase specification
            response: Doctor's response with fix_commands, fix_type, verify_command

        Returns:
            FixExecutionResult with action_taken and should_continue_retry
        """
        phase_id = phase.get("phase_id")

        # Check if execute_fix is enabled (user opt-in)
        if not self.executor._allow_execute_fix:
            logger.warning(
                "[Doctor] execute_fix requested but disabled. "
                "Enable via models.yaml: doctor.allow_execute_fix_global: true"
            )
            log_error(
                error_signature=f"execute_fix disabled: {phase_id}",
                symptom="execute_fix action requested but feature is disabled",
                run_id=self.executor.run_id,
                phase_id=phase_id,
                suspected_cause="User opt-in required via models.yaml",
                priority="HIGH",
            )
            # Fall back to retry_with_fix behavior
            hint = response.builder_hint or "Infrastructure fix needed but execute_fix disabled"
            self.executor._builder_hint_by_phase[phase_id] = hint
            return FixExecutionResult("execute_fix_disabled", True)

        # Check per-phase limit
        current_count = self.executor._execute_fix_by_phase.get(phase_id, 0)
        if current_count >= MAX_EXECUTE_FIX_PER_PHASE:
            logger.warning(
                f"[Doctor] execute_fix limit reached for phase {phase_id} "
                f"({current_count}/{MAX_EXECUTE_FIX_PER_PHASE})"
            )
            # Fall back to mark_fatal since we can't fix it
            self.executor._update_phase_status(phase_id, "FAILED")
            return FixExecutionResult("execute_fix_limit", False)

        # Validate fix_commands and fix_type
        fix_commands = response.fix_commands or []
        fix_type = response.fix_type or ""
        verify_command = response.verify_command

        # Safety: In project_build runs, do not allow Doctor to execute git-based fixes.
        # The git fix recipes commonly include `git reset --hard` / `git clean -fd` which will:
        # - wipe partially-generated deliverables needed for convergence
        # - create noisy checkpoint commits
        # - potentially discard unrelated local work in the repo
        #
        # For Autopack self-maintenance runs, git execute_fix is acceptable (controlled, intentional).
        if self.executor.run_type == "project_build" and fix_type == "git":
            logger.warning(
                f"[Doctor] Blocking execute_fix of type 'git' for project_build run (phase={phase_id}). "
                f"Falling back to normal retry loop."
            )
            try:
                log_fix(
                    error_signature=f"execute_fix blocked (git) for {phase_id}",
                    fix_description=(
                        "Blocked Doctor execute_fix with fix_type='git' for project_build run to prevent "
                        "destructive repo operations (e.g., git reset --hard / git clean -fd) from wiping "
                        "partially-generated deliverables and obscuring debugging history."
                    ),
                    files_changed=[],
                    run_id=self.executor.run_id,
                    phase_id=phase_id,
                    outcome="BLOCKED_GIT_EXECUTE_FIX",
                )
            except Exception:
                pass
            hint = (
                response.builder_hint
                or "Fix attempt blocked: git execute_fix is disabled for project_build runs"
            )
            self.executor._builder_hint_by_phase[phase_id] = hint
            return FixExecutionResult("execute_fix_blocked_git_project_build", True)

        if not fix_commands:
            logger.warning("[Doctor] execute_fix requested but no fix_commands provided")
            return FixExecutionResult("execute_fix_no_commands", True)

        # Validate commands
        is_valid, validation_errors = self._validate_fix_commands(fix_commands, fix_type)
        if not is_valid:
            logger.error(f"[Doctor] execute_fix command validation failed: {validation_errors}")
            log_error(
                error_signature=f"execute_fix validation failed: {phase_id}",
                symptom=f"Commands failed validation: {validation_errors}",
                run_id=self.executor.run_id,
                phase_id=phase_id,
                suspected_cause="Doctor suggested invalid/unsafe commands",
                priority="HIGH",
            )
            # Fall back to retry_with_fix
            hint = f"execute_fix validation failed: {validation_errors[0]}"
            self.executor._builder_hint_by_phase[phase_id] = hint
            return FixExecutionResult("execute_fix_invalid", True)

        # Create git checkpoint (commit) before executing
        # PR-EXE-4: Delegated to run_checkpoint module
        create_execute_fix_checkpoint(workspace=Path(self.executor.workspace), phase_id=phase_id)

        # Execute fix commands
        logger.info(f"[Doctor] Executing {len(fix_commands)} fix commands (type: {fix_type})...")
        self.executor._execute_fix_by_phase[phase_id] = current_count + 1

        all_succeeded = True
        for i, cmd in enumerate(fix_commands):
            logger.info(f"[Doctor] Executing [{i + 1}/{len(fix_commands)}]: {cmd}")
            try:
                # Parse command string into argument list safely (prevents shell injection)
                args = shlex.split(cmd)
                # Execute in workspace directory
                result = subprocess.run(
                    args,
                    shell=False,
                    cwd=str(self.executor.workspace),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    logger.error(
                        f"[Doctor] Command failed (exit {result.returncode}): {result.stderr}"
                    )
                    all_succeeded = False
                    break
                else:
                    logger.info(f"[Doctor] Command succeeded: {result.stdout[:200]}")
            except subprocess.TimeoutExpired:
                logger.error(f"[Doctor] Command timed out: {cmd}")
                all_succeeded = False
                break
            except Exception as e:
                logger.error(f"[Doctor] Command execution error: {e}")
                all_succeeded = False
                break

        # Run verify_command if provided
        if all_succeeded and verify_command:
            logger.info(f"[Doctor] Running verify command: {verify_command}")
            try:
                # Parse command string into argument list safely (prevents shell injection)
                verify_args = shlex.split(verify_command)
                verify_result = subprocess.run(
                    verify_args,
                    shell=False,
                    cwd=str(self.executor.workspace),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if verify_result.returncode != 0:
                    logger.warning(f"[Doctor] Verify command failed: {verify_result.stderr}")
                    all_succeeded = False
                else:
                    logger.info("[Doctor] Verify command passed")
            except Exception as e:
                logger.warning(f"[Doctor] Verify command error: {e}")
                all_succeeded = False

        if all_succeeded:
            logger.info("[Doctor] execute_fix succeeded - continuing retry loop")
            log_fix(
                error_signature=f"execute_fix success: {phase_id}",
                fix_description=f"Executed {len(fix_commands)} commands: {fix_commands}",
                run_id=self.executor.run_id,
                phase_id=phase_id,
                outcome="RESOLVED_BY_EXECUTE_FIX",
            )
            return FixExecutionResult("execute_fix_success", True)  # Continue retry loop
        else:
            logger.warning("[Doctor] execute_fix failed - marking phase as failed")
            self.executor._update_phase_status(phase_id, "FAILED")
            return FixExecutionResult("execute_fix_failed", False)

    def _validate_fix_commands(self, commands: List[str], fix_type: str) -> Tuple[bool, List[str]]:
        """
        Validate fix commands against whitelist and security rules.

        Security validation layers:
        1. Check fix_type is allowed
        2. Normalize command to prevent variations
        3. Detect path-based bypass attempts
        4. Check for banned command prefixes
        5. Check for banned metacharacters
        6. Validate shlex parsing
        7. Match against strict regex whitelist patterns

        Args:
            commands: List of shell commands to validate
            fix_type: Type of fix ("git", "file", "python")

        Returns:
            Tuple of (is_valid: bool, errors: List[str])
        """
        errors = []

        # Check fix_type is allowed
        if fix_type not in ALLOWED_FIX_TYPES:
            errors.append(f"fix_type '{fix_type}' not in allowed types: {ALLOWED_FIX_TYPES}")
            return False, errors

        # Get whitelist patterns for this fix_type
        whitelist_patterns = ALLOWED_FIX_COMMANDS.get(fix_type, [])
        if not whitelist_patterns:
            errors.append(f"No whitelist patterns defined for fix_type '{fix_type}'")
            return False, errors

        for cmd in commands:
            # Normalize command to prevent bypass with spacing variations
            normalized_cmd = normalize_command(cmd)

            # Detect and block path-based bypass attempts
            if detect_path_bypass_attempts(normalized_cmd):
                errors.append(
                    f"Command '{cmd}' uses path variation to bypass security (use simple command name)"
                )
                continue

            # Check for banned command prefixes (before whitespace normalization)
            cmd_stripped = cmd.strip()
            has_banned_prefix = False
            for banned in BANNED_COMMAND_PREFIXES:
                if cmd_stripped.startswith(banned):
                    errors.append(f"Command '{cmd}' uses banned prefix '{banned}'")
                    has_banned_prefix = True
                    break

            if has_banned_prefix:
                continue

            # Check for banned metacharacters
            has_banned_char = False
            for char in BANNED_METACHARACTERS:
                if char in cmd:
                    errors.append(f"Command '{cmd}' contains banned metacharacter '{char}'")
                    has_banned_char = True
                    break

            if has_banned_char:
                continue

            # Validate against whitelist using shlex + regex
            try:
                # Use shlex to properly tokenize (handles quoted arguments)
                shlex.split(cmd)
            except ValueError as e:
                errors.append(f"Command '{cmd}' failed shlex parsing: {e}")
                continue

            # Check if normalized command matches any whitelist pattern
            matched = False
            for pattern in whitelist_patterns:
                if re.match(pattern, normalized_cmd):
                    matched = True
                    break

            if not matched:
                errors.append(
                    f"Command '{cmd}' does not match any whitelist pattern for type '{fix_type}'"
                )

        return len(errors) == 0, errors
