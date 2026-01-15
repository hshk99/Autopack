"""
Disk scanner for analyzing storage usage.

MVP implementation uses Python os.walk for scanning.
Future versions can integrate WizTree for faster scanning.
"""

import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional
import shutil

from .models import ScanResult


class StorageScanner:
    """
    Scans directories to analyze disk usage.

    Uses Python's os.walk for cross-platform scanning.
    For MVP, focuses on specific high-value directories rather than full disk scans.
    """

    def __init__(self, max_depth: int = 3, exclude_dirs: Optional[List[str]] = None):
        """
        Initialize scanner.

        Args:
            max_depth: Maximum directory depth to scan (default: 3)
            exclude_dirs: Directory names to skip (e.g., .git, node_modules during scan)
        """
        self.max_depth = max_depth
        self.exclude_dirs = exclude_dirs or [".git", "__pycache__", ".pytest_cache"]

    def get_disk_usage(self, drive_letter: str = "C") -> tuple:
        """
        Get total, used, and free disk space.

        Args:
            drive_letter: Drive letter to check (default: C)

        Returns:
            Tuple of (total_bytes, used_bytes, free_bytes)
        """
        drive_path = f"{drive_letter}:\\" if len(drive_letter) == 1 else drive_letter

        try:
            usage = shutil.disk_usage(drive_path)
            return (usage.total, usage.used, usage.free)
        except Exception as e:
            print(f"Warning: Could not get disk usage for {drive_path}: {e}")
            return (0, 0, 0)

    def scan_directory(self, directory: str, max_items: int = 10000) -> List[ScanResult]:
        """
        Scan a specific directory and return results.

        Uses single-pass traversal with accumulated directory sizes to avoid O(n²)
        complexity. Directory sizes are calculated during traversal accumulation
        instead of via redundant traversals.

        Args:
            directory: Directory path to scan
            max_items: Maximum number of items to return (to avoid memory issues)

        Returns:
            List of ScanResult objects
        """
        results: list[ScanResult] = []
        scanned_count = 0
        directory_norm = os.path.normpath(directory)

        # Cache to store accumulated sizes for each directory path.
        #
        # IMPORTANT: This mirrors the prior `_get_directory_size(dir, max_depth=2)`
        # behavior: include files in the directory itself and its immediate child
        # directories (one level down). We achieve this by adding each file size
        # to its containing directory and one parent directory.
        dir_sizes: dict[str, int] = {}

        # Directory ScanResults are created when discovered so we preserve the
        # original "directories first, then files per os.walk root" behavior.
        dir_results_by_path: dict[str, ScanResult] = {}

        dir_path = Path(directory)
        if not dir_path.exists():
            print(f"Warning: Directory does not exist: {directory}")
            return results

        try:
            # Single traversal:
            # - Walk down to `self.max_depth` (inclusive) for sizing accumulation.
            # - Only EMIT results (dirs/files) for depths < self.max_depth (matching
            #   prior behavior where depth >= self.max_depth caused a continue).
            for root, dirs, files in os.walk(directory_norm):
                root_norm = os.path.normpath(root)
                depth = root_norm[len(directory_norm) :].count(os.sep)

                # Exclude certain directories (applies to traversal and output)
                dirs[:] = [d for d in dirs if d not in self.exclude_dirs]

                # Stop recursion beyond the depth needed for directory sizing.
                if depth > self.max_depth:
                    dirs[:] = []
                    continue

                # At the sizing boundary: include files for accumulation but don't
                # recurse further, and don't emit results at this depth.
                emit_results = depth < self.max_depth
                if depth == self.max_depth:
                    dirs[:] = []

                # Accumulate file sizes for directory sizing (depth-limited to mimic
                # `_get_directory_size(..., max_depth=2)`).
                for file_name in files:
                    file_path = os.path.join(root_norm, file_name)
                    try:
                        file_size = os.path.getsize(file_path)
                    except (OSError, PermissionError):
                        continue

                    dir_sizes[root_norm] = dir_sizes.get(root_norm, 0) + file_size
                    parent = os.path.dirname(root_norm)
                    if parent and parent.startswith(directory_norm):
                        dir_sizes[parent] = dir_sizes.get(parent, 0) + file_size

                    if not emit_results:
                        continue

                    if scanned_count >= max_items:
                        break

                    try:
                        stat = os.stat(file_path)
                    except (OSError, PermissionError):
                        continue

                    results.append(
                        ScanResult(
                            path=file_path,
                            size_bytes=stat.st_size,
                            modified=datetime.fromtimestamp(stat.st_mtime),
                            is_folder=False,
                            attributes="-",
                        )
                    )
                    scanned_count += 1

                if not emit_results:
                    continue

                # Emit directories (placeholder size, filled from cache post-traversal)
                for dir_name in dirs:
                    if scanned_count >= max_items:
                        break

                    dir_full_path = os.path.normpath(os.path.join(root_norm, dir_name))
                    try:
                        stat = os.stat(dir_full_path)
                    except (OSError, PermissionError):
                        continue

                    sr = ScanResult(
                        path=dir_full_path,
                        size_bytes=0,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                        is_folder=True,
                        attributes="d",
                    )
                    dir_results_by_path[dir_full_path] = sr
                    results.append(sr)
                    scanned_count += 1

                if scanned_count >= max_items:
                    break

            # Fill in directory sizes from the accumulated cache.
            for dir_path_str, sr in dir_results_by_path.items():
                sr.size_bytes = dir_sizes.get(dir_path_str, 0)

        except Exception as e:
            print(f"Error scanning directory {directory}: {e}")

        return results

    def scan_drive(
        self,
        drive_letter: str,
        max_depth: Optional[int] = None,
        max_items: int = 10000,
        admin_mode: bool = False,
    ) -> List[ScanResult]:
        """
        Scan an entire drive starting from its root.

        Wraps scan_directory for drive root paths. Handles both Windows drive
        letters (C, D, etc.) and Unix-style roots (/).

        Args:
            drive_letter: Drive letter (e.g., "C") or Unix root ("/")
            max_depth: Maximum directory depth (overrides instance max_depth if provided)
            max_items: Maximum items to return (default: 10000)
            admin_mode: Ignored for Python scanner (included for API compatibility)

        Returns:
            List of ScanResult objects from the drive scan
        """
        # Handle Unix root path
        if drive_letter == "/" or drive_letter == "":
            drive_path = "/"
        # Handle Windows drive letter (single letter or with colon/backslash)
        elif len(drive_letter) == 1 and drive_letter.isalpha():
            drive_path = f"{drive_letter.upper()}:\\"
        elif drive_letter.endswith(":\\") or drive_letter.endswith(":/"):
            drive_path = drive_letter
        elif drive_letter.endswith(":"):
            drive_path = f"{drive_letter}\\"
        else:
            # Assume it's already a valid path
            drive_path = drive_letter

        # Temporarily override max_depth if provided
        original_max_depth = self.max_depth
        if max_depth is not None:
            self.max_depth = max_depth

        try:
            results = self.scan_directory(drive_path, max_items=max_items)
        finally:
            # Restore original max_depth
            self.max_depth = original_max_depth

        return results

    def scan_high_value_directories(
        self, drive_letter: str = "C", max_items: int = 10000
    ) -> List[ScanResult]:
        """
        Scan specific high-value directories known to accumulate large files.

        Instead of scanning entire drive (slow), focus on:
        - User's temp folder
        - Downloads
        - AppData (for dev caches)
        - Common development directories

        Args:
            drive_letter: Drive letter to scan
            max_items: Maximum number of items to return (to avoid memory issues)

        Returns:
            Combined list of ScanResult objects from all scanned directories
        """
        results = []
        total_scanned = 0

        # Determine user home directory
        user_home = Path.home()

        # High-value directories to scan
        target_dirs = [
            user_home / "AppData" / "Local" / "Temp",
            user_home / "Downloads",
            user_home / "AppData" / "Local" / "Microsoft" / "Edge",
            user_home / "AppData" / "Local" / "Google" / "Chrome",
            user_home / "AppData" / "Roaming" / "npm-cache",
        ]

        # Add common development directories if they exist
        common_dev_dirs = [
            Path(f"{drive_letter}:/dev"),
            Path(f"{drive_letter}:/projects"),
            user_home / "dev",
            user_home / "projects",
        ]

        for dev_dir in common_dev_dirs:
            if dev_dir.exists():
                target_dirs.append(dev_dir)

        # Scan each directory
        for target_dir in target_dirs:
            if total_scanned >= max_items:
                break
            if target_dir.exists():
                print(f"Scanning: {target_dir}")
                remaining = max_items - total_scanned
                dir_results = self.scan_directory(str(target_dir), max_items=remaining)
                results.extend(dir_results)
                total_scanned += len(dir_results)
            else:
                print(f"Skipping (not found): {target_dir}")

        return results

    def _get_directory_size(self, directory: str, max_depth: int = 2) -> int:
        """
        Calculate total size of a directory (with depth limit to avoid long operations).

        Args:
            directory: Directory path
            max_depth: Maximum depth to traverse

        Returns:
            Total size in bytes
        """
        total_size = 0
        try:
            for root, dirs, files in os.walk(directory):
                depth = root[len(directory) :].count(os.sep)
                if depth >= max_depth:
                    dirs[:] = []
                    continue

                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(file_path)
                    except (OSError, PermissionError):
                        continue
        except Exception:
            pass

        return total_size

    def get_top_consumers(self, results: List[ScanResult], top_n: int = 20) -> List[ScanResult]:
        """
        Get top N largest files/folders from scan results.

        Args:
            results: List of ScanResult objects
            top_n: Number of top consumers to return

        Returns:
            List of top N largest ScanResult objects
        """
        sorted_results = sorted(results, key=lambda x: x.size_bytes, reverse=True)
        return sorted_results[:top_n]


# ==============================================================================
# Scanner Factory (BUILD-150 Phase 3)
# ==============================================================================


def create_scanner(prefer_wiztree: bool = True):
    """
    Factory to create optimal scanner based on availability.

    Args:
        prefer_wiztree: Try WizTree first if available (default: True)

    Returns:
        WizTreeScanner if available and preferred, else StorageScanner

    Example:
        >>> scanner = create_scanner(prefer_wiztree=True)
        >>> results = scanner.scan_drive("C", max_depth=3, max_items=1000)
    """
    if prefer_wiztree:
        try:
            from .wiztree_scanner import WizTreeScanner

            scanner = WizTreeScanner()
            if scanner.is_available():
                return scanner
        except ImportError:
            pass  # WizTree scanner not available

    return StorageScanner()
