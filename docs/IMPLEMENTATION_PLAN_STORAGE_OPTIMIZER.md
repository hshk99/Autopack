# Implementation Plan: Storage Optimizer Module

**Project**: Autopack Storage Optimizer
**Version**: 1.0
**Date**: 2026-01-01
**Status**: Planning Phase

## Executive Summary

Build a **Storage Optimizer** module for Autopack that runs fortnightly to reclaim disk space on Windows systems. The system will leverage existing open-source tools (WizTree) as the scanning engine and build intelligent cleanup automation on top.

### Key Differentiators
- **Developer-aware**: Knows about node_modules, venv, Docker, build artifacts
- **Automated scheduling**: Runs every fortnight, learns user patterns
- **Safe by default**: Approval workflow, rollback capability
- **Integrated with Autopack**: Uses existing phase system, database, telemetry

---

## Architecture Overview

```
Storage Optimizer Module
├── Scanning Engine (WizTree CLI wrapper)
├── Classification Layer (AI-powered categorization)
├── Cleanup Rules Engine (Safe deletion policies)
├── Scheduler (Fortnightly automation)
├── Reporting Dashboard (Space trends, recommendations)
└── Integration with Autopack Executor
```

---

## Phase Breakdown: Autopack vs Cursor

| Phase | Owner | Complexity | Why |
|-------|-------|------------|-----|
| **Phase 1**: Research & Prototyping | Cursor | High | External tool integration, Windows-specific APIs |
| **Phase 2**: Core Module Structure | Autopack | Medium | Follow existing patterns, file creation |
| **Phase 3**: Scanner Wrapper | Cursor | High | External process management, CSV parsing |
| **Phase 4**: Classification Engine | Autopack | Medium | Rule-based logic, pattern matching |
| **Phase 5**: Cleanup Executor | Autopack | Medium | File operations, safety checks |
| **Phase 6**: Scheduler Integration | Autopack | Low | Cron/task scheduler integration |
| **Phase 7**: Reporting System | Autopack | Medium | Database queries, trend analysis |
| **Phase 8**: Autopack Executor Integration | Cursor | Medium | Modify existing executor architecture |
| **Phase 9**: Testing & Validation | Both | High | Test suite + manual validation |
| **Phase 10**: Documentation | Autopack | Low | Generate user guides, API docs |

---

## Phase 1: Research & Prototyping (CURSOR)

**Duration**: 2-3 hours
**Owner**: Cursor (requires external tool testing)

### Objectives
1. Verify WizTree CLI works on Windows
2. Test CSV export format and parsing
3. Prototype basic scanning workflow
4. Identify Windows API requirements

### Tasks

#### Task 1.1: WizTree CLI Integration Research
```bash
# Download WizTree portable version
# https://www.diskanalyzer.com/download

# Test CLI commands
wiztree64.exe C:\ /export=C:\temp\scan_results.csv /admin=0

# Analyze CSV format
# Expected columns: File Name, Size, Allocated, Modified, Attributes, etc.
```

**Deliverable**: `docs/research/WIZTREE_CLI_INTEGRATION_RESEARCH.md`
- WizTree CLI command reference
- CSV schema documentation
- Performance benchmarks (scan time for various drive sizes)
- Limitations and edge cases

#### Task 1.2: Alternative Scanner Evaluation
Evaluate fallback options if WizTree licensing/distribution is problematic:

| Tool | License | Speed | CLI Support | Notes |
|------|---------|-------|-------------|-------|
| WizTree | Freeware | Fastest | Yes (CSV export) | Not open-source |
| WinDirStat | GPL v2 | Slow | Limited | Open-source |
| TreeSize Free | Freeware | Medium | Yes (XML export) | Good alternative |
| Custom Scanner | N/A | Slow | Full control | Built with Python/Win32 |

**Deliverable**: `docs/research/STORAGE_SCANNER_COMPARISON.md`

#### Task 1.3: Windows Cleanup API Research
Research safe deletion methods:
- `os.remove()` vs `send2trash` library (Recycle Bin)
- Windows Storage Sense API integration
- `cleanmgr.exe` automation
- DISM cleanup commands

**Deliverable**: `docs/research/WINDOWS_CLEANUP_APIS.md`

#### Task 1.4: Prototype Scanner Wrapper
```python
# scripts/storage/prototype_scanner.py
"""
Prototype: WizTree CLI wrapper
Tests scanning, parsing, and basic classification
"""

import subprocess
import csv
from pathlib import Path

def scan_drive(drive_letter: str = "C") -> list[dict]:
    """Scan drive using WizTree CLI, return parsed results."""
    output_csv = Path("C:/temp/wiztree_scan.csv")

    # Run WizTree scan
    cmd = [
        "C:/Program Files/WizTree/wiztree64.exe",
        f"{drive_letter}:\\",
        f"/export={output_csv}",
        "/admin=0"  # Don't require admin (faster, but less complete)
    ]

    subprocess.run(cmd, check=True)

    # Parse CSV
    results = []
    with open(output_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append({
                'path': row['File Name'],
                'size': int(row['Size']),
                'modified': row['Modified'],
                'is_folder': row['Attributes'].startswith('d'),
            })

    return results

def classify_cleanup_candidate(path: str, size: int) -> dict:
    """Classify if a file/folder is a cleanup candidate."""
    path_lower = path.lower()

    # Developer artifacts
    if 'node_modules' in path_lower:
        return {'category': 'dev_artifacts', 'confidence': 'high', 'safe': True}
    if path_lower.endswith(('venv', '.venv', 'virtualenv')):
        return {'category': 'dev_artifacts', 'confidence': 'high', 'safe': True}

    # Temp files
    if '\\temp\\' in path_lower or '\\tmp\\' in path_lower:
        return {'category': 'temp_files', 'confidence': 'medium', 'safe': True}

    # Browser cache
    if 'cache' in path_lower and any(browser in path_lower for browser in ['chrome', 'edge', 'firefox']):
        return {'category': 'browser_cache', 'confidence': 'high', 'safe': True}

    # Windows Update
    if 'softwaredistribution\\download' in path_lower:
        return {'category': 'windows_update', 'confidence': 'high', 'safe': True}

    # Windows.old
    if 'windows.old' in path_lower:
        return {'category': 'windows_old', 'confidence': 'high', 'safe': False}  # Requires user approval

    return {'category': 'unknown', 'confidence': 'low', 'safe': False}

if __name__ == "__main__":
    print("Scanning C: drive...")
    results = scan_drive("C")

    # Find top 20 largest folders
    folders = [r for r in results if r['is_folder']]
    folders.sort(key=lambda x: x['size'], reverse=True)

    print(f"\nTop 20 largest folders:")
    for i, folder in enumerate(folders[:20], 1):
        size_gb = folder['size'] / (1024**3)
        classification = classify_cleanup_candidate(folder['path'], folder['size'])
        print(f"{i}. {size_gb:.2f} GB - {folder['path']}")
        print(f"   Category: {classification['category']} (confidence: {classification['confidence']}, safe: {classification['safe']})")
```

