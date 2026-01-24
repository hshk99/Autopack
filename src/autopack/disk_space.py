"""Disk space checking utilities for artifact writes.

IMP-SAFETY-007: Add disk space check before artifact writes to prevent disk exhaustion.
"""

import logging
import shutil
from pathlib import Path
from typing import Union

from .config import settings
from .exceptions import DiskSpaceError

logger = logging.getLogger(__name__)


def check_disk_space(
    path: Union[str, Path],
    required_bytes: int = 0,
    min_free_bytes: int = None,
) -> bool:
    """Check if sufficient disk space is available.

    Args:
        path: Path where the write will occur (used to determine the disk)
        required_bytes: Additional bytes needed for the operation
        min_free_bytes: Minimum free bytes required. If None, uses config setting.

    Returns:
        True if sufficient space is available, False otherwise.
    """
    if min_free_bytes is None:
        min_free_bytes = settings.min_disk_space_bytes

    try:
        # Resolve to absolute path and get the parent directory if it's a file
        path = Path(path).resolve()
        check_path = path if path.is_dir() else path.parent

        # If parent doesn't exist, walk up to find an existing directory
        while not check_path.exists() and check_path.parent != check_path:
            check_path = check_path.parent

        if not check_path.exists():
            # Can't determine disk space, proceed with caution
            logger.warning(f"Cannot determine disk space for path: {path}")
            return True

        usage = shutil.disk_usage(check_path)
        total_required = min_free_bytes + required_bytes

        if usage.free >= total_required:
            return True

        logger.warning(
            f"Insufficient disk space: {usage.free:,} bytes available, "
            f"{total_required:,} bytes required (min_free={min_free_bytes:,}, "
            f"write_size={required_bytes:,})"
        )
        return False

    except OSError as e:
        # If we can't check disk space, log warning and proceed
        logger.warning(f"Failed to check disk space for {path}: {e}")
        return True


def ensure_disk_space(
    path: Union[str, Path],
    required_bytes: int = 0,
    min_free_bytes: int = None,
) -> None:
    """Ensure sufficient disk space is available, raising an error if not.

    Args:
        path: Path where the write will occur (used to determine the disk)
        required_bytes: Additional bytes needed for the operation
        min_free_bytes: Minimum free bytes required. If None, uses config setting.

    Raises:
        DiskSpaceError: If insufficient disk space is available.
    """
    if min_free_bytes is None:
        min_free_bytes = settings.min_disk_space_bytes

    try:
        path = Path(path).resolve()
        check_path = path if path.is_dir() else path.parent

        # Walk up to find an existing directory
        while not check_path.exists() and check_path.parent != check_path:
            check_path = check_path.parent

        if not check_path.exists():
            logger.warning(f"Cannot determine disk space for path: {path}")
            return

        usage = shutil.disk_usage(check_path)
        total_required = min_free_bytes + required_bytes

        if usage.free < total_required:
            raise DiskSpaceError(
                f"Insufficient disk space: {usage.free:,} bytes available, "
                f"{total_required:,} bytes required",
                required_bytes=total_required,
                available_bytes=usage.free,
                path=str(path),
            )

    except DiskSpaceError:
        raise
    except OSError as e:
        logger.warning(f"Failed to check disk space for {path}: {e}")


def get_available_disk_space(path: Union[str, Path]) -> int:
    """Get available disk space in bytes.

    Args:
        path: Path to check (uses the disk containing this path)

    Returns:
        Available bytes, or -1 if unable to determine.
    """
    try:
        path = Path(path).resolve()
        check_path = path if path.is_dir() else path.parent

        while not check_path.exists() and check_path.parent != check_path:
            check_path = check_path.parent

        if not check_path.exists():
            return -1

        usage = shutil.disk_usage(check_path)
        return usage.free

    except OSError:
        return -1
