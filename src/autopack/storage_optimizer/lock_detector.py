"""
Lock detector for Windows file lock classification (BUILD-152).

Detects and classifies Windows file locks to enable:
- Intelligent retry logic (retry transient locks, skip permanent)
- User-friendly remediation guidance
- Lock type tracking in checkpoint logs

Common lock types:
- searchindexer: Windows Search indexing (transient, retry)
- antivirus: Defender/antivirus scanning (transient, retry)
- handle: File open in another process (transient, retry)
- permission: Insufficient permissions (permanent, skip)
- path_too_long: Path exceeds Windows MAX_PATH (permanent, skip)
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LockDetector:
    """
    Detects and classifies Windows file locks for retry decision-making.

    Uses exception message pattern matching to categorize lock types.
    Future enhancement: Use psutil to identify locking processes.

    Example:
        ```python
        detector = LockDetector()
        try:
            send2trash.send2trash(path)
        except Exception as e:
            lock_type = detector.detect_lock_type(path, e)
            if detector.is_transient_lock(lock_type):
                print("Retrying...")
            else:
                hint = detector.get_remediation_hint(lock_type)
                print(f"Skipping: {hint}")
        ```
    """

    def __init__(self):
        """Initialize lock detector."""
        # Pattern mapping for lock type detection
        self.lock_patterns = {
            "searchindexer": [
                "searchindexer",
                "windows search",
                "search indexer",
                "indexing service",
            ],
            "antivirus": ["virus", "defender", "malware", "threat", "security", "quarantine"],
            "handle": [
                "being used by another process",
                "process cannot access the file",
                "file is in use",
                "cannot access",
                "sharing violation",
            ],
            "permission": [
                "access is denied",
                "permission denied",
                "insufficient privileges",
                "you do not have permission",
                "unauthorized access",
            ],
            "path_too_long": [
                "path too long",
                "file name too long",
                "path length exceeds",
                "exceeds maximum path",
            ],
        }

        # Remediation hints for each lock type
        self.remediation_hints = {
            "searchindexer": (
                "Windows Search is indexing this file. "
                "Options: (1) Wait 30-60s and retry, "
                "(2) Disable indexing for this folder, "
                "(3) Run: resmon.exe → CPU → Associated Handles to verify"
            ),
            "antivirus": (
                "Antivirus/Windows Defender is scanning this file. "
                "Options: (1) Wait 5-15 minutes for scan to complete, "
                "(2) Add folder to antivirus exclusions temporarily, "
                "(3) Retry after scan completes"
            ),
            "handle": (
                "File is open in another process. "
                "Options: (1) Close the application using this file, "
                "(2) Use Resource Monitor (resmon.exe): CPU → Associated Handles, "
                "(3) Advanced: Use Sysinternals handle.exe to identify process"
            ),
            "permission": (
                "Insufficient permissions. "
                "Options: (1) Run PowerShell/CLI as Administrator, "
                "(2) Check folder ownership: icacls <path>, "
                "(3) Ensure you have write access to parent directory"
            ),
            "path_too_long": (
                "Path exceeds Windows MAX_PATH (260 chars). "
                "Options: (1) Move to shorter path, "
                "(2) Use robocopy to delete, "
                "(3) Enable long path support: Computer\\HKLM\\SYSTEM\\CurrentControlSet\\Control\\FileSystem\\LongPathsEnabled"
            ),
            "unknown": (
                "Unknown lock type. "
                "Options: (1) Check for open handles with resmon.exe, "
                "(2) Verify file/folder permissions, "
                "(3) Retry after closing applications"
            ),
        }

        # Transient locks that should be retried
        self.transient_locks = {"searchindexer", "antivirus", "handle"}

    def detect_lock_type(self, path: Path, error: Exception) -> str:
        """
        Detect lock type from exception details.

        Args:
            path: Path that failed to delete
            error: Exception that occurred during deletion

        Returns:
            Lock type string: 'searchindexer' | 'antivirus' | 'handle' |
                             'permission' | 'path_too_long' | 'unknown'

        Algorithm:
            1. Convert exception message to lowercase
            2. Pattern match against known lock types
            3. Return first match or 'unknown'
        """
        error_msg = str(error).lower()

        # Check each lock type pattern
        for lock_type, patterns in self.lock_patterns.items():
            for pattern in patterns:
                if pattern in error_msg:
                    logger.debug(f"Detected {lock_type} lock for {path}: pattern='{pattern}'")
                    return lock_type

        # No match found
        logger.debug(f"Unknown lock type for {path}: {error_msg[:100]}")
        return "unknown"

    def is_transient_lock(self, lock_type: str) -> bool:
        """
        Check if lock type is transient (should retry).

        Transient locks are temporary and may release after a short delay.
        Permanent locks require manual intervention.

        Args:
            lock_type: Lock type string from detect_lock_type()

        Returns:
            True if lock is transient (retry), False if permanent (skip)

        Transient locks (retry):
            - searchindexer: Windows Search releases lock after indexing
            - antivirus: Scanner releases lock after scan
            - handle: User may close application

        Permanent locks (skip):
            - permission: Requires privilege escalation
            - path_too_long: Requires path restructuring
            - unknown: Conservative approach (don't retry unknown)
        """
        is_transient = lock_type in self.transient_locks
        logger.debug(
            f"Lock type '{lock_type}' is {'transient (retry)' if is_transient else 'permanent (skip)'}"
        )
        return is_transient

    def get_remediation_hint(self, lock_type: str) -> str:
        """
        Get user-friendly remediation guidance for lock type.

        Args:
            lock_type: Lock type string from detect_lock_type()

        Returns:
            Human-readable remediation hint with actionable steps

        Example:
            >>> detector.get_remediation_hint("searchindexer")
            "Windows Search is indexing this file. Options: (1) Wait 30-60s..."
        """
        hint = self.remediation_hints.get(lock_type, self.remediation_hints["unknown"])
        return hint

    def get_recommended_retry_count(self, lock_type: str) -> int:
        """
        Get recommended retry count for lock type.

        Different lock types have different retry strategies:
        - searchindexer: 3 retries (usually releases within 10-20s)
        - antivirus: 2 retries (scan may take several minutes)
        - handle: 3 retries (user may close app quickly)
        - permission/path_too_long/unknown: 0 retries (permanent)

        Args:
            lock_type: Lock type string from detect_lock_type()

        Returns:
            Recommended number of retry attempts (0 = don't retry)
        """
        retry_counts = {
            "searchindexer": 3,
            "antivirus": 2,
            "handle": 3,
            "permission": 0,
            "path_too_long": 0,
            "unknown": 0,
        }
        return retry_counts.get(lock_type, 0)

    def get_backoff_seconds(self, lock_type: str, retry_attempt: int) -> int:
        """
        Get backoff delay in seconds for retry attempt.

        Uses lock-type-specific backoff strategies:
        - searchindexer: [2, 5, 10] seconds (short delays)
        - antivirus: [10, 30, 60] seconds (longer delays for scanning)
        - handle: [2, 5, 10] seconds (short delays)
        - Other: Default [2, 5, 10] seconds

        Args:
            lock_type: Lock type string from detect_lock_type()
            retry_attempt: Current retry attempt (0-indexed)

        Returns:
            Backoff delay in seconds for this retry attempt

        Example:
            >>> detector.get_backoff_seconds("antivirus", 0)
            10  # First retry after 10 seconds
            >>> detector.get_backoff_seconds("antivirus", 1)
            30  # Second retry after 30 seconds
        """
        backoff_strategies = {
            "searchindexer": [2, 5, 10],
            "antivirus": [10, 30, 60],
            "handle": [2, 5, 10],
        }

        default_backoff = [2, 5, 10]
        backoff = backoff_strategies.get(lock_type, default_backoff)

        # Return backoff for this attempt, or last value if out of range
        if retry_attempt < len(backoff):
            return backoff[retry_attempt]
        else:
            return backoff[-1]


# ==============================================================================
# Advanced Lock Detection (Optional - psutil-based)
# ==============================================================================


def find_locking_process(path: Path) -> Optional[str]:
    """
    Find the process holding a lock on a file (requires psutil).

    This is an OPTIONAL enhancement for more detailed lock detection.
    Not required for BUILD-152 MVP.

    Args:
        path: Path to check for locks

    Returns:
        Process name if found, None if psutil unavailable or no lock detected

    Example:
        >>> find_locking_process(Path("C:/temp/file.log"))
        "SearchIndexer.exe"
    """
    try:
        import psutil

        # Normalize path for comparison
        target_path = str(path.resolve()).lower()

        # Check all processes
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                # Get open files for this process
                for file in proc.open_files():
                    if file.path.lower() == target_path:
                        logger.info(
                            f"Found locking process: {proc.info['name']} (PID: {proc.info['pid']})"
                        )
                        return proc.info["name"]
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue  # Skip processes we can't access

        return None

    except ImportError:
        logger.debug("psutil not available for advanced lock detection")
        return None
    except Exception as e:
        logger.warning(f"Failed to find locking process: {e}")
        return None