**Deliverable**: Working prototype in `scripts/storage/prototype_scanner.py`

**Expected Output**:
```
Scanning C: drive...
Top 20 largest folders:
1. 52.00 GB - C:\Program Files (x86)\Steam\steamapps\common\Monster Hunter World
   Category: unknown (confidence: low, safe: False)
2. 20.00 GB - C:\dev\project1\node_modules
   Category: dev_artifacts (confidence: high, safe: True)
3. 15.00 GB - C:\Users\hshk9\AppData\Local\Docker\wsl\data
   Category: dev_artifacts (confidence: high, safe: True)
...
```

---

## Phase 2: Core Module Structure (AUTOPACK)

**Duration**: 1-2 hours
**Owner**: Autopack (file creation, boilerplate)

### Objectives
1. Create module directory structure
2. Set up base classes and interfaces
3. Add to Autopack's module registry
4. Create initial configuration schema

### Tasks

#### Task 2.1: Create Module Directory Structure
```
src/autopack/storage_optimizer/
├── __init__.py                 # Module exports
├── scanner.py                  # Disk scanning wrapper
├── classifier.py               # File classification logic
├── cleanup_rules.py            # Cleanup policies and rules
├── cleanup_executor.py         # Safe deletion executor
├── scheduler.py                # Fortnightly scheduling
├── reporter.py                 # Storage trends and reports
├── config.py                   # Configuration schema
└── models.py                   # Data models (ScanResult, CleanupCandidate, etc.)

scripts/storage/
├── scan_disk.py               # CLI: Manual disk scan
├── cleanup_storage.py         # CLI: Execute cleanup
├── storage_report.py          # CLI: Generate reports
└── prototype_scanner.py       # (from Phase 1)

tests/autopack/storage_optimizer/
├── test_scanner.py
├── test_classifier.py
├── test_cleanup_rules.py
├── test_cleanup_executor.py
└── fixtures/
    └── sample_scan_results.csv
```

#### Task 2.2: Define Data Models
```python
# src/autopack/storage_optimizer/models.py
"""
Data models for storage optimizer.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

class CleanupCategory(Enum):
    """Categories of files that can be cleaned."""
    TEMP_FILES = "temp_files"
    BROWSER_CACHE = "browser_cache"
    DEV_ARTIFACTS = "dev_artifacts"
    WINDOWS_UPDATE = "windows_update"
    WINDOWS_OLD = "windows_old"
    DOCKER_WSL = "docker_wsl"
    BUILD_ARTIFACTS = "build_artifacts"
    DOWNLOADS_OLD = "downloads_old"
    RECYCLE_BIN = "recycle_bin"
    UNKNOWN = "unknown"

class SafetyLevel(Enum):
    """Safety level for deletion."""
    SAFE = "safe"           # Can auto-delete without approval
    REVIEW = "review"       # Requires user approval
    DANGEROUS = "dangerous" # Never auto-delete

@dataclass
class ScanResult:
    """Result from disk scan."""
    path: str
    size_bytes: int
    modified: datetime
    is_folder: bool
    attributes: str

@dataclass
class CleanupCandidate:
    """A file/folder that could be cleaned up."""
    path: str
    size_bytes: int
    category: CleanupCategory
    safety_level: SafetyLevel
    confidence: float  # 0.0 to 1.0
    reason: str
    potential_savings_gb: float
    last_modified: datetime

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024**3)

@dataclass
class CleanupPlan:
    """Plan for cleanup execution."""
    candidates: list[CleanupCandidate]
    total_potential_savings_gb: float
    auto_deletable_count: int
    requires_approval_count: int
    created_at: datetime

@dataclass
class CleanupResult:
    """Result of cleanup execution."""
    path: str
    size_freed_bytes: int
    success: bool
    error: Optional[str]
    timestamp: datetime

@dataclass
class StorageReport:
    """Storage usage report."""
    scan_date: datetime
    total_disk_space_gb: float
    used_space_gb: float
    free_space_gb: float
    top_space_consumers: list[dict]
    cleanup_candidates: list[CleanupCandidate]
    historical_trend: Optional[list[dict]]  # Previous scans
```

#### Task 2.3: Create Configuration Schema
```python
# src/autopack/storage_optimizer/config.py
"""
Configuration for storage optimizer.
"""

from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class StorageOptimizerConfig:
    """Configuration for storage optimizer."""

    # Scanner settings
    scanner_executable: str = "wiztree64.exe"
    scanner_path: Path = Path("C:/Program Files/WizTree/wiztree64.exe")
    scan_drives: list[str] = field(default_factory=lambda: ["C"])
    require_admin: bool = False  # Faster scans without admin

    # Cleanup settings
    auto_delete_threshold_gb: float = 0.1  # Auto-delete only if < 100MB
    max_auto_delete_total_gb: float = 10.0  # Max total auto-deletion per run
    use_recycle_bin: bool = True  # Send to recycle bin vs permanent delete

    # Safety settings
    protected_paths: list[str] = field(default_factory=lambda: [
        "C:\\Windows\\System32",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
    ])

    # Scheduling settings
    schedule_enabled: bool = True
    schedule_interval_days: int = 14  # Fortnightly
    schedule_time: str = "02:00"  # 2 AM

    # Reporting settings
    report_retention_days: int = 90
    send_email_report: bool = False
    email_recipient: str = ""

    # Developer-specific settings
    cleanup_node_modules: bool = True
    cleanup_venv: bool = True
    cleanup_docker: bool = True
    cleanup_build_artifacts: bool = True

    # Age thresholds (days)
    temp_files_age_days: int = 7
    downloads_age_days: int = 30
    dev_artifacts_age_days: int = 60

# Default configuration
DEFAULT_CONFIG = StorageOptimizerConfig()
```

#### Task 2.4: Create Module __init__.py
```python
# src/autopack/storage_optimizer/__init__.py
"""
Storage Optimizer Module

Automated disk space cleanup with developer-aware intelligence.
"""

from .models import (
    CleanupCategory,
    SafetyLevel,
    ScanResult,
    CleanupCandidate,
    CleanupPlan,
    CleanupResult,
    StorageReport,
)
from .config import StorageOptimizerConfig, DEFAULT_CONFIG
from .scanner import DiskScanner
from .classifier import FileClassifier
from .cleanup_rules import CleanupRulesEngine
from .cleanup_executor import CleanupExecutor
from .scheduler import StorageScheduler
from .reporter import StorageReporter

__version__ = "1.0.0"

__all__ = [
    # Models
    "CleanupCategory",
    "SafetyLevel",
    "ScanResult",
    "CleanupCandidate",
    "CleanupPlan",
    "CleanupResult",
    "StorageReport",

    # Configuration
    "StorageOptimizerConfig",
    "DEFAULT_CONFIG",

    # Core classes
    "DiskScanner",
    "FileClassifier",
    "CleanupRulesEngine",
    "CleanupExecutor",
    "StorageScheduler",
    "StorageReporter",
]
```

