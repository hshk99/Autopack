"""Executor instance locking to prevent duplicate executors per run-id.

BUILD-048-T1: Process-Level Locking
Prevents multiple executor instances from running concurrently for the same run-id.
"""

import os
import platform
import socket
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ExecutorLockManager:
    """Ensures only one executor runs per run-id using file-based locking.

    Uses platform-appropriate file locking (fcntl on Unix, msvcrt on Windows)
    to prevent multiple executor processes from executing the same run.

    Example:
        >>> lock = ExecutorLockManager("my-run-id")
        >>> if lock.acquire():
        ...     try:
        ...         # Execute run
        ...         pass
        ...     finally:
        ...         lock.release()
        >>>
        >>> # Or use context manager
        >>> with ExecutorLockManager("my-run-id"):
        ...     # Execute run
        ...     pass
    """

    def __init__(self, run_id: str, lock_dir: Optional[Path] = None, timeout: int = 5):
        """Initialize the lock manager.

        Args:
            run_id: Run ID to lock (one lock per run-id)
            lock_dir: Directory for lock files. Defaults to {autonomous_runs_dir}/.locks
            timeout: Lock acquisition timeout in seconds (not currently used)
        """
        from .config import settings

        self.run_id = run_id

        # P2.2: Respect settings.autonomous_runs_dir for parallel-run safety
        if lock_dir is not None:
            self.lock_dir = lock_dir
        else:
            # Use configured runs directory instead of hardcoded path
            self.lock_dir = Path(settings.autonomous_runs_dir) / ".locks"

        self.timeout = timeout

        # Create lock directory if it doesn't exist
        self.lock_dir.mkdir(parents=True, exist_ok=True)

        # Lock file path
        self.lock_file_path = self.lock_dir / f"{run_id}.lock"
        self._lock_fd = None

        # Current process info for debugging
        self.pid = os.getpid()
        self.hostname = socket.gethostname()
        self.executor_id = f"{self.pid}@{self.hostname}"

    def acquire(self) -> bool:
        """Acquire exclusive lock for this run-id.

        Returns:
            True if lock acquired successfully, False if another executor holds it

        Raises:
            RuntimeError: If lock file operation fails unexpectedly
        """
        try:
            # Open lock file for writing using os.open to get fd directly
            self._lock_fd = os.open(self.lock_file_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)

            # Write current executor info for debugging
            debug_info = (
                f"{self.executor_id}\n" f"{os.getcwd()}\n" f"{os.getenv('PYTHONPATH', 'N/A')}\n"
            )
            os.write(self._lock_fd, debug_info.encode())

            # Try to acquire exclusive lock (non-blocking)
            if platform.system() == "Windows":
                import msvcrt

                try:
                    # Lock first byte of file (exclusive, non-blocking)
                    msvcrt.locking(self._lock_fd, msvcrt.LK_NBLCK, 1)
                    logger.info(
                        f"[LOCK] Acquired executor lock for run_id={self.run_id} "
                        f"(PID={self.pid}, host={self.hostname})"
                    )
                    return True
                except OSError:
                    # Lock already held
                    self._log_existing_lock()
                    os.close(self._lock_fd)
                    self._lock_fd = None
                    return False
            else:  # Unix/Linux/Mac
                import fcntl

                try:
                    # Acquire exclusive lock (non-blocking)
                    fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    logger.info(
                        f"[LOCK] Acquired executor lock for run_id={self.run_id} "
                        f"(PID={self.pid}, host={self.hostname})"
                    )
                    return True
                except (IOError, OSError):
                    # Lock already held
                    self._log_existing_lock()
                    os.close(self._lock_fd)
                    self._lock_fd = None
                    return False

        except Exception as e:
            logger.error(f"[LOCK] Unexpected error acquiring lock: {e}")
            if self._lock_fd is not None:
                try:
                    os.close(self._lock_fd)
                finally:
                    self._lock_fd = None
            raise RuntimeError(f"Failed to acquire executor lock: {e}")

    def _log_existing_lock(self):
        """Log information about the existing lock holder."""
        try:
            # Read lock file to get existing executor info
            with open(self.lock_file_path, "r") as f:
                lines = f.readlines()
                existing_executor = lines[0].strip() if len(lines) > 0 else "unknown"
                existing_cwd = lines[1].strip() if len(lines) > 1 else "unknown"

            logger.error(
                f"[LOCK] Another executor is already running for run_id={self.run_id}\n"
                f"  Existing executor: {existing_executor}\n"
                f"  Working directory: {existing_cwd}\n"
                f"  Current executor: {self.executor_id}\n"
                f"  Lock file: {self.lock_file_path}\n"
                f"\n"
                f"  To force unlock (if executor crashed):\n"
                f"    rm {self.lock_file_path}\n"
                f"\n"
                f"  Exiting to prevent duplicate work."
            )
        except Exception as e:
            logger.error(
                f"[LOCK] Another executor is already running for run_id={self.run_id} "
                f"(could not read lock file: {e})"
            )

    def release(self):
        """Release the lock."""
        if self._lock_fd is None:
            return

        try:
            # Release file lock
            if platform.system() == "Windows":
                import msvcrt

                try:
                    msvcrt.locking(self._lock_fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass  # Lock may already be released
            else:  # Unix
                import fcntl

                try:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                except (IOError, OSError):
                    pass  # Lock may already be released

            # Close file descriptor
            try:
                os.close(self._lock_fd)
            finally:
                self._lock_fd = None

            # Remove lock file
            try:
                self.lock_file_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"[LOCK] Could not delete lock file: {e}")

            logger.info(f"[LOCK] Released executor lock for run_id={self.run_id} (PID={self.pid})")

        except Exception as e:
            logger.warning(f"[LOCK] Error releasing lock: {e}")

    def __enter__(self):
        """Context manager entry - acquire lock or raise."""
        if not self.acquire():
            raise RuntimeError(
                f"Executor lock already held for run_id={self.run_id}. "
                f"Another executor is running. Exiting to prevent duplicate work."
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release lock."""
        self.release()
        return False  # Don't suppress exceptions

    def is_locked(self) -> bool:
        """Check if a lock exists for this run-id (without acquiring).

        Returns:
            True if lock file exists, False otherwise

        Note: This is a heuristic check - the lock file may be stale if
        the executor crashed without cleanup.
        """
        return self.lock_file_path.exists()

    def force_unlock(self) -> bool:
        """Force remove the lock file (use with caution).

        This should only be used if you're certain the previous executor
        crashed and left a stale lock.

        Returns:
            True if lock file was removed, False if it didn't exist
        """
        if self.lock_file_path.exists():
            try:
                self.lock_file_path.unlink()
                logger.warning(
                    f"[LOCK] Force-unlocked run_id={self.run_id} (removed stale lock file)"
                )
                return True
            except Exception as e:
                logger.error(f"[LOCK] Failed to force-unlock: {e}")
                raise
        return False
