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

        Args:
            directory: Directory path to scan
            max_items: Maximum number of items to return (to avoid memory issues)

        Returns:
            List of ScanResult objects
        """
        results = []
        scanned_count = 0

        dir_path = Path(directory)
        if not dir_path.exists():
            print(f"Warning: Directory does not exist: {directory}")
            return results

        try:
            for root, dirs, files in os.walk(directory):
                # Enforce max depth
                depth = root[len(directory) :].count(os.sep)
                if depth >= self.max_depth:
                    dirs[:] = []  # Don't recurse deeper
                    continue

                # Exclude certain directories
                dirs[:] = [d for d in dirs if d not in self.exclude_dirs]

                # Scan directories
                for dir_name in dirs:
                    if scanned_count >= max_items:
                        break

                    dir_full_path = os.path.join(root, dir_name)
                    try:
                        stat = os.stat(dir_full_path)
                        size = self._get_directory_size(dir_full_path)

                        results.append(
                            ScanResult(
                                path=dir_full_path,
                                size_bytes=size,
                                modified=datetime.fromtimestamp(stat.st_mtime),
                                is_folder=True,
                                attributes="d",
                            )
                        )
                        scanned_count += 1
                    except (OSError, PermissionError):
                        # Skip inaccessible directories
                        continue

                # Scan files
                for file_name in files:
                    if scanned_count >= max_items:
                        break

                    file_path = os.path.join(root, file_name)
                    try:
                        stat = os.stat(file_path)

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
                    except (OSError, PermissionError):
                        # Skip inaccessible files
                        continue

                if scanned_count >= max_items:
                    break

        except Exception as e:
            print(f"Error scanning directory {directory}: {e}")

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