**Deliverables**:
- All directory structure created
- All model classes defined
- Configuration schema complete
- Module properly exported

---

## Phase 3: Scanner Wrapper (CURSOR)

**Duration**: 2-3 hours
**Owner**: Cursor (external process management, error handling)

### Objectives
1. Wrap WizTree CLI in robust Python interface
2. Handle edge cases (permissions, locked files, large drives)
3. Implement caching for performance
4. Add fallback scanning method

### Tasks

#### Task 3.1: Implement DiskScanner Class
```python
# src/autopack/storage_optimizer/scanner.py
"""
Disk scanner wrapper for WizTree CLI.
"""

import csv
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging

from .models import ScanResult
from .config import StorageOptimizerConfig

logger = logging.getLogger(__name__)

class DiskScanner:
    """Wrapper for WizTree CLI disk scanning."""

    def __init__(self, config: StorageOptimizerConfig):
        self.config = config
        self.cache_dir = Path.home() / ".autopack" / "storage_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def scan(
        self,
        drive_letter: str = "C",
        use_cache: bool = True,
        cache_ttl_hours: int = 6
    ) -> list[ScanResult]:
        """
        Scan a drive and return results.

        Args:
            drive_letter: Drive letter to scan (e.g., "C")
            use_cache: Whether to use cached results if available
            cache_ttl_hours: Cache time-to-live in hours

        Returns:
            List of ScanResult objects
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached_results(drive_letter, cache_ttl_hours)
            if cached:
                logger.info(f"Using cached scan results for {drive_letter}:")
                return cached

        # Run fresh scan
        logger.info(f"Scanning {drive_letter}: drive with WizTree...")
        results = self._run_wiztree_scan(drive_letter)

        # Cache results
        self._cache_results(drive_letter, results)

        return results

    def _run_wiztree_scan(self, drive_letter: str) -> list[ScanResult]:
        """Run WizTree CLI and parse results."""
        # Create temporary CSV output file
        output_csv = self.cache_dir / f"scan_{drive_letter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        # Build command
        cmd = [
            str(self.config.scanner_path),
            f"{drive_letter}:\\",
            f"/export={output_csv}",
            f"/admin={'1' if self.config.require_admin else '0'}",
        ]

        try:
            # Run scanner
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                check=True
            )

            logger.info(f"WizTree scan completed for {drive_letter}:")

            # Parse CSV results
            return self._parse_csv_results(output_csv)

        except subprocess.TimeoutExpired:
            logger.error(f"WizTree scan timed out for {drive_letter}:")
            raise
        except subprocess.CalledProcessError as e:
            logger.error(f"WizTree scan failed: {e.stderr}")
            raise
        except FileNotFoundError:
            logger.error(f"WizTree executable not found at {self.config.scanner_path}")
            raise
        finally:
            # Cleanup temp file (optional - keep for debugging)
            pass

    def _parse_csv_results(self, csv_path: Path) -> list[ScanResult]:
        """Parse WizTree CSV export."""
        results = []

        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    results.append(ScanResult(
                        path=row['File Name'],
                        size_bytes=int(row['Size']),
                        modified=datetime.strptime(row['Modified'], '%Y-%m-%d %H:%M:%S'),
                        is_folder=row['Attributes'].startswith('d'),
                        attributes=row['Attributes']
                    ))
                except (ValueError, KeyError) as e:
                    logger.warning(f"Failed to parse row: {e}")
                    continue

        logger.info(f"Parsed {len(results)} scan results")
        return results

    def _get_cached_results(
        self,
        drive_letter: str,
        ttl_hours: int
    ) -> Optional[list[ScanResult]]:
        """Get cached scan results if available and fresh."""
        cache_pattern = f"scan_{drive_letter}_*.csv"
        cache_files = sorted(self.cache_dir.glob(cache_pattern), reverse=True)

        if not cache_files:
            return None

        latest_cache = cache_files[0]
        cache_age = datetime.now() - datetime.fromtimestamp(latest_cache.stat().st_mtime)

        if cache_age > timedelta(hours=ttl_hours):
            logger.info(f"Cache expired (age: {cache_age})")
            return None

        logger.info(f"Using cache from {latest_cache.name} (age: {cache_age})")
        return self._parse_csv_results(latest_cache)

    def _cache_results(self, drive_letter: str, results: list[ScanResult]) -> None:
        """Cache scan results for future use."""
        # Already cached by _run_wiztree_scan
        pass
```

**Deliverable**: Robust scanner with caching, error handling, and logging

#### Task 3.2: Add Fallback Scanner (Python-based)
For systems without WizTree or when WizTree fails:

```python
# src/autopack/storage_optimizer/scanner.py (continued)

class FallbackScanner:
    """Python-based disk scanner (slower, but always available)."""

    @staticmethod
    def scan(root_path: Path, max_depth: int = 5) -> list[ScanResult]:
        """
        Scan directory tree using Python os.walk.
        Slower than WizTree but always works.
        """
        results = []

        for dirpath, dirnames, filenames in os.walk(root_path):
            depth = dirpath.count(os.sep) - str(root_path).count(os.sep)
            if depth > max_depth:
                dirnames.clear()  # Don't recurse deeper
                continue

            # Add folders
            for dirname in dirnames:
                full_path = Path(dirpath) / dirname
                try:
                    stat = full_path.stat()
                    results.append(ScanResult(
                        path=str(full_path),
                        size_bytes=FallbackScanner._get_dir_size(full_path),
                        modified=datetime.fromtimestamp(stat.st_mtime),
                        is_folder=True,
                        attributes='d'
                    ))
                except (PermissionError, FileNotFoundError):
                    continue

            # Add files
            for filename in filenames:
                full_path = Path(dirpath) / filename
                try:
                    stat = full_path.stat()
                    results.append(ScanResult(
                        path=str(full_path),
                        size_bytes=stat.st_size,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                        is_folder=False,
                        attributes='-'
                    ))
                except (PermissionError, FileNotFoundError):
                    continue

        return results

    @staticmethod
    def _get_dir_size(path: Path) -> int:
        """Calculate directory size recursively."""
        total = 0
        try:
            for entry in path.rglob('*'):
                if entry.is_file():
                    total += entry.stat().st_size
        except (PermissionError, FileNotFoundError):
            pass
        return total
```

**Deliverable**: Fallback scanner for reliability

---

## Phase 4: Classification Engine (AUTOPACK)

**Duration**: 2-3 hours
**Owner**: Autopack (rule-based logic, pattern matching)

### Objectives
1. Implement file classification rules
2. Developer-aware pattern detection
3. Confidence scoring
4. Safety level assignment

### Tasks

