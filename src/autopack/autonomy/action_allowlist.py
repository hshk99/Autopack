"""Action allowlist for safe autopilot execution (BUILD-180).

Defines which actions can be auto-executed by autopilot without approval.
Only read-only commands and run-local artifact writes are allowed.
"""

import logging
import re
from enum import Enum
from typing import List

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of actions autopilot can perform."""

    COMMAND = "command"
    FILE_WRITE = "file_write"
    FILE_READ = "file_read"
    FILE_DELETE = "file_delete"


class ActionClassification(Enum):
    """Classification of action safety."""

    SAFE = "safe"  # Can be auto-executed
    REQUIRES_APPROVAL = "requires_approval"  # Needs explicit approval
    BLOCKED = "blocked"  # Never allowed


# Paths that require approval for any write operation
REPO_WRITE_PATHS: List[str] = [
    "docs/",
    "config/",
    "src/",
    "tests/",
    ".github/",
    "scripts/",
    "README.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
]

# Safe action types (can be auto-executed)
SAFE_ACTION_TYPES: List[ActionType] = [
    ActionType.FILE_READ,
]

# Patterns for safe read-only commands
SAFE_COMMAND_PATTERNS: List[str] = [
    # Git read-only commands
    r"^git\s+status",
    r"^git\s+diff",
    r"^git\s+log",
    r"^git\s+show",
    r"^git\s+branch",
    r"^git\s+rev-parse",
    # Doc drift checks (read-only)
    r"python\s+scripts/check_docs_drift\.py",
    r"python\s+-m\s+pytest.*tests/docs/.*--collect-only",
    r"python\s+scripts/tidy/sot_summary_refresh\.py\s+--check",
    # Test collection (not execution)
    r"pytest.*--collect-only",
    # Linting in check mode
    r"black\s+--check",
    r"ruff\s+check",
    r"mypy",
    r"flake8",
    # File listing
    r"^ls\b",
    r"^dir\b",
    r"^find\b.*-name",
    # Simple read-only commands
    r"^echo\b",
]

# Patterns that require approval even if they match safe patterns
REQUIRES_APPROVAL_PATTERNS: List[str] = [
    # Tidy with --execute
    r"--execute",
    # Any rm/del commands
    r"\brm\b",
    r"\bdel\b",
    r"\brmdir\b",
    # Git write commands
    r"^git\s+push",
    r"^git\s+commit",
    r"^git\s+reset",
    r"^git\s+checkout",
    r"^git\s+merge",
    r"^git\s+rebase",
    # Package installation
    r"pip\s+install",
    r"npm\s+install",
]

# Run-local artifact path pattern (safe for writes)
RUN_LOCAL_ARTIFACT_PATTERN = r"^\.autonomous_runs/"

# Shell metacharacters that enable command chaining / redirection.
# SafeActionExecutor uses shlex.split() + shell=False, but we still treat commands
# containing these metacharacters as requiring approval for defense in depth.
SHELL_METACHAR_PATTERN = r"[;&|><`]"


def is_action_safe(action_type: ActionType, target: str) -> bool:
    """Check if an action is safe to auto-execute.

    Args:
        action_type: Type of action
        target: Target of action (command string or file path)

    Returns:
        True if action is safe to auto-execute
    """
    classification = classify_action(action_type, target)
    return classification == ActionClassification.SAFE


def classify_action(action_type: ActionType, target: str) -> ActionClassification:
    """Classify an action's safety level.

    Args:
        action_type: Type of action
        target: Target of action (command string or file path)

    Returns:
        ActionClassification indicating safety level
    """
    if action_type == ActionType.FILE_READ:
        return ActionClassification.SAFE

    if action_type == ActionType.FILE_DELETE:
        return ActionClassification.REQUIRES_APPROVAL

    if action_type == ActionType.FILE_WRITE:
        return _classify_file_write(target)

    if action_type == ActionType.COMMAND:
        return _classify_command(target)

    return ActionClassification.REQUIRES_APPROVAL


def _classify_file_write(path: str) -> ActionClassification:
    """Classify a file write action.

    Args:
        path: File path to write to

    Returns:
        ActionClassification
    """
    # Normalize path separators
    normalized_path = path.replace("\\", "/")

    # Run-local artifacts are safe
    if re.match(RUN_LOCAL_ARTIFACT_PATTERN, normalized_path):
        return ActionClassification.SAFE

    # Check against repo write paths
    for repo_path in REPO_WRITE_PATHS:
        if normalized_path.startswith(repo_path) or normalized_path == repo_path.rstrip("/"):
            return ActionClassification.REQUIRES_APPROVAL

    # Root-level files require approval
    if "/" not in normalized_path:
        return ActionClassification.REQUIRES_APPROVAL

    # Default to requiring approval for safety
    return ActionClassification.REQUIRES_APPROVAL


def _classify_command(command: str) -> ActionClassification:
    """Classify a command action.

    Args:
        command: Command string

    Returns:
        ActionClassification
    """
    # Block auto-execution for any shell metacharacters / chaining.
    # SECURITY: This check MUST happen FIRST, before pattern matching.
    # Otherwise "git status && rm -rf /" could match "git status" as safe.
    if re.search(SHELL_METACHAR_PATTERN, command):
        logger.warning(f"Blocked action with shell metacharacters: {command}")
        return ActionClassification.REQUIRES_APPROVAL
    if "$(" in command:
        logger.warning(f"Blocked action with command substitution: {command}")
        return ActionClassification.REQUIRES_APPROVAL

    # Check for requires-approval patterns first (higher priority)
    for pattern in REQUIRES_APPROVAL_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return ActionClassification.REQUIRES_APPROVAL

    # Check for safe patterns
    for pattern in SAFE_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return ActionClassification.SAFE

    # Default to requiring approval
    return ActionClassification.REQUIRES_APPROVAL


def get_safe_commands_description() -> str:
    """Get human-readable description of safe commands.

    Returns:
        Description string for documentation
    """
    return """
Safe commands (can be auto-executed):
- git status, diff, log, show, branch, rev-parse (read-only git)
- python scripts/check_docs_drift.py (doc drift check)
- python scripts/tidy/sot_summary_refresh.py --check (SOT check mode)
- pytest --collect-only (test collection only)
- black --check, ruff check, mypy, flake8 (linting in check mode)
- ls, dir, find (file listing)

Commands requiring approval:
- Any command with --execute flag
- rm, del, rmdir (deletions)
- git push, commit, reset, checkout, merge, rebase (git writes)
- pip install, npm install (package installation)
"""
