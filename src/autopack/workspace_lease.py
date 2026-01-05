"""Workspace lease manager for preventing concurrent workspace usage (P2.4).

Prevents multiple executors from using the same physical workspace directory
concurrently. This is orthogonal to per-run ExecutorLockManager - a workspace
can host multiple runs sequentially, but only one executor should access it
at a time to avoid git state corruption.

Safety properties:
- Global lock keyed by absolute workspace path
- Prevents concurrent git operations in same working tree
- Works alongside per-run ExecutorLockManager
- Automatic cleanup on context exit

Example:
    >>> with WorkspaceLease("/path/to/workspace") as lease:
    ...     # Safe to execute git operations
    ...     execute_run(lease.workspace_path)
"""

import os
import socket
import logging
from pathlib import Path
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)


class WorkspaceLease:
    """Ensures only one executor accesses a workspace at a time."""

    def __init__(self, workspace_path: Path, lease_dir: Optional[Path] = None, timeout: int = 5):
        """Initialize workspace lease manager.

        Args:
            workspace_path: Absolute path to workspace directory
            lease_dir: Directory for lease lock files (default: {autonomous_runs_dir}/.workspace_leases)
            timeout: Lock acquisition timeout in seconds (not currently used)
        """
        self.workspace_path = Path(workspace_path).resolve()
        self.timeout = timeout

        # Determine lease directory
        if lease_dir is not None:
            self.lease_dir = lease_dir
        else:
            self.lease_dir = Path(settings.autonomous_runs_dir) / ".workspace_leases"

        # Create lease directory if needed
        self.lease_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique lock file name from absolute workspace path
        # Use hash to handle long paths and special characters
        import hashlib

        path_hash = hashlib.sha256(str(self.workspace_path).encode()).hexdigest()[:16]
        self.lock_file_path = self.lease_dir / f"workspace_{path_hash}.lock"

        self.lock_file = None

        # Current process info for debugging
        self.pid = os.getpid()
        self.hostname = socket.gethostname()
        self.executor_id = f"{self.pid}@{self.hostname}"

    def acquire(self) -> bool:
        """Acquire exclusive lease for this workspace.

        Returns:
            True if lease acquired successfully, False if another executor holds it

        Raises:
            RuntimeError: If lease operation fails unexpectedly
        """
        try:
            # Open lock file for writing
            self.lock_file = open(self.lock_file_path, "w")

            # Write current executor info for debugging
            self.lock_file.write(f"{self.executor_id}\n")
            self.lock_file.write(f"{self.workspace_path}\n")
            self.lock_file.write(f"{os.getcwd()}\n")
            self.lock_file.flush()

            # Try to acquire exclusive lock (non-blocking)
            if os.name == "nt":  # Windows
                import msvcrt

                try:
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    logger.info(
                        f"[WorkspaceLease] Acquired lease for workspace={self.workspace_path} "
                        f"(PID={self.pid}, host={self.hostname})"
                    )
                    return True
                except OSError:
                    # Lock already held
                    self._log_existing_lease()
                    self.lock_file.close()
                    self.lock_file = None
                    return False
            else:  # Unix/Linux/Mac
                import fcntl

                try:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    logger.info(
                        f"[WorkspaceLease] Acquired lease for workspace={self.workspace_path} "
                        f"(PID={self.pid}, host={self.hostname})"
                    )
                    return True
                except (IOError, OSError):
                    # Lock already held
                    self._log_existing_lease()
                    self.lock_file.close()
                    self.lock_file = None
                    return False

        except Exception as e:
            logger.error(f"[WorkspaceLease] Unexpected error acquiring lease: {e}")
            if self.lock_file:
                self.lock_file.close()
                self.lock_file = None
            raise RuntimeError(f"Failed to acquire workspace lease: {e}")

    def _log_existing_lease(self):
        """Log information about the existing lease holder."""
        try:
            # Read lock file to get existing executor info
            with open(self.lock_file_path, "r") as f:
                lines = f.readlines()
                existing_executor = lines[0].strip() if len(lines) > 0 else "unknown"
                existing_workspace = lines[1].strip() if len(lines) > 1 else "unknown"

            logger.error(
                f"[WorkspaceLease] Another executor is already using this workspace\n"
                f"  Workspace path: {self.workspace_path}\n"
                f"  Existing executor: {existing_executor}\n"
                f"  Existing workspace: {existing_workspace}\n"
                f"  Current executor: {self.executor_id}\n"
                f"  Lock file: {self.lock_file_path}\n"
                f"\n"
                f"  To force unlock (if executor crashed):\n"
                f"    rm {self.lock_file_path}\n"
                f"\n"
                f"  Exiting to prevent workspace corruption."
            )
        except Exception as e:
            logger.error(
                f"[WorkspaceLease] Another executor is already using workspace={self.workspace_path} "
                f"(could not read lock file: {e})"
            )

    def release(self):
        """Release the workspace lease."""
        if not self.lock_file:
            return

        try:
            # Release file lock
            if os.name == "nt":  # Windows
                import msvcrt

                try:
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass  # Lock may already be released
            else:  # Unix
                import fcntl

                try:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                except (IOError, OSError):
                    pass  # Lock may already be released

            # Close and delete lock file
            self.lock_file.close()
            self.lock_file = None

            # Remove lock file
            try:
                self.lock_file_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"[WorkspaceLease] Could not delete lock file: {e}")

            logger.info(
                f"[WorkspaceLease] Released lease for workspace={self.workspace_path} "
                f"(PID={self.pid})"
            )

        except Exception as e:
            logger.warning(f"[WorkspaceLease] Error releasing lease: {e}")

    def __enter__(self):
        """Context manager entry - acquire lease or raise."""
        if not self.acquire():
            raise RuntimeError(
                f"Workspace lease already held for {self.workspace_path}. "
                f"Another executor is using this workspace. Exiting to prevent corruption."
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release lease."""
        self.release()
        return False  # Don't suppress exceptions

    def is_locked(self) -> bool:
        """Check if a lease exists for this workspace (without acquiring).

        Returns:
            True if lock file exists, False otherwise

        Note: This is a heuristic check - the lock file may be stale if
        the executor crashed without cleanup.
        """
        return self.lock_file_path.exists()

    def force_unlock(self) -> bool:
        """Force remove the lease lock file (use with caution).

        This should only be used if you're certain the previous executor
        crashed and left a stale lock.

        Returns:
            True if lock file was removed, False if it didn't exist
        """
        if self.lock_file_path.exists():
            try:
                self.lock_file_path.unlink()
                logger.warning(
                    f"[WorkspaceLease] Force-unlocked workspace={self.workspace_path} "
                    f"(removed stale lock file)"
                )
                return True
            except Exception as e:
                logger.error(f"[WorkspaceLease] Failed to force-unlock: {e}")
                raise
        return False