#### Task 4.1: Implement FileClassifier
```python
# src/autopack/storage_optimizer/classifier.py
"""
File classification for cleanup candidates.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .models import ScanResult, CleanupCandidate, CleanupCategory, SafetyLevel
from .config import StorageOptimizerConfig

class FileClassifier:
    """Classify files/folders for cleanup eligibility."""

    def __init__(self, config: StorageOptimizerConfig):
        self.config = config

        # Define classification rules
        self.rules = [
            self._classify_temp_files,
            self._classify_browser_cache,
            self._classify_dev_artifacts,
            self._classify_windows_update,
            self._classify_windows_old,
            self._classify_docker_wsl,
            self._classify_build_artifacts,
            self._classify_old_downloads,
            self._classify_recycle_bin,
        ]

    def classify(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """
        Classify a scan result as a cleanup candidate.

        Returns None if not a cleanup candidate.
        """
        # Try each classification rule
        for rule in self.rules:
            candidate = rule(scan_result)
            if candidate:
                return candidate

        return None

    def classify_batch(self, scan_results: list[ScanResult]) -> list[CleanupCandidate]:
        """Classify multiple scan results."""
        candidates = []
        for result in scan_results:
            candidate = self.classify(result)
            if candidate:
                candidates.append(candidate)
        return candidates

    # -------------------------------------------------------------------------
    # Classification Rules
    # -------------------------------------------------------------------------

    def _classify_temp_files(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """Classify temporary files."""
        path_lower = scan_result.path.lower()

        # Windows temp directories
        temp_patterns = [
            r'\\temp\\',
            r'\\tmp\\',
            r'\\appdata\\local\\temp',
            r'\\windows\\temp',
        ]

        if any(re.search(pattern, path_lower) for pattern in temp_patterns):
            # Check age
            age_days = (datetime.now() - scan_result.modified).days

            if age_days >= self.config.temp_files_age_days:
                return CleanupCandidate(
                    path=scan_result.path,
                    size_bytes=scan_result.size_bytes,
                    category=CleanupCategory.TEMP_FILES,
                    safety_level=SafetyLevel.SAFE,
                    confidence=0.9,
                    reason=f"Temp file/folder older than {self.config.temp_files_age_days} days",
                    potential_savings_gb=scan_result.size_bytes / (1024**3),
                    last_modified=scan_result.modified
                )

        return None

    def _classify_browser_cache(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """Classify browser cache files."""
        path_lower = scan_result.path.lower()

        browser_cache_patterns = [
            (r'chrome.*\\cache', 'Chrome cache'),
            (r'edge.*\\cache', 'Edge cache'),
            (r'firefox.*\\cache', 'Firefox cache'),
            (r'appdata\\local\\microsoft\\edge\\user data.*\\cache', 'Edge cache'),
            (r'appdata\\local\\google\\chrome\\user data.*\\cache', 'Chrome cache'),
        ]

        for pattern, name in browser_cache_patterns:
            if re.search(pattern, path_lower):
                return CleanupCandidate(
                    path=scan_result.path,
                    size_bytes=scan_result.size_bytes,
                    category=CleanupCategory.BROWSER_CACHE,
                    safety_level=SafetyLevel.SAFE,
                    confidence=0.95,
                    reason=f"{name} - safe to clear",
                    potential_savings_gb=scan_result.size_bytes / (1024**3),
                    last_modified=scan_result.modified
                )

        return None

    def _classify_dev_artifacts(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """Classify developer artifacts (node_modules, venv, etc.)."""
        if not scan_result.is_folder:
            return None

        path = Path(scan_result.path)
        folder_name = path.name.lower()

        # node_modules
        if folder_name == 'node_modules' and self.config.cleanup_node_modules:
            # Check if project seems abandoned (old package.json)
            parent_package_json = path.parent / 'package.json'
            if parent_package_json.exists():
                age_days = (datetime.now() - datetime.fromtimestamp(parent_package_json.stat().st_mtime)).days

                if age_days >= self.config.dev_artifacts_age_days:
                    return CleanupCandidate(
                        path=scan_result.path,
                        size_bytes=scan_result.size_bytes,
                        category=CleanupCategory.DEV_ARTIFACTS,
                        safety_level=SafetyLevel.REVIEW,
                        confidence=0.8,
                        reason=f"node_modules in project not modified for {age_days} days",
                        potential_savings_gb=scan_result.size_bytes / (1024**3),
                        last_modified=scan_result.modified
                    )

        # Python venv
        if folder_name in ('venv', '.venv', 'virtualenv', 'env') and self.config.cleanup_venv:
            # Check age
            age_days = (datetime.now() - scan_result.modified).days

            if age_days >= self.config.dev_artifacts_age_days:
                return CleanupCandidate(
                    path=scan_result.path,
                    size_bytes=scan_result.size_bytes,
                    category=CleanupCategory.DEV_ARTIFACTS,
                    safety_level=SafetyLevel.REVIEW,
                    confidence=0.8,
                    reason=f"Python venv not modified for {age_days} days",
                    potential_savings_gb=scan_result.size_bytes / (1024**3),
                    last_modified=scan_result.modified
                )

        return None

    def _classify_windows_update(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """Classify Windows Update cache."""
        path_lower = scan_result.path.lower()

        if 'softwaredistribution\\download' in path_lower:
            return CleanupCandidate(
                path=scan_result.path,
                size_bytes=scan_result.size_bytes,
                category=CleanupCategory.WINDOWS_UPDATE,
                safety_level=SafetyLevel.SAFE,
                confidence=0.9,
                reason="Windows Update download cache",
                potential_savings_gb=scan_result.size_bytes / (1024**3),
                last_modified=scan_result.modified
            )

        return None

    def _classify_windows_old(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """Classify Windows.old folder."""
        path_lower = scan_result.path.lower()

        if path_lower == 'c:\\windows.old' or path_lower.startswith('c:\\windows.old\\'):
            return CleanupCandidate(
                path='C:\\Windows.old',  # Always use root folder
                size_bytes=scan_result.size_bytes,
                category=CleanupCategory.WINDOWS_OLD,
                safety_level=SafetyLevel.REVIEW,
                confidence=1.0,
                reason="Previous Windows installation (safe to remove after 30 days)",
                potential_savings_gb=scan_result.size_bytes / (1024**3),
                last_modified=scan_result.modified
            )

        return None

    def _classify_docker_wsl(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """Classify Docker/WSL data."""
        path_lower = scan_result.path.lower()

        docker_patterns = [
            (r'docker\\wsl\\data', 'Docker WSL data'),
            (r'appdata\\local\\docker', 'Docker Desktop data'),
        ]

        for pattern, name in docker_patterns:
            if re.search(pattern, path_lower) and self.config.cleanup_docker:
                return CleanupCandidate(
                    path=scan_result.path,
                    size_bytes=scan_result.size_bytes,
                    category=CleanupCategory.DOCKER_WSL,
                    safety_level=SafetyLevel.REVIEW,
                    confidence=0.7,
                    reason=f"{name} - review before deletion",
                    potential_savings_gb=scan_result.size_bytes / (1024**3),
                    last_modified=scan_result.modified
                )

        return None

    def _classify_build_artifacts(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """Classify build artifacts (dist, build, target, etc.)."""
        if not scan_result.is_folder:
            return None

        path = Path(scan_result.path)
        folder_name = path.name.lower()

        build_folders = ['dist', 'build', 'target', 'out', '.next', '__pycache__']

        if folder_name in build_folders and self.config.cleanup_build_artifacts:
            age_days = (datetime.now() - scan_result.modified).days

            if age_days >= 7:  # Build artifacts older than 1 week
                return CleanupCandidate(
                    path=scan_result.path,
                    size_bytes=scan_result.size_bytes,
                    category=CleanupCategory.BUILD_ARTIFACTS,
                    safety_level=SafetyLevel.REVIEW,
                    confidence=0.6,
                    reason=f"Build artifact ({folder_name}) not modified for {age_days} days",
                    potential_savings_gb=scan_result.size_bytes / (1024**3),
                    last_modified=scan_result.modified
                )

        return None

    def _classify_old_downloads(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """Classify old files in Downloads folder."""
        path_lower = scan_result.path.lower()

        if '\\downloads\\' in path_lower:
            age_days = (datetime.now() - scan_result.modified).days

            if age_days >= self.config.downloads_age_days:
                return CleanupCandidate(
                    path=scan_result.path,
                    size_bytes=scan_result.size_bytes,
                    category=CleanupCategory.DOWNLOADS_OLD,
                    safety_level=SafetyLevel.REVIEW,
                    confidence=0.5,
                    reason=f"Download older than {self.config.downloads_age_days} days",
                    potential_savings_gb=scan_result.size_bytes / (1024**3),
                    last_modified=scan_result.modified
                )

        return None

    def _classify_recycle_bin(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """Classify Recycle Bin contents."""
        path_lower = scan_result.path.lower()

        if '$recycle.bin' in path_lower:
            return CleanupCandidate(
                path=scan_result.path,
                size_bytes=scan_result.size_bytes,
                category=CleanupCategory.RECYCLE_BIN,
                safety_level=SafetyLevel.SAFE,
                confidence=1.0,
                reason="Recycle Bin contents",
                potential_savings_gb=scan_result.size_bytes / (1024**3),
                last_modified=scan_result.modified
            )

        return None
```

