"""Git inspection helpers for PR proposal generation.

Per IMPLEMENTATION_PLAN_PR_APPROVAL_PIPELINE.md:
- Deterministic, local-only git operations
- No network calls
- Stable output parsing (git diff --numstat)

Contract:
- get_diff_stats: Compute diff stats vs base ref (default HEAD~1)
- ensure_branch: Create or switch to branch
- commit_all: Stage all changes and commit, returning commit SHA
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class DiffStats:
    """Diff statistics from git diff --numstat."""

    files: list[str]  # Changed file paths
    added: int  # Total lines added
    removed: int  # Total lines removed


def get_diff_stats(base_ref: str = "HEAD~1") -> DiffStats:
    """Compute diff stats vs base ref.

    Uses `git diff --numstat` for stable, parseable output.

    Args:
        base_ref: Git ref to diff against (default: HEAD~1)

    Returns:
        DiffStats with files changed and line counts

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    # Run git diff --numstat
    result = subprocess.run(
        ["git", "diff", "--numstat", base_ref],
        capture_output=True,
        text=True,
        check=True,
    )

    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []

    files = []
    total_added = 0
    total_removed = 0

    for line in lines:
        parts = line.split("\t")
        if len(parts) < 3:
            continue

        added_str, removed_str, file_path = parts[0], parts[1], parts[2]

        # Handle binary files (marked as "-")
        added = 0 if added_str == "-" else int(added_str)
        removed = 0 if removed_str == "-" else int(removed_str)

        files.append(file_path)
        total_added += added
        total_removed += removed

    return DiffStats(files=files, added=total_added, removed=total_removed)


def ensure_branch(branch: str) -> None:
    """Create or switch to branch.

    Args:
        branch: Branch name to ensure exists

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    # Check if branch exists
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        # Branch exists, switch to it
        subprocess.run(["git", "checkout", branch], check=True, capture_output=True)
    else:
        # Branch doesn't exist, create it
        subprocess.run(["git", "checkout", "-b", branch], check=True, capture_output=True)


def commit_all(message: str) -> str:
    """Stage all changes and commit.

    Args:
        message: Commit message

    Returns:
        Commit SHA (short form)

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    # Stage all changes
    subprocess.run(["git", "add", "."], check=True, capture_output=True)

    # Commit
    subprocess.run(
        ["git", "commit", "-m", message],
        check=True,
        capture_output=True,
    )

    # Get commit SHA
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()


def get_current_branch() -> str:
    """Get current branch name.

    Returns:
        Current branch name

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_commit_sha(ref: str = "HEAD") -> str:
    """Get full commit SHA for ref.

    Args:
        ref: Git ref (default: HEAD)

    Returns:
        Full commit SHA

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    result = subprocess.run(
        ["git", "rev-parse", ref],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
