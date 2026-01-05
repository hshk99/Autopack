"""Workspace isolation manager for parallel runs (P2.0).

Creates and manages git worktrees to enable concurrent execution of multiple
run_ids without workspace contamination. Each run gets its own isolated
git working tree while sharing the git object database.

Safety properties:
- One worktree per run_id
- Automatic cleanup on context exit
- Prevents cross-run git state pollution
- Compatible with RollbackManager (each worktree has independent git state)

Example:
    >>> with WorkspaceManager("my-run-id") as workspace:
    ...     # Execute autonomous run in isolated workspace
    ...     execute_run(workspace)
"""

import subprocess
import logging
import shutil
from pathlib import Path
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Manages isolated git worktrees for parallel run execution."""

    def __init__(
        self,
        run_id: str,
        source_repo: Optional[Path] = None,
        worktree_base: Optional[Path] = None,
        cleanup_on_exit: bool = True,
    ):
        """Initialize workspace manager.

        Args:
            run_id: Unique run identifier
            source_repo: Path to source git repository (default: current directory)
            worktree_base: Base directory for worktrees (default: {autonomous_runs_dir}/workspaces)
            cleanup_on_exit: Whether to remove worktree on context exit (default: True)
        """
        self.run_id = run_id
        self.source_repo = source_repo or Path.cwd()
        self.cleanup_on_exit = cleanup_on_exit

        # Determine worktree location
        if worktree_base is not None:
            self.worktree_base = worktree_base
        else:
            self.worktree_base = Path(settings.autonomous_runs_dir) / "workspaces"

        # Sanitize run_id for filesystem safety
        safe_run_id = run_id.replace("/", "-").replace("\\", "-").replace(" ", "-")
        self.worktree_path = self.worktree_base / safe_run_id

        self.created = False

    def create_worktree(self, branch: Optional[str] = None) -> Path:
        """Create a new git worktree for this run.

        Args:
            branch: Branch to checkout in worktree (default: HEAD detached)

        Returns:
            Path to created worktree

        Raises:
            RuntimeError: If worktree creation fails
        """
        # Ensure base directory exists
        self.worktree_base.mkdir(parents=True, exist_ok=True)

        # Check if worktree already exists
        if self.worktree_path.exists():
            logger.warning(
                f"[Workspace] Worktree already exists: {self.worktree_path}\n"
                f"  Removing and recreating..."
            )
            self.remove_worktree()

        try:
            # Build git worktree add command
            cmd = ["git", "worktree", "add"]

            if branch:
                # Checkout specific branch
                cmd.extend([str(self.worktree_path), branch])
            else:
                # Detached HEAD at current commit
                cmd.extend(["--detach", str(self.worktree_path)])

            logger.info(f"[Workspace] Creating worktree for run_id={self.run_id}")
            logger.debug(f"[Workspace] Command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd, cwd=self.source_repo, capture_output=True, text=True, timeout=60
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.error(f"[Workspace] Failed to create worktree: {error_msg}")
                raise RuntimeError(f"git worktree add failed: {error_msg}")

            self.created = True
            logger.info(f"[Workspace] Created worktree: {self.worktree_path}")

            return self.worktree_path

        except subprocess.TimeoutExpired:
            logger.error("[Workspace] Timeout creating worktree")
            raise RuntimeError("git worktree add timed out")
        except Exception as e:
            logger.error(f"[Workspace] Exception creating worktree: {e}")
            raise

    def remove_worktree(self, force: bool = False) -> bool:
        """Remove the worktree for this run.

        Args:
            force: Force removal even if worktree has uncommitted changes

        Returns:
            True if removed successfully, False otherwise
        """
        if not self.worktree_path.exists():
            logger.debug(f"[Workspace] Worktree does not exist: {self.worktree_path}")
            return True

        try:
            # First, remove from git's worktree registry
            cmd = ["git", "worktree", "remove"]
            if force:
                cmd.append("--force")
            cmd.append(str(self.worktree_path))

            logger.info(f"[Workspace] Removing worktree: {self.worktree_path}")

            result = subprocess.run(
                cmd, cwd=self.source_repo, capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.warning(f"[Workspace] git worktree remove failed: {error_msg}")

                # Fallback: manually delete directory and prune
                logger.info("[Workspace] Attempting manual cleanup...")
                if self.worktree_path.exists():
                    shutil.rmtree(self.worktree_path, ignore_errors=True)

                # Prune stale worktree references
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=self.source_repo,
                    capture_output=True,
                    timeout=10,
                )

            logger.info(f"[Workspace] Removed worktree: {self.worktree_path}")
            self.created = False
            return True

        except subprocess.TimeoutExpired:
            logger.error("[Workspace] Timeout removing worktree")
            return False
        except Exception as e:
            logger.warning(f"[Workspace] Exception removing worktree: {e}")
            return False

    def __enter__(self) -> Path:
        """Context manager entry - create worktree.

        Returns:
            Path to created worktree
        """
        return self.create_worktree()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - optionally cleanup worktree."""
        if self.cleanup_on_exit:
            # Force removal on exception to ensure cleanup even with uncommitted changes
            force = exc_type is not None
            self.remove_worktree(force=force)
        return False  # Don't suppress exceptions

    @staticmethod
    def list_worktrees(repo: Optional[Path] = None) -> list[dict]:
        """List all git worktrees for a repository.

        Args:
            repo: Repository path (default: current directory)

        Returns:
            List of worktree info dicts with keys: path, branch, commit
        """
        repo = repo or Path.cwd()

        try:
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(f"[Workspace] Failed to list worktrees: {result.stderr}")
                return []

            # Parse porcelain output
            worktrees = []
            current_worktree = {}

            for line in result.stdout.split("\n"):
                line = line.strip()
                if not line:
                    if current_worktree:
                        worktrees.append(current_worktree)
                        current_worktree = {}
                    continue

                if line.startswith("worktree "):
                    current_worktree["path"] = line.split(" ", 1)[1]
                elif line.startswith("HEAD "):
                    current_worktree["commit"] = line.split(" ", 1)[1]
                elif line.startswith("branch "):
                    current_worktree["branch"] = line.split(" ", 1)[1]
                elif line == "detached":
                    current_worktree["detached"] = True

            # Add last worktree if exists
            if current_worktree:
                worktrees.append(current_worktree)

            return worktrees

        except Exception as e:
            logger.warning(f"[Workspace] Exception listing worktrees: {e}")
            return []

    @staticmethod
    def cleanup_all_worktrees(
        repo: Optional[Path] = None, worktree_base: Optional[Path] = None
    ) -> int:
        """Remove all managed worktrees (for cleanup/reset).

        Args:
            repo: Repository path (default: current directory)
            worktree_base: Base directory for worktrees (default: {autonomous_runs_dir}/workspaces)

        Returns:
            Number of worktrees removed
        """
        repo = repo or Path.cwd()
        worktree_base = worktree_base or (Path(settings.autonomous_runs_dir) / "workspaces")

        if not worktree_base.exists():
            logger.debug(f"[Workspace] No worktrees to clean: {worktree_base}")
            return 0

        count = 0
        for worktree_dir in worktree_base.iterdir():
            if not worktree_dir.is_dir():
                continue

            try:
                # Extract run_id from directory name
                run_id = worktree_dir.name
                manager = WorkspaceManager(run_id, source_repo=repo, worktree_base=worktree_base)
                if manager.remove_worktree(force=True):
                    count += 1
            except Exception as e:
                logger.warning(f"[Workspace] Failed to remove {worktree_dir}: {e}")

        if count > 0:
            logger.info(f"[Workspace] Cleaned up {count} worktrees")

        return count