**Deliverable**: Comprehensive classification engine with 9+ rule categories

---

## Phase 5: Cleanup Executor (AUTOPACK)

**Duration**: 2-3 hours
**Owner**: Autopack (file operations, safety checks)

### Objectives
1. Safe file deletion with approval workflow
2. Recycle bin vs permanent deletion
3. Rollback capability
4. Progress tracking and logging

### Tasks

#### Task 5.1: Implement CleanupExecutor
```python
# src/autopack/storage_optimizer/cleanup_executor.py
"""
Safe cleanup execution with approval workflow.
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import logging

try:
    from send2trash import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False

from .models import CleanupCandidate, CleanupPlan, CleanupResult, SafetyLevel
from .config import StorageOptimizerConfig

logger = logging.getLogger(__name__)

class CleanupExecutor:
    """Execute cleanup operations safely."""

    def __init__(self, config: StorageOptimizerConfig):
        self.config = config
        self.dry_run = True

    def create_plan(self, candidates: List[CleanupCandidate]) -> CleanupPlan:
        """
        Create cleanup plan from candidates.
        Separates auto-deletable from requires-approval.
        """
        auto_deletable = [
            c for c in candidates
            if c.safety_level == SafetyLevel.SAFE
            and c.size_gb <= self.config.auto_delete_threshold_gb
        ]

        requires_approval = [
            c for c in candidates
            if c.safety_level == SafetyLevel.REVIEW
            or c.size_gb > self.config.auto_delete_threshold_gb
        ]

        total_savings = sum(c.size_gb for c in candidates)

        return CleanupPlan(
            candidates=candidates,
            total_potential_savings_gb=total_savings,
            auto_deletable_count=len(auto_deletable),
            requires_approval_count=len(requires_approval),
            created_at=datetime.now()
        )

    def execute_plan(
        self,
        plan: CleanupPlan,
        approved_paths: Optional[List[str]] = None,
        dry_run: bool = True
    ) -> List[CleanupResult]:
        """
        Execute cleanup plan.

        Args:
            plan: Cleanup plan to execute
            approved_paths: List of paths user approved for deletion
            dry_run: If True, don't actually delete files

        Returns:
            List of CleanupResult objects
        """
        self.dry_run = dry_run
        results = []

        approved_set = set(approved_paths or [])

        for candidate in plan.candidates:
            # Safety check: NEVER delete dangerous items
            if candidate.safety_level == SafetyLevel.DANGEROUS:
                logger.warning(f"Skipping dangerous item: {candidate.path}")
                continue

            # Check if protected path
            if self._is_protected_path(candidate.path):
                logger.warning(f"Skipping protected path: {candidate.path}")
                continue

            # Auto-delete if safe
            if candidate.safety_level == SafetyLevel.SAFE:
                if candidate.size_gb <= self.config.auto_delete_threshold_gb:
                    result = self._delete_item(candidate)
                    results.append(result)
                else:
                    logger.info(f"Item too large for auto-delete: {candidate.path} ({candidate.size_gb:.2f} GB)")

            # Delete if user approved
            elif candidate.path in approved_set:
                result = self._delete_item(candidate)
                results.append(result)
            else:
                logger.info(f"Skipping unapproved item: {candidate.path}")

        # Check total deletion limit
        total_deleted_gb = sum(r.size_freed_bytes / (1024**3) for r in results if r.success)
        if total_deleted_gb > self.config.max_auto_delete_total_gb:
            logger.warning(f"Exceeded max auto-delete limit: {total_deleted_gb:.2f} GB")

        return results

    def _delete_item(self, candidate: CleanupCandidate) -> CleanupResult:
        """Delete a single item."""
        path = Path(candidate.path)

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would delete: {path} ({candidate.size_gb:.2f} GB)")
            return CleanupResult(
                path=str(path),
                size_freed_bytes=candidate.size_bytes,
                success=True,
                error=None,
                timestamp=datetime.now()
            )

        try:
            # Use recycle bin if configured and available
            if self.config.use_recycle_bin and SEND2TRASH_AVAILABLE:
                send2trash(str(path))
                logger.info(f"Moved to Recycle Bin: {path} ({candidate.size_gb:.2f} GB)")
            else:
                # Permanent deletion
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                logger.info(f"Deleted: {path} ({candidate.size_gb:.2f} GB)")

            return CleanupResult(
                path=str(path),
                size_freed_bytes=candidate.size_bytes,
                success=True,
                error=None,
                timestamp=datetime.now()
            )

        except PermissionError as e:
            logger.error(f"Permission denied: {path} - {e}")
            return CleanupResult(
                path=str(path),
                size_freed_bytes=0,
                success=False,
                error=f"Permission denied: {e}",
                timestamp=datetime.now()
            )
        except Exception as e:
            logger.error(f"Failed to delete {path}: {e}")
            return CleanupResult(
                path=str(path),
                size_freed_bytes=0,
                success=False,
                error=str(e),
                timestamp=datetime.now()
            )

    def _is_protected_path(self, path: str) -> bool:
        """Check if path is protected from deletion."""
        path_lower = path.lower()

        for protected in self.config.protected_paths:
            if path_lower.startswith(protected.lower()):
                return True

        return False
```

