"""Proof metrics for phase proofs (BUILD-180).

Pure functions for collecting deterministic metrics from git.
Used by phase_proof_writer to include real metrics when available.
"""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProofMetrics:
    """Metrics for a phase proof."""

    files_modified: int = 0
    changed_file_sample: List[str] = field(default_factory=list)
    metrics_placeholder: bool = True
    tests_passed: int = 0
    tests_failed: int = 0


def count_changed_files(workspace_root: Path) -> Optional[int]:
    """Count changed files via git diff --name-only.

    Args:
        workspace_root: Root directory of workspace

    Returns:
        Number of changed files, or None if git unavailable
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.debug(f"git diff failed with exit code {result.returncode}")
            return None

        # Count non-empty lines
        lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return len(lines)

    except subprocess.TimeoutExpired:
        logger.warning("git diff timed out")
        return None

    except FileNotFoundError:
        logger.debug("git not found")
        return None

    except Exception as e:
        logger.debug(f"Failed to count changed files: {e}")
        return None


def list_changed_files(workspace_root: Path, limit: int = 10) -> List[str]:
    """List changed files via git diff --name-only.

    Args:
        workspace_root: Root directory of workspace
        limit: Maximum number of files to return

    Returns:
        List of changed file paths (up to limit)
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return []

        lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return lines[:limit]

    except Exception as e:
        logger.debug(f"Failed to list changed files: {e}")
        return []


def count_staged_files(workspace_root: Path) -> Optional[int]:
    """Count staged files via git diff --cached --name-only.

    Args:
        workspace_root: Root directory of workspace

    Returns:
        Number of staged files, or None if git unavailable
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return None

        lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return len(lines)

    except Exception as e:
        logger.debug(f"Failed to count staged files: {e}")
        return None


def get_proof_metrics(
    workspace_root: Path,
    include_staged: bool = True,
) -> ProofMetrics:
    """Get all proof metrics for a workspace.

    Args:
        workspace_root: Root directory of workspace
        include_staged: Whether to include staged files in count

    Returns:
        ProofMetrics with real values if git available, else placeholder
    """
    # Try to get file count
    file_count = count_changed_files(workspace_root)

    if file_count is None:
        # Git unavailable - return placeholder metrics
        return ProofMetrics(
            files_modified=0,
            changed_file_sample=[],
            metrics_placeholder=True,
            tests_passed=0,
            tests_failed=0,
        )

    # Add staged files if requested
    if include_staged:
        staged_count = count_staged_files(workspace_root)
        if staged_count is not None:
            file_count += staged_count

    # Get file sample
    file_sample = list_changed_files(workspace_root)

    return ProofMetrics(
        files_modified=file_count,
        changed_file_sample=file_sample,
        metrics_placeholder=False,
        tests_passed=0,  # Would need test runner integration
        tests_failed=0,
    )


def get_commit_file_count(workspace_root: Path, commit_ref: str = "HEAD") -> Optional[int]:
    """Get file count for a specific commit.

    Args:
        workspace_root: Root directory of workspace
        commit_ref: Git commit reference

    Returns:
        Number of files changed in commit, or None if unavailable
    """
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_ref],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return None

        lines = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return len(lines)

    except Exception as e:
        logger.debug(f"Failed to get commit file count: {e}")
        return None
