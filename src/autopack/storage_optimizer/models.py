"""
Core data models for Storage Optimizer.

Defines the data structures for scan results, cleanup candidates,
and storage reports.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ScanResult:
    """Result of scanning a single file or directory."""

    path: str
    size_bytes: int
    modified: datetime
    is_folder: bool
    attributes: str = "-"

    @property
    def size_mb(self) -> float:
        """Size in megabytes."""
        return self.size_bytes / (1024 * 1024)

    @property
    def size_gb(self) -> float:
        """Size in gigabytes."""
        return self.size_bytes / (1024 * 1024 * 1024)

    @property
    def age_days(self) -> int:
        """Age in days since last modification."""
        return (datetime.now() - self.modified).days


@dataclass
class CleanupCandidate:
    """A file or directory that could potentially be cleaned up."""

    path: str
    category: str
    size_bytes: int
    age_days: int
    reason: str
    can_auto_delete: bool = False
    requires_approval: bool = True
    modified: Optional[datetime] = None

    @property
    def size_mb(self) -> float:
        """Size in megabytes."""
        return self.size_bytes / (1024 * 1024)

    @property
    def size_gb(self) -> float:
        """Size in gigabytes."""
        return self.size_bytes / (1024 * 1024 * 1024)


@dataclass
class CleanupPlan:
    """Collection of cleanup candidates organized by category."""

    candidates: List[CleanupCandidate] = field(default_factory=list)
    total_size_bytes: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def total_size_gb(self) -> float:
        """Total potential savings in gigabytes."""
        return self.total_size_bytes / (1024 * 1024 * 1024)

    @property
    def candidates_by_category(self) -> dict:
        """Group candidates by category."""
        by_category = {}
        for candidate in self.candidates:
            if candidate.category not in by_category:
                by_category[candidate.category] = []
            by_category[candidate.category].append(candidate)
        return by_category

    @property
    def size_by_category(self) -> dict:
        """Total size by category in bytes."""
        by_category = {}
        for candidate in self.candidates:
            if candidate.category not in by_category:
                by_category[candidate.category] = 0
            by_category[candidate.category] += candidate.size_bytes
        return by_category

    def add_candidate(self, candidate: CleanupCandidate) -> None:
        """Add a cleanup candidate to the plan."""
        self.candidates.append(candidate)
        self.total_size_bytes += candidate.size_bytes


@dataclass
class StorageReport:
    """
    Complete storage analysis report.

    Includes disk usage, top space consumers, cleanup opportunities,
    and policy enforcement summary.
    """

    scan_date: datetime
    drive_letter: str
    total_space_bytes: int
    used_space_bytes: int
    free_space_bytes: int

    # Scan results
    total_files_scanned: int = 0
    total_folders_scanned: int = 0
    top_consumers: List[ScanResult] = field(default_factory=list)

    # Cleanup plan
    cleanup_plan: Optional[CleanupPlan] = None

    # Policy enforcement
    protected_paths_found: List[str] = field(default_factory=list)
    protected_size_bytes: int = 0

    @property
    def total_space_gb(self) -> float:
        """Total disk space in GB."""
        return self.total_space_bytes / (1024 * 1024 * 1024)

    @property
    def used_space_gb(self) -> float:
        """Used disk space in GB."""
        return self.used_space_bytes / (1024 * 1024 * 1024)

    @property
    def free_space_gb(self) -> float:
        """Free disk space in GB."""
        return self.free_space_bytes / (1024 * 1024 * 1024)

    @property
    def used_percentage(self) -> float:
        """Percentage of disk space used."""
        if self.total_space_bytes == 0:
            return 0.0
        return (self.used_space_bytes / self.total_space_bytes) * 100

    @property
    def protected_size_gb(self) -> float:
        """Protected space in GB."""
        return self.protected_size_bytes / (1024 * 1024 * 1024)
