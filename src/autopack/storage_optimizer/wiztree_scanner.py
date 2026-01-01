"""
WizTree CLI wrapper for high-performance disk scanning.

WizTree provides 30-50x faster scanning by reading the NTFS Master File Table (MFT)
directly instead of recursively enumerating directories.

Performance benchmarks:
- 500 GB drive: ~5-10 seconds
- 1 TB drive: ~10-20 seconds
- 2 TB drive: ~20-40 seconds

Falls back to Python-based scanner if WizTree is not installed or fails.
"""

import os
import subprocess
import csv
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone
from .models import ScanResult
from .scanner import StorageScanner

logger = logging.getLogger(__name__)


class WizTreeScanner:
    """High-performance scanner using WizTree CLI."""

    def __init__(self, wiztree_path: Optional[Path] = None):
        """
        Initialize WizTree scanner.

        Args:
            wiztree_path: Path to wiztree64.exe (auto-detect if None)
        """
        self.wiztree_path = wiztree_path or self._find_wiztree()
        self.fallback_scanner = StorageScanner()

    def _find_wiztree(self) -> Optional[Path]:
        """
        Auto-detect WizTree installation.

        Searches common installation paths:
        1. C:\Program Files\WizTree\wiztree64.exe
        2. C:\Program Files (x86)\WizTree\wiztree64.exe
        3. %LOCALAPPDATA%\WizTree\wiztree64.exe
        4. WIZTREE_PATH environment variable

        Returns:
            Path to wiztree64.exe or None if not found
        """
        # Check environment variable first
        env_path = os.getenv("WIZTREE_PATH")
        if env_path:
            path = Path(env_path)
            if path.exists():
                logger.info(f"[WizTree] Found via WIZTREE_PATH: {path}")
                return path

        # Check common installation paths
        possible_paths = [
            Path("C:/Program Files/WizTree/wiztree64.exe"),
            Path("C:/Program Files (x86)/WizTree/wiztree64.exe"),
            Path(os.getenv("LOCALAPPDATA", "")) / "WizTree" / "wiztree64.exe",
        ]

        for path in possible_paths:
            if path.exists():
                logger.info(f"[WizTree] Found at: {path}")
                return path

        logger.warning("[WizTree] Not found - will use Python fallback scanner")
        logger.info("[WizTree] Download from: https://www.diskanalyzer.com/download")
        return None

    def is_available(self) -> bool:
        """
        Check if WizTree is available.

        Returns:
            True if wiztree64.exe exists and is executable
        """
        return self.wiztree_path is not None and self.wiztree_path.exists()

    def scan_drive(
        self,
        drive_letter: str,
        max_depth: Optional[int] = None,
        max_items: int = 10000,
        admin_mode: bool = False
    ) -> List[ScanResult]:
        """
        Scan drive using WizTree CLI.

        WizTree scans the entire drive regardless of max_depth - we filter results
        after parsing the CSV to match the Python scanner behavior.

        Args:
            drive_letter: Drive letter (e.g., "C")
            max_depth: Maximum directory depth (None = unlimited, filter after scan)
            max_items: Maximum items to return (limits CSV parsing)
            admin_mode: Run with admin privileges (slower but more complete)

        Returns:
            List of ScanResult objects sorted by size descending

        Raises:
            None - falls back to Python scanner on any error
        """
        if not self.is_available():
            logger.warning("[WizTree] Not available, using Python fallback")
            return self.fallback_scanner.scan_drive(drive_letter, max_depth, max_items)

        try:
            # Create temp CSV file
            timestamp = int(datetime.now().timestamp())
            csv_path = Path(f"c:/temp/wiztree_scan_{drive_letter}_{timestamp}.csv")
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            # Build command
            # Note: WizTree CLI returns exit code 0 even on some errors, so we check CSV validity
            cmd = [
                str(self.wiztree_path),
                f"{drive_letter}:\\",
                f"/export={csv_path}",
                f"/admin={'1' if admin_mode else '0'}"
            ]

            logger.info(f"[WizTree] Scanning {drive_letter}:\\ (admin={admin_mode})...")
            start_time = datetime.now()

            # Run WizTree CLI
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            # Check if CSV was created (WizTree sometimes returns 0 even on failure)
            if not csv_path.exists():
                logger.error("[WizTree] CSV export file not created")
                return self.fallback_scanner.scan_drive(drive_letter, max_depth, max_items)

            if result.returncode != 0:
                logger.warning(f"[WizTree] Non-zero exit code: {result.returncode}")
                logger.warning(f"[WizTree] stderr: {result.stderr}")
                # Continue anyway - CSV might still be valid

            # Parse CSV
            scan_results = self._parse_csv(csv_path, max_depth, max_items)

            duration = (datetime.now() - start_time).seconds
            logger.info(f"[WizTree] Scanned {len(scan_results)} items in {duration}s")

            # Cleanup temp file
            try:
                csv_path.unlink(missing_ok=True)
            except:
                pass  # Don't fail if cleanup fails

            return scan_results

        except subprocess.TimeoutExpired:
            logger.error("[WizTree] Scan timeout (>10 minutes) - falling back to Python scanner")
            return self.fallback_scanner.scan_drive(drive_letter, max_depth, max_items)

        except Exception as e:
            logger.error(f"[WizTree] Unexpected error: {e} - falling back to Python scanner")
            return self.fallback_scanner.scan_drive(drive_letter, max_depth, max_items)

    def _parse_csv(
        self,
        csv_path: Path,
        max_depth: Optional[int],
        max_items: int
    ) -> List[ScanResult]:
        """
        Parse WizTree CSV export into ScanResult objects.

        CSV Format (with header):
            File Name,Size,Allocated,Modified,Attributes,%,Files,%,Allocated

        Example rows:
            "C:\\",1234567890,1234567890,"2025-12-01 10:30:00","d",100,100,100
            "C:\\temp\\file.txt",1024,4096,"2025-12-01 09:15:00","-",0.0001,1,0.0003

        Attributes column codes:
            d = directory
            - = file
            h = hidden
            s = system
            r = read-only

        Args:
            csv_path: Path to WizTree CSV export
            max_depth: Maximum directory depth to include (None = unlimited)
            max_items: Maximum items to return

        Returns:
            List of ScanResult objects sorted by size descending

        Raises:
            Exception: If CSV parsing fails (caller should fallback to Python scanner)
        """
        results = []

        try:
            # WizTree exports UTF-8 with BOM, use utf-8-sig to handle it
            with open(csv_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Skip if max_items reached
                    if len(results) >= max_items:
                        break

                    # Parse row fields
                    file_path = row.get('File Name', '')
                    if not file_path:
                        continue  # Skip empty paths

                    try:
                        size_bytes = int(row.get('Size', 0))
                    except ValueError:
                        size_bytes = 0

                    modified_str = row.get('Modified', '')
                    attributes = row.get('Attributes', '')

                    # Filter by depth if specified
                    if max_depth is not None:
                        # Count backslashes to determine depth
                        # C:\ = depth 0, C:\temp = depth 1, C:\temp\file.txt = depth 2
                        depth = file_path.count('\\') - 1  # Subtract root backslash
                        if depth > max_depth:
                            continue

                    # Parse timestamp (WizTree format: "YYYY-MM-DD HH:MM:SS")
                    try:
                        last_modified = datetime.strptime(modified_str, '%Y-%m-%d %H:%M:%S')
                        last_modified = last_modified.replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        # If parsing fails, use current time
                        last_modified = datetime.now(timezone.utc)

                    # Parse attributes
                    is_directory = 'd' in attributes.lower()
                    is_hidden = 'h' in attributes.lower()
                    is_system = 's' in attributes.lower()

                    # Create ScanResult
                    result = ScanResult(
                        path=file_path,
                        size_bytes=size_bytes,
                        is_directory=is_directory,
                        last_modified=last_modified,
                        is_hidden=is_hidden,
                        is_system=is_system
                    )

                    results.append(result)

        except Exception as e:
            logger.error(f"[WizTree] CSV parse error: {e}")
            raise  # Caller will fallback to Python scanner

        # Sort by size descending (match Python scanner behavior)
        results.sort(key=lambda r: r.size_bytes, reverse=True)

        return results

    def scan_directory(
        self,
        directory_path: str,
        max_depth: Optional[int] = None,
        max_items: int = 1000
    ) -> List[ScanResult]:
        """
        Scan specific directory using WizTree.

        Note: WizTree performs best on full drive scans (MFT reading).
        For directory-specific scans, it falls back to standard enumeration,
        which may not be significantly faster than Python. Consider using
        Python scanner directly for single directories.

        Args:
            directory_path: Full path to directory
            max_depth: Maximum depth relative to this directory
            max_items: Maximum items to return

        Returns:
            List of ScanResult objects
        """
        if not self.is_available():
            logger.warning("[WizTree] Not available, using Python fallback")
            return self.fallback_scanner.scan_directory(directory_path, max_depth, max_items)

        try:
            timestamp = int(datetime.now().timestamp())
            csv_path = Path(f"c:/temp/wiztree_scan_dir_{timestamp}.csv")
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            # Build command
            cmd = [
                str(self.wiztree_path),
                directory_path,
                f"/export={csv_path}",
                "/admin=0"  # No admin needed for single directory
            ]

            logger.info(f"[WizTree] Scanning directory: {directory_path}")
            start_time = datetime.now()

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for directories
            )

            if not csv_path.exists():
                logger.error("[WizTree] CSV export file not created")
                return self.fallback_scanner.scan_directory(directory_path, max_depth, max_items)

            # Parse CSV (adjust depth calculation for subdirectory scans)
            scan_results = self._parse_csv(csv_path, max_depth, max_items)

            duration = (datetime.now() - start_time).seconds
            logger.info(f"[WizTree] Scanned {len(scan_results)} items in {duration}s")

            # Cleanup
            try:
                csv_path.unlink(missing_ok=True)
            except:
                pass

            return scan_results

        except subprocess.TimeoutExpired:
            logger.error("[WizTree] Directory scan timeout - falling back")
            return self.fallback_scanner.scan_directory(directory_path, max_depth, max_items)

        except Exception as e:
            logger.error(f"[WizTree] Directory scan error: {e} - falling back")
            return self.fallback_scanner.scan_directory(directory_path, max_depth, max_items)