**Deliverable**: Safe cleanup executor with approval workflow

---

## Phase 6: Scheduler Integration (AUTOPACK)

**Duration**: 1-2 hours
**Owner**: Autopack (task scheduling)

### Objectives
1. Windows Task Scheduler integration
2. Fortnightly execution schedule
3. Email notifications (optional)

### Tasks

#### Task 6.1: Implement StorageScheduler
```python
# src/autopack/storage_optimizer/scheduler.py
"""
Scheduling for automated storage optimization.
"""

import platform
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import logging

from .config import StorageOptimizerConfig

logger = logging.getLogger(__name__)

class StorageScheduler:
    """Schedule automated storage optimization runs."""

    def __init__(self, config: StorageOptimizerConfig):
        self.config = config
        self.task_name = "AutopackStorageOptimizer"

    def create_schedule(self) -> bool:
        """
        Create scheduled task for fortnightly runs.

        Returns True if successful.
        """
        if platform.system() != "Windows":
            logger.error("Scheduling only supported on Windows")
            return False

        # Get script path
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "storage" / "cleanup_storage.py"

        # Calculate next run time
        now = datetime.now()
        schedule_time_parts = self.config.schedule_time.split(':')
        next_run = now.replace(
            hour=int(schedule_time_parts[0]),
            minute=int(schedule_time_parts[1]),
            second=0,
            microsecond=0
        )

        if next_run < now:
            next_run += timedelta(days=1)

        # Create Windows Task Scheduler task
        cmd = [
            'schtasks',
            '/create',
            '/tn', self.task_name,
            '/tr', f'python "{script_path}" --auto',
            '/sc', 'daily',
            '/mo', str(self.config.schedule_interval_days),
            '/st', self.config.schedule_time,
            '/f'  # Force overwrite if exists
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Created scheduled task: {self.task_name}")
            logger.info(f"Next run: {next_run}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create scheduled task: {e.stderr}")
            return False

    def delete_schedule(self) -> bool:
        """Delete scheduled task."""
        if platform.system() != "Windows":
            return False

        cmd = ['schtasks', '/delete', '/tn', self.task_name, '/f']

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Deleted scheduled task: {self.task_name}")
            return True
        except subprocess.CalledProcessError:
            logger.error("Failed to delete scheduled task")
            return False

    def check_schedule_status(self) -> dict:
        """Check status of scheduled task."""
        if platform.system() != "Windows":
            return {'exists': False}

        cmd = ['schtasks', '/query', '/tn', self.task_name, '/fo', 'csv']

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')

            if len(lines) > 1:
                # Parse CSV output
                return {
                    'exists': True,
                    'status': 'Scheduled',
                    'next_run': 'See Task Scheduler for details'
                }
        except subprocess.CalledProcessError:
            return {'exists': False}

        return {'exists': False}
```

**Deliverable**: Windows Task Scheduler integration

---

## Phase 7: Reporting System (AUTOPACK)

**Duration**: 2-3 hours
**Owner**: Autopack (database queries, charts)

### Objectives
1. Generate storage usage reports
2. Track space reclaimed over time
3. Visualize trends
4. Email reports (optional)

### Tasks

#### Task 7.1: Implement StorageReporter
```python
# src/autopack/storage_optimizer/reporter.py
"""
Storage reporting and trend analysis.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
import json
import logging

from .models import StorageReport, CleanupCandidate, CleanupResult
from .config import StorageOptimizerConfig

logger = logging.getLogger(__name__)

class StorageReporter:
    """Generate storage usage reports."""

    def __init__(self, config: StorageOptimizerConfig):
        self.config = config
        self.reports_dir = Path.home() / ".autopack" / "storage_reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def create_report(
        self,
        scan_date: datetime,
        total_space_gb: float,
        used_space_gb: float,
        free_space_gb: float,
        top_consumers: List[dict],
        cleanup_candidates: List[CleanupCandidate]
    ) -> StorageReport:
        """Create storage report."""

        # Load historical trend
        historical_trend = self._load_historical_trend()

        report = StorageReport(
            scan_date=scan_date,
            total_disk_space_gb=total_space_gb,
            used_space_gb=used_space_gb,
            free_space_gb=free_space_gb,
            top_space_consumers=top_consumers,
            cleanup_candidates=cleanup_candidates,
            historical_trend=historical_trend
        )

        # Save report
        self._save_report(report)

        return report

    def generate_summary(
        self,
        report: StorageReport,
        cleanup_results: Optional[List[CleanupResult]] = None
    ) -> str:
        """Generate human-readable summary."""

        lines = []
        lines.append("=" * 70)
        lines.append("STORAGE OPTIMIZATION REPORT")
        lines.append("=" * 70)
        lines.append(f"Date: {report.scan_date.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        lines.append("DISK USAGE:")
        lines.append(f"  Total Space: {report.total_disk_space_gb:.2f} GB")
        lines.append(f"  Used Space:  {report.used_space_gb:.2f} GB ({report.used_space_gb/report.total_disk_space_gb*100:.1f}%)")
        lines.append(f"  Free Space:  {report.free_space_gb:.2f} GB ({report.free_space_gb/report.total_disk_space_gb*100:.1f}%)")
        lines.append("")

        lines.append("TOP 10 SPACE CONSUMERS:")
        for i, consumer in enumerate(report.top_space_consumers[:10], 1):
            lines.append(f"  {i}. {consumer['size_gb']:.2f} GB - {consumer['path']}")
        lines.append("")

        if report.cleanup_candidates:
            total_reclaimable = sum(c.size_gb for c in report.cleanup_candidates)
            lines.append("CLEANUP OPPORTUNITIES:")
            lines.append(f"  Total Potential Savings: {total_reclaimable:.2f} GB")
            lines.append(f"  Candidates: {len(report.cleanup_candidates)}")
            lines.append("")

            # Group by category
            by_category = {}
            for candidate in report.cleanup_candidates:
                category = candidate.category.value
                if category not in by_category:
                    by_category[category] = []
                by_category[category].append(candidate)

            lines.append("  By Category:")
            for category, candidates in sorted(by_category.items(), key=lambda x: sum(c.size_gb for c in x[1]), reverse=True):
                total = sum(c.size_gb for c in candidates)
                lines.append(f"    {category}: {total:.2f} GB ({len(candidates)} items)")

        if cleanup_results:
            lines.append("")
            lines.append("CLEANUP RESULTS:")
            successful = [r for r in cleanup_results if r.success]
            failed = [r for r in cleanup_results if not r.success]
            total_freed = sum(r.size_freed_bytes / (1024**3) for r in successful)

            lines.append(f"  Total Space Freed: {total_freed:.2f} GB")
            lines.append(f"  Successful: {len(successful)}")
            lines.append(f"  Failed: {len(failed)}")

            if failed:
                lines.append("")
                lines.append("  Failed Deletions:")
                for result in failed[:5]:  # Show first 5 failures
                    lines.append(f"    - {result.path}: {result.error}")

        lines.append("")
        lines.append("=" * 70)

        return "\n".join(lines)

    def _save_report(self, report: StorageReport) -> None:
        """Save report to disk."""
        filename = f"storage_report_{report.scan_date.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.reports_dir / filename

        # Convert to JSON-serializable dict
        report_dict = {
            'scan_date': report.scan_date.isoformat(),
            'total_disk_space_gb': report.total_disk_space_gb,
            'used_space_gb': report.used_space_gb,
            'free_space_gb': report.free_space_gb,
            'top_space_consumers': report.top_space_consumers,
            'cleanup_candidates': [
                {
                    'path': c.path,
                    'size_gb': c.size_gb,
                    'category': c.category.value,
                    'safety_level': c.safety_level.value,
                    'confidence': c.confidence,
                    'reason': c.reason,
                }
                for c in report.cleanup_candidates
            ],
            'historical_trend': report.historical_trend or []
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, indent=2)

        logger.info(f"Saved report to {filepath}")

    def _load_historical_trend(self) -> List[dict]:
        """Load historical reports for trend analysis."""
        trend = []

        # Load last 12 reports (roughly 6 months if running fortnightly)
        report_files = sorted(self.reports_dir.glob('storage_report_*.json'), reverse=True)[:12]

        for report_file in report_files:
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    trend.append({
                        'date': data['scan_date'],
                        'used_space_gb': data['used_space_gb'],
                        'free_space_gb': data['free_space_gb'],
                    })
            except Exception as e:
                logger.warning(f"Failed to load historical report {report_file}: {e}")

        return list(reversed(trend))  # Oldest first
```

