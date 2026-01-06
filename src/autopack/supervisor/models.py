"""Supervisor models (BUILD-179).

Typed result models for supervisor operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RunResult:
    """Result of a single autonomous run execution."""

    run_id: str
    """Run identifier."""

    success: bool
    """True if run completed successfully."""

    exit_code: int
    """Process exit code."""

    workspace: Optional[Path] = None
    """Workspace path used for this run."""

    stdout: str = ""
    """Standard output from the run."""

    stderr: str = ""
    """Standard error from the run."""

    error: Optional[str] = None
    """Error message if run failed."""


@dataclass
class SupervisorResult:
    """Result of a parallel supervisor execution."""

    run_results: Dict[str, RunResult] = field(default_factory=dict)
    """Map of run_id to individual run results."""

    @property
    def total_runs(self) -> int:
        """Total number of runs attempted."""
        return len(self.run_results)

    @property
    def successful_runs(self) -> int:
        """Number of successful runs."""
        return sum(1 for r in self.run_results.values() if r.success)

    @property
    def failed_runs(self) -> int:
        """Number of failed runs."""
        return self.total_runs - self.successful_runs

    @property
    def all_successful(self) -> bool:
        """True if all runs completed successfully."""
        return all(r.success for r in self.run_results.values())

    def get_failed_run_ids(self) -> List[str]:
        """Get list of run IDs that failed."""
        return [run_id for run_id, r in self.run_results.items() if not r.success]

    def get_successful_run_ids(self) -> List[str]:
        """Get list of run IDs that succeeded."""
        return [run_id for run_id, r in self.run_results.items() if r.success]
