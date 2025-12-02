"""Git rollback functionality for autonomous build system.

Provides branch-based rollback points for build runs, allowing safe
restoration of repository state if a run fails or needs to be reverted.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GitRollbackError(Exception):
    """Base exception for git rollback operations."""
    pass


class GitRollback:
    """Manages git-based rollback points for build runs."""

    def __init__(self, repo_path: Optional[Path] = None):
        """
        Initialize git rollback manager.

        Args:
            repo_path: Path to git repository. Defaults to current directory.
        """
        self.repo_path = repo_path or Path.cwd()
        self._verify_git_repo()

    def _verify_git_repo(self) -> None:
        """Verify that repo_path is a valid git repository."""
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            raise GitRollbackError(f"Not a git repository: {self.repo_path}")

    def _run_git_command(
        self, 
        args: list[str], 
        check: bool = True,
        capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Run a git command in the repository.

        Args:
            args: Git command arguments (without 'git' prefix)
            check: Whether to raise exception on non-zero exit
            capture_output: Whether to capture stdout/stderr

        Returns:
            CompletedProcess instance

        Raises:
            GitRollbackError: If command fails and check=True
        """
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.repo_path,
                check=check,
                capture_output=capture_output,
                text=True
            )
            return result
        except subprocess.CalledProcessError as e:
            error_msg = f"Git command failed: {' '.join(args)}"
            if e.stderr:
                error_msg += f"\n{e.stderr}"
            raise GitRollbackError(error_msg) from e

    def _get_branch_name(self, run_id: str) -> str:
        """Generate rollback branch name for a run ID."""
        return f"autopack/pre-run-{run_id}"

    def _has_uncommitted_changes(self) -> bool:
        """Check if repository has uncommitted changes."""
        result = self._run_git_command(["status", "--porcelain"])
        return bool(result.stdout.strip())

    def _stash_changes(self) -> bool:
        """
        Stash uncommitted changes.

        Returns:
            True if changes were stashed, False if nothing to stash
        """
        result = self._run_git_command(["stash", "push", "-u", "-m", "autopack-rollback-stash"])
        return "No local changes to save" not in result.stdout

    def _branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists."""
        result = self._run_git_command(
            ["rev-parse", "--verify", branch_name],
            check=False
        )
        return result.returncode == 0

    def create_rollback_point(self, run_id: str) -> str:
        """
        Create a rollback point for a build run.

        Creates a branch at the current HEAD that can be used to restore
        repository state if the run needs to be rolled back.

        Args:
            run_id: Unique identifier for the build run

        Returns:
            Name of the created rollback branch

        Raises:
            GitRollbackError: If rollback point creation fails
        """
        branch_name = self._get_branch_name(run_id)
        
        # Check for uncommitted changes
        if self._has_uncommitted_changes():
            logger.warning(f"Uncommitted changes detected, stashing before creating rollback point")
            if self._stash_changes():
                logger.info("Changes stashed successfully")

        # Check if branch already exists
        if self._branch_exists(branch_name):
            logger.warning(f"Rollback branch {branch_name} already exists, force overwriting")
            self._run_git_command(["branch", "-D", branch_name])

        # Create the rollback branch
        self._run_git_command(["branch", branch_name])
        logger.info(f"Created rollback point: {branch_name}")
        
        return branch_name

    def rollback_to_point(self, run_id: str) -> bool:
        """
        Rollback repository to a previous rollback point.

        Performs a hard reset to the specified rollback branch, discarding
        all changes made since the rollback point was created.

        Args:
            run_id: Unique identifier for the build run to rollback

        Returns:
            True if rollback succeeded, False otherwise
        """
        branch_name = self._get_branch_name(run_id)
        
        if not self._branch_exists(branch_name):
            logger.error(f"Rollback branch {branch_name} not found")
            return False

        try:
            # Hard reset to the rollback branch
            self._run_git_command(["reset", "--hard", branch_name])
            logger.info(f"Successfully rolled back to {branch_name}")
            return True
        except GitRollbackError as e:
            logger.error(f"Failed to rollback to {branch_name}: {e}")
            return False

    def cleanup_rollback_point(self, run_id: str) -> bool:
        """
        Clean up a rollback point after successful run completion.

        Args:
            run_id: Unique identifier for the completed build run

        Returns:
            True if cleanup succeeded, False otherwise
        """
        branch_name = self._get_branch_name(run_id)
        
        if not self._branch_exists(branch_name):
            logger.warning(f"Rollback branch {branch_name} not found, nothing to clean up")
            return True

        try:
            self._run_git_command(["branch", "-D", branch_name])
            logger.info(f"Cleaned up rollback point: {branch_name}")
            return True
        except GitRollbackError as e:
            logger.error(f"Failed to cleanup rollback point {branch_name}: {e}")
            return False


# Convenience functions for backward compatibility
def create_rollback_point(run_id: str) -> str:
    """Create a rollback point for a build run."""
    rollback = GitRollback()
    return rollback.create_rollback_point(run_id)


def rollback_to_point(run_id: str) -> bool:
    """Rollback repository to a previous rollback point."""
    rollback = GitRollback()
    return rollback.rollback_to_point(run_id)


def cleanup_rollback_point(run_id: str) -> bool:
    """Clean up a rollback point after successful run completion."""
    rollback = GitRollback()
    return rollback.cleanup_rollback_point(run_id)