**Deliverable**: Comprehensive reporting system with historical trends

---

## Phase 8: Autopack Executor Integration (CURSOR)

**Duration**: 2-3 hours
**Owner**: Cursor (modify existing executor)

### Objectives
1. Add storage optimization as a new phase type
2. Integrate with existing approval workflow
3. Add to autonomous executor scheduling
4. Database schema updates

### Tasks

#### Task 8.1: Add Storage Optimizer Phase Type
```python
# src/autopack/models.py (add new phase type)

class PhaseType(str, Enum):
    # ... existing phase types ...
    STORAGE_OPTIMIZATION = "storage_optimization"
```

#### Task 8.2: Create Storage Optimization Phase Handler
```python
# src/autopack/phases/storage_optimization_phase.py
"""
Storage optimization phase handler.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import logging

from autopack.storage_optimizer import (
    DiskScanner,
    FileClassifier,
    CleanupExecutor,
    StorageReporter,
    StorageOptimizerConfig,
)
from autopack.models import Phase, PhaseState
from autopack.database import SessionLocal

logger = logging.getLogger(__name__)

class StorageOptimizationPhase:
    """Execute storage optimization phase."""

    def __init__(self, phase: Phase, config: StorageOptimizerConfig):
        self.phase = phase
        self.config = config
        self.scanner = DiskScanner(config)
        self.classifier = FileClassifier(config)
        self.executor = CleanupExecutor(config)
        self.reporter = StorageReporter(config)

    def execute(self) -> Dict[str, Any]:
        """Execute storage optimization phase."""
        logger.info(f"Starting storage optimization phase: {self.phase.phase_id}")

        # Step 1: Scan disk
        logger.info("Scanning disk...")
        scan_results = self.scanner.scan(drive_letter="C", use_cache=False)

        # Step 2: Classify cleanup candidates
        logger.info("Classifying cleanup candidates...")
        candidates = self.classifier.classify_batch(scan_results)

        # Step 3: Create cleanup plan
        logger.info("Creating cleanup plan...")
        plan = self.executor.create_plan(candidates)

        # Step 4: Get disk space info
        import shutil
        disk_usage = shutil.disk_usage("C:\\")
        total_gb = disk_usage.total / (1024**3)
        used_gb = disk_usage.used / (1024**3)
        free_gb = disk_usage.free / (1024**3)

        # Step 5: Find top space consumers
        top_consumers = sorted(
            [{'path': r.path, 'size_gb': r.size_bytes / (1024**3)} for r in scan_results if r.is_folder],
            key=lambda x: x['size_gb'],
            reverse=True
        )[:20]

        # Step 6: Create report
        report = self.reporter.create_report(
            scan_date=datetime.now(),
            total_space_gb=total_gb,
            used_space_gb=used_gb,
            free_space_gb=free_gb,
            top_consumers=top_consumers,
            cleanup_candidates=candidates
        )

        # Step 7: Request approval for cleanup
        if plan.requires_approval_count > 0:
            logger.info(f"{plan.requires_approval_count} items require approval")
            # This would integrate with Autopack's approval system
            # For now, return pending status
            return {
                'status': 'pending_approval',
                'plan': plan,
                'report': report,
                'message': f"Found {len(candidates)} cleanup candidates totaling {plan.total_potential_savings_gb:.2f} GB"
            }

        # Step 8: Execute cleanup (auto-deletable only)
        logger.info("Executing cleanup...")
        results = self.executor.execute_plan(plan, dry_run=False)

        # Step 9: Generate summary
        summary = self.reporter.generate_summary(report, results)
        logger.info(f"\n{summary}")

        return {
            'status': 'complete',
            'results': results,
            'report': report,
            'summary': summary
        }
```

#### Task 8.3: Integrate with Autonomous Executor
```python
# src/autopack/autonomous_executor.py (add storage optimization)

def should_run_storage_optimization(self) -> bool:
    """Check if storage optimization should run."""
    # Run every 14 days
    last_run = self._get_last_storage_optimization_run()

    if not last_run:
        return True

    days_since_last = (datetime.now() - last_run).days
    return days_since_last >= 14

def run_storage_optimization(self):
    """Run storage optimization phase."""
    from autopack.phases.storage_optimization_phase import StorageOptimizationPhase
    from autopack.storage_optimizer.config import DEFAULT_CONFIG

    # Create phase
    phase = Phase(
        phase_id="storage_optimization",
        run_id=self.run_id,
        phase_type=PhaseType.STORAGE_OPTIMIZATION,
        state=PhaseState.EXECUTING,
        created_at=datetime.now()
    )

    # Execute
    handler = StorageOptimizationPhase(phase, DEFAULT_CONFIG)
    result = handler.execute()

    # Update phase state
    if result['status'] == 'complete':
        phase.state = PhaseState.COMPLETE
    elif result['status'] == 'pending_approval':
        phase.state = PhaseState.BLOCKED

    # Save to database
    session = SessionLocal()
    session.add(phase)
    session.commit()
    session.close()

    return result
```

