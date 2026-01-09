#!/usr/bin/env python3
"""
Prototype: WizTree CLI Wrapper + Python Fallback

This is a PROTOTYPE to validate the WizTree integration approach.
Tests scanning, parsing, and basic classification.

Usage:
    # Scan using WizTree (if available)
    python prototype_scanner.py

    # Force Python scanner
    python prototype_scanner.py --python-fallback

    # Scan specific drive
    python prototype_scanner.py --drive D

Category: PROTOTYPE / RESEARCH
"""

import argparse
import csv
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import os
import shutil

# ==============================================================================
# Data Models (Simplified for Prototype)
# ==============================================================================

class ScanResult:
    """Result from disk scan."""
    def __init__(self, path: str, size_bytes: int, modified: datetime, is_folder: bool):
        self.path = path
        self.size_bytes = size_bytes
        self.modified = modified
        self.is_folder = is_folder

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024**3)


# ==============================================================================
# WizTree Scanner
# ==============================================================================

class WizTreeScanner:
    """WizTree CLI wrapper."""

    def __init__(self, wiztree_path: Optional[Path] = None):
        self.wiztree_path = wiztree_path or self._find_wiztree()

    def _find_wiztree(self) -> Optional[Path]:
        """Try to find WizTree executable."""
        # Common installation locations
        search_paths = [
            Path("C:/Program Files/WizTree/wiztree64.exe"),
            Path("C:/Program Files (x86)/WizTree/wiztree64.exe"),
            Path("C:/Program Files/WizTree/wiztree.exe"),
            # Portable version in user downloads
            Path.home() / "Downloads" / "wiztree64.exe",
            # Bundled with Autopack (future)
            Path(__file__).parent.parent.parent / "tools" / "wiztree" / "wiztree64.exe",
        ]

        for path in search_paths:
            if path.exists():
                print(f"[WizTree] Found at: {path}")
                return path

        print("[WizTree] Not found - will use Python fallback")
        return None

    def is_available(self) -> bool:
        """Check if WizTree is available."""
        return self.wiztree_path is not None and self.wiztree_path.exists()

    def scan(self, drive_letter: str = "C") -> List[ScanResult]:
        """Scan drive using WizTree."""
        if not self.is_available():
            raise RuntimeError("WizTree not available")

        # Create output CSV path
        output_csv = Path.home() / ".autopack" / "cache" / f"wiztree_scan_{drive_letter}_{int(time.time())}.csv"
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        print(f"[WizTree] Scanning {drive_letter}: drive...")
        print(f"[WizTree] Output: {output_csv}")

        # Build command
        cmd = [
            str(self.wiztree_path),
            f"{drive_letter}:\\",
            f"/export={output_csv}",
            "/admin=0"  # Don't require admin (faster)
        ]

        start_time = time.time()

        try:
            # Run WizTree
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                check=True
            )

            elapsed = time.time() - start_time
            print(f"[WizTree] Scan completed in {elapsed:.1f} seconds")

            # Parse CSV
            results = self._parse_csv(output_csv)
            print(f"[WizTree] Parsed {len(results)} entries")

            return results

        except subprocess.TimeoutExpired:
            print("[WizTree] ERROR: Scan timed out")
            raise
        except subprocess.CalledProcessError as e:
            print(f"[WizTree] ERROR: Scan failed: {e.stderr}")
            raise
        except FileNotFoundError:
            print(f"[WizTree] ERROR: Executable not found at {self.wiztree_path}")
            raise

    def _parse_csv(self, csv_path: Path) -> List[ScanResult]:
        """Parse WizTree CSV export."""
        results = []

        try:
            with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    try:
                        # Parse timestamp
                        modified_str = row.get('Modified', '')
                        try:
                            modified = datetime.strptime(modified_str, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            modified = datetime.now()

                        results.append(ScanResult(
                            path=row['File Name'],
                            size_bytes=int(row['Size']),
                            modified=modified,
                            is_folder=row['Attributes'].startswith('d')
                        ))
                    except (ValueError, KeyError):
                        # Skip malformed rows
                        continue

        except Exception as e:
            print(f"[WizTree] ERROR parsing CSV: {e}")
            raise

        return results


# ==============================================================================
# Python Fallback Scanner
# ==============================================================================

class PythonScanner:
    """Python-based fallback scanner."""

    def scan(self, drive_letter: str = "C", max_depth: int = 4) -> List[ScanResult]:
        """
        Scan drive using Python os.walk.
        Limited depth to avoid being too slow.
        """
        root_path = Path(f"{drive_letter}:\\")
        print(f"[Python] Scanning {root_path} (max depth: {max_depth})...")
        print("[Python] This will be slower than WizTree...")

        results = []
        start_time = time.time()

        try:
            for dirpath, dirnames, filenames in os.walk(root_path):
                # Calculate depth
                depth = str(dirpath).count(os.sep) - str(root_path).count(os.sep)
                if depth > max_depth:
                    dirnames.clear()  # Don't recurse deeper
                    continue

                # Skip system/protected folders
                dirnames[:] = [d for d in dirnames if not d.startswith('$') and d.lower() not in ['system volume information']]

                # Add folders
                for dirname in dirnames:
                    full_path = Path(dirpath) / dirname
                    try:
                        stat = full_path.stat()
                        size = self._estimate_dir_size(full_path, max_depth=1)  # Quick estimate
                        results.append(ScanResult(
                            path=str(full_path),
                            size_bytes=size,
                            modified=datetime.fromtimestamp(stat.st_mtime),
                            is_folder=True
                        ))
                    except (PermissionError, FileNotFoundError):
                        continue

                # Add files (sample, don't add all for performance)
                if depth <= 2:  # Only add individual files at shallow depth
                    for filename in filenames[:100]:  # Sample first 100 files per directory
                        full_path = Path(dirpath) / filename
                        try:
                            stat = full_path.stat()
                            results.append(ScanResult(
                                path=str(full_path),
                                size_bytes=stat.st_size,
                                modified=datetime.fromtimestamp(stat.st_mtime),
                                is_folder=False
                            ))
                        except (PermissionError, FileNotFoundError):
                            continue

            elapsed = time.time() - start_time
            print(f"[Python] Scan completed in {elapsed:.1f} seconds")
            print(f"[Python] Found {len(results)} entries")

            return results

        except KeyboardInterrupt:
            print("\n[Python] Scan interrupted by user")
            raise

    def _estimate_dir_size(self, path: Path, max_depth: int = 1) -> int:
        """Estimate directory size (quick, not accurate)."""
        total = 0
        try:
            if max_depth == 0:
                return 0

            for entry in path.iterdir():
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir() and max_depth > 1:
                    total += self._estimate_dir_size(entry, max_depth - 1)
        except (PermissionError, FileNotFoundError):
            pass

        return total


# ==============================================================================
# Simple Classifier (Prototype)
# ==============================================================================

class SimpleClassifier:
    """Basic file classification for prototype."""

    @staticmethod
    def classify(scan_result: ScanResult) -> Optional[Dict]:
        """Classify a scan result as a cleanup candidate."""
        path_lower = scan_result.path.lower()

        # Developer artifacts
        if 'node_modules' in path_lower and scan_result.is_folder:
            return {
                'category': 'dev_artifacts',
                'subcategory': 'node_modules',
                'confidence': 'high',
                'safe': 'review',  # Requires approval
                'reason': 'Node.js dependencies folder'
            }

        if scan_result.is_folder and Path(scan_result.path).name.lower() in ['venv', '.venv', 'virtualenv']:
            return {
                'category': 'dev_artifacts',
                'subcategory': 'python_venv',
                'confidence': 'high',
                'safe': 'review',
                'reason': 'Python virtual environment'
            }

        # Temp files
        if any(pattern in path_lower for pattern in ['\\temp\\', '\\tmp\\', 'appdata\\local\\temp']):
            age_days = (datetime.now() - scan_result.modified).days
            if age_days >= 7:
                return {
                    'category': 'temp_files',
                    'confidence': 'high',
                    'safe': 'safe',
                    'reason': f'Temp file/folder older than 7 days (age: {age_days} days)'
                }

        # Browser cache
        if 'cache' in path_lower and any(browser in path_lower for browser in ['chrome', 'edge', 'firefox']):
            return {
                'category': 'browser_cache',
                'confidence': 'high',
                'safe': 'safe',
                'reason': 'Browser cache folder'
            }

        # Windows Update
        if 'softwaredistribution\\download' in path_lower:
            return {
                'category': 'windows_update',
                'confidence': 'high',
                'safe': 'safe',
                'reason': 'Windows Update download cache'
            }

        # Windows.old
        if 'windows.old' in path_lower:
            return {
                'category': 'windows_old',
                'confidence': 'high',
                'safe': 'review',
                'reason': 'Previous Windows installation'
            }

        return None


# ==============================================================================
# Main Prototype
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Storage Scanner Prototype")
    parser.add_argument('--drive', default='C', help='Drive letter to scan')
    parser.add_argument('--python-fallback', action='store_true', help='Force Python scanner')
    parser.add_argument('--top-n', type=int, default=20, help='Show top N largest folders')
    args = parser.parse_args()

    print("=" * 70)
    print("STORAGE SCANNER PROTOTYPE")
    print("=" * 70)
    print()

    # Choose scanner
    if args.python_fallback:
        print("[Scanner] Using Python fallback scanner")
        scanner = PythonScanner()
        results = scanner.scan(drive_letter=args.drive)
    else:
        wiztree = WizTreeScanner()
        if wiztree.is_available():
            print("[Scanner] Using WizTree (fast)")
            results = wiztree.scan(drive_letter=args.drive)
        else:
            print("[Scanner] WizTree not available, falling back to Python")
            scanner = PythonScanner()
            results = scanner.scan(drive_letter=args.drive)

    # Get disk space info
    try:
        disk_usage = shutil.disk_usage(f"{args.drive}:\\")
        total_gb = disk_usage.total / (1024**3)
        used_gb = disk_usage.used / (1024**3)
        free_gb = disk_usage.free / (1024**3)

        print()
        print("=" * 70)
        print("DISK USAGE SUMMARY")
        print("=" * 70)
        print(f"Total Space: {total_gb:.2f} GB")
        print(f"Used Space:  {used_gb:.2f} GB ({used_gb/total_gb*100:.1f}%)")
        print(f"Free Space:  {free_gb:.2f} GB ({free_gb/total_gb*100:.1f}%)")
    except Exception as e:
        print(f"[Warning] Could not get disk usage: {e}")

    # Find top space consumers (folders only)
    folders = [r for r in results if r.is_folder]
    folders.sort(key=lambda x: x.size_bytes, reverse=True)

    print()
    print("=" * 70)
    print(f"TOP {args.top_n} LARGEST FOLDERS")
    print("=" * 70)

    classifier = SimpleClassifier()
    cleanup_candidates = []

    for i, folder in enumerate(folders[:args.top_n], 1):
        classification = classifier.classify(folder)

        print(f"\n{i}. {folder.size_gb:.2f} GB - {folder.path}")
        print(f"   Modified: {folder.modified.strftime('%Y-%m-%d')}")

        if classification:
            print(f"   🔍 Category: {classification['category']} ({classification['subcategory'] if 'subcategory' in classification else 'general'})")
            print(f"   🎯 Confidence: {classification['confidence']}")
            print(f"   {'✅' if classification['safe'] == 'safe' else '⚠️'} Safety: {classification['safe']}")
            print(f"   💡 {classification['reason']}")

            cleanup_candidates.append({
                'folder': folder,
                'classification': classification
            })

    # Cleanup summary
    if cleanup_candidates:
        print()
        print("=" * 70)
        print("CLEANUP OPPORTUNITIES")
        print("=" * 70)

        total_reclaimable = sum(c['folder'].size_gb for c in cleanup_candidates)
        safe_cleanup = [c for c in cleanup_candidates if c['classification']['safe'] == 'safe']
        review_cleanup = [c for c in cleanup_candidates if c['classification']['safe'] == 'review']

        print(f"Total Potential Savings: {total_reclaimable:.2f} GB")
        print(f"Candidates: {len(cleanup_candidates)}")
        print()
        print(f"Auto-cleanable (safe):        {sum(c['folder'].size_gb for c in safe_cleanup):.2f} GB ({len(safe_cleanup)} items)")
        print(f"Requires approval (review):   {sum(c['folder'].size_gb for c in review_cleanup):.2f} GB ({len(review_cleanup)} items)")

        # Group by category
        by_category = {}
        for candidate in cleanup_candidates:
            category = candidate['classification']['category']
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(candidate)

        print()
        print("By Category:")
        for category, candidates in sorted(by_category.items(), key=lambda x: sum(c['folder'].size_gb for c in x[1]), reverse=True):
            total = sum(c['folder'].size_gb for c in candidates)
            print(f"  {category}: {total:.2f} GB ({len(candidates)} items)")

    print()
    print("=" * 70)
    print("PROTOTYPE COMPLETE")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Review cleanup candidates above")
    print("  2. Verify WizTree scanning performance")
    print("  3. Test Python fallback on non-NTFS drives")
    print("  4. Proceed to Phase 2: Core Module Implementation")


if __name__ == "__main__":
    main()
