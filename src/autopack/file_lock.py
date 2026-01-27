"""Common file locking logic for cross-platform support.

Provides a unified file-locking interface that works across Windows, Linux, and macOS
using platform-appropriate primitives (msvcrt on Windows, fcntl on Unix).
"""

import logging
import os
import platform
from typing import Optional

logger = logging.getLogger(__name__)


class FileLock:
    """Cross-platform file lock using OS-level primitives.

    Provides a simple acquire/release interface for file-based locking that works
    on both Windows (msvcrt) and Unix-like systems (fcntl). Supports context manager
    usage for automatic cleanup.

    Example:
        >>> lock = FileLock("/path/to/lock.lock")
        >>> lock.acquire()
        >>> try:
        ...     # Protected region
        ...     pass
        ... finally:
        ...     lock.release()
        >>>
        >>> # Or use context manager
        >>> with FileLock("/path/to/lock.lock"):
        ...     # Protected region
        ...     pass
    """

    def __init__(self, lock_path: str):
        """Initialize file lock.

        Args:
            lock_path: Path to the lock file
        """
        self.lock_path = lock_path
        self._lock_fd: Optional[int] = None

    def acquire(self):
        """Acquire file lock.

        Raises:
            RuntimeError: If lock operation fails unexpectedly
        """
        try:
            # Open lock file for writing using os.open to get file descriptor directly
            self._lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)

            # Try to acquire exclusive lock (non-blocking)
            if platform.system() == "Windows":
                import msvcrt

                try:
                    msvcrt.locking(self._lock_fd, msvcrt.LK_NBLCK, 1)
                except OSError:
                    # Lock already held
                    os.close(self._lock_fd)
                    self._lock_fd = None
                    raise
            else:  # Unix/Linux/Mac
                import fcntl

                try:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (IOError, OSError):
                    # Lock already held
                    os.close(self._lock_fd)
                    self._lock_fd = None
                    raise

        except Exception as e:
            logger.error(f"Failed to acquire file lock {self.lock_path}: {e}")
            if self._lock_fd is not None:
                try:
                    os.close(self._lock_fd)
                finally:
                    self._lock_fd = None
            raise RuntimeError(f"Failed to acquire file lock: {e}") from e

    def release(self):
        """Release file lock.

        Safely releases the file lock, closes the file descriptor, and removes
        the lock file. Safe to call even if lock was never acquired.
        """
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
                os.unlink(self.lock_path)
            except Exception as e:
                logger.warning(f"Could not delete lock file {self.lock_path}: {e}")

        except Exception as e:
            logger.warning(f"Error releasing file lock {self.lock_path}: {e}")

    def __enter__(self):
        """Context manager entry - acquire lock.

        Returns:
            self for use in 'with' statement
        """
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release lock."""
        self.release()
        return False  # Don't suppress exceptions