**Deliverable**: Full integration with Autopack executor

---

## Phase 9: Testing & Validation (BOTH)

**Duration**: 3-4 hours
**Owner**: Autopack (unit tests) + Cursor (integration tests)

### Objectives
1. Unit tests for all components
2. Integration tests
3. Manual testing on real system
4. Performance benchmarks

### Tasks

#### Task 9.1: Unit Tests (AUTOPACK)
```python
# tests/autopack/storage_optimizer/test_classifier.py
"""
Unit tests for FileClassifier.
"""

import pytest
from datetime import datetime, timedelta
from autopack.storage_optimizer import FileClassifier, ScanResult
from autopack.storage_optimizer.config import DEFAULT_CONFIG

def test_classify_temp_files():
    """Test temp file classification."""
    classifier = FileClassifier(DEFAULT_CONFIG)

    # Old temp file should be candidate
    old_temp = ScanResult(
        path="C:\\Users\\test\\AppData\\Local\\Temp\\oldfile.txt",
        size_bytes=1024 * 1024,  # 1 MB
        modified=datetime.now() - timedelta(days=30),
        is_folder=False,
        attributes='-'
    )

    candidate = classifier.classify(old_temp)
    assert candidate is not None
    assert candidate.category.value == 'temp_files'
    assert candidate.safety_level.value == 'safe'

def test_classify_node_modules():
    """Test node_modules classification."""
    classifier = FileClassifier(DEFAULT_CONFIG)

    old_node_modules = ScanResult(
        path="C:\\dev\\old_project\\node_modules",
        size_bytes=500 * 1024 * 1024,  # 500 MB
        modified=datetime.now() - timedelta(days=90),
        is_folder=True,
        attributes='d'
    )

    candidate = classifier.classify(old_node_modules)
    assert candidate is not None
    assert candidate.category.value == 'dev_artifacts'
    assert candidate.safety_level.value == 'review'

# ... more tests ...
```

#### Task 9.2: Integration Tests (CURSOR)
```python
# tests/autopack/storage_optimizer/test_integration.py
"""
Integration tests for full storage optimization workflow.
"""

import pytest
from autopack.storage_optimizer import (
    DiskScanner,
    FileClassifier,
    CleanupExecutor,
    StorageReporter,
    DEFAULT_CONFIG
)

def test_full_workflow():
    """Test complete storage optimization workflow."""
    # Scan
    scanner = DiskScanner(DEFAULT_CONFIG)
    results = scanner.scan(drive_letter="C", use_cache=True)
    assert len(results) > 0

    # Classify
    classifier = FileClassifier(DEFAULT_CONFIG)
    candidates = classifier.classify_batch(results)

    # Plan
    executor = CleanupExecutor(DEFAULT_CONFIG)
    plan = executor.create_plan(candidates)
    assert plan.total_potential_savings_gb >= 0

    # Report
    reporter = StorageReporter(DEFAULT_CONFIG)
    # ... test reporting ...
```

**Deliverable**: Comprehensive test suite with >80% coverage

---

## Phase 10: Documentation (AUTOPACK)

**Duration**: 1-2 hours
**Owner**: Autopack (documentation generation)

### Objectives
1. User guide
2. API documentation
3. Configuration reference
4. Troubleshooting guide

### Tasks

#### Task 10.1: User Guide
Create `docs/guides/STORAGE_OPTIMIZER_USER_GUIDE.md`:
- Installation
- Quick start
- Configuration options
- Scheduling setup
- Understanding reports
- FAQ

#### Task 10.2: API Documentation
Create `docs/api/STORAGE_OPTIMIZER_API.md`:
- Module exports
- Class reference
- Method signatures
- Usage examples

**Deliverable**: Complete documentation suite

---

## Summary: Phase Ownership

### Cursor-Owned Phases (4 phases, ~9-11 hours)
1. **Phase 1**: Research & Prototyping (2-3 hours)
2. **Phase 3**: Scanner Wrapper (2-3 hours)
3. **Phase 8**: Autopack Executor Integration (2-3 hours)
4. **Phase 9 (partial)**: Integration Testing (2-3 hours)

**Total Cursor**: ~9-11 hours

### Autopack-Owned Phases (6 phases, ~11-14 hours)
1. **Phase 2**: Core Module Structure (1-2 hours)
2. **Phase 4**: Classification Engine (2-3 hours)
3. **Phase 5**: Cleanup Executor (2-3 hours)
4. **Phase 6**: Scheduler Integration (1-2 hours)
5. **Phase 7**: Reporting System (2-3 hours)
6. **Phase 9 (partial)**: Unit Testing (1-2 hours)
7. **Phase 10**: Documentation (1-2 hours)

**Total Autopack**: ~11-14 hours

---

## Rollout Plan

### Week 1: Foundation (Cursor)
- Phase 1: Research & Prototyping
- Deliverable: Working prototype, tool evaluation

### Week 2: Core Implementation (Autopack)
- Phase 2: Module structure
- Phase 4: Classification engine
- Phase 5: Cleanup executor
- Deliverable: Core functionality working

### Week 3: Advanced Features (Mix)
- Phase 3: Scanner wrapper (Cursor)
- Phase 6: Scheduler (Autopack)
- Phase 7: Reporting (Autopack)
- Deliverable: Full feature set

### Week 4: Integration & Polish (Mix)
- Phase 8: Executor integration (Cursor)
- Phase 9: Testing (Both)
- Phase 10: Documentation (Autopack)
- Deliverable: Production-ready system

---

## Success Criteria

1. **Functionality**:
   - ✅ Scans C: drive in <2 minutes
   - ✅ Identifies 10+ cleanup categories
   - ✅ Safely deletes with approval workflow
   - ✅ Runs on fortnightly schedule
   - ✅ Generates detailed reports

2. **Performance**:
   - ✅ Reclaims ≥10 GB per run on typical system
   - ✅ <5% false positives (safe files marked for deletion)
   - ✅ Zero data loss incidents

3. **Integration**:
   - ✅ Seamlessly integrates with Autopack executor
   - ✅ Uses existing database/telemetry
   - ✅ Follows Autopack phase patterns

4. **Usability**:
   - ✅ Simple CLI interface
   - ✅ Clear, actionable reports
   - ✅ Easy configuration

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Cursor starts Phase 1** (Research & Prototyping)
3. **Create project tracking** in Autopack database
4. **Set up monitoring** for fortnightly runs
5. **Begin implementation** following phase order

---

**Document Version**: 1.0
**Created**: 2026-01-01
**Status**: Ready for Implementation
