"""Gap scanner library API (BUILD-179).

Provides a thin library façade for the gap scanner, suitable for CLI wrappers
and programmatic use. All business logic remains in scanner.py.

Usage:
    from autopack.gaps.api import scan_gaps

    result = scan_gaps(
        run_id="my-run",
        project_id="autopack",
        workspace_root=Path.cwd(),
        write_artifact=True,
    )
    print(result.report.summary)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..file_layout import RunFileLayout
from .models import GapReportV1
from .scanner import scan_workspace

logger = logging.getLogger(__name__)


@dataclass
class GapScanResult:
    """Result of a gap scan operation."""

    report: GapReportV1
    """The generated gap report."""

    artifact_path: Optional[Path] = None
    """Path to saved artifact, if write_artifact=True."""

    @property
    def total_gaps(self) -> int:
        """Total number of gaps found."""
        return self.report.summary.total_gaps

    @property
    def has_blockers(self) -> bool:
        """True if any gaps block autopilot execution."""
        return self.report.summary.autopilot_blockers > 0


def scan_gaps(
    *,
    run_id: str,
    project_id: str,
    workspace_root: Optional[Path] = None,
    write_artifact: bool = False,
) -> GapScanResult:
    """Scan workspace for gaps (deterministic).

    This is the primary library API for gap scanning. It wraps the GapScanner
    with standard parameters and optional artifact writing.

    Args:
        run_id: Run identifier for artifact paths.
        project_id: Project identifier.
        workspace_root: Workspace root directory (default: cwd).
        write_artifact: If True, write gap report to run-local artifact.

    Returns:
        GapScanResult with the report and optional artifact path.

    Raises:
        ValueError: If workspace_root doesn't exist.
        pydantic.ValidationError: If report fails schema validation.
    """
    workspace = (workspace_root or Path.cwd()).resolve()

    if not workspace.exists():
        raise ValueError(f"Workspace root does not exist: {workspace}")

    logger.info(f"Scanning workspace: {workspace}")

    # Scan workspace
    report = scan_workspace(
        workspace_root=workspace,
        project_id=project_id,
        run_id=run_id,
    )

    # Validate against schema
    report.validate_against_schema()

    logger.info(
        f"Found {report.summary.total_gaps} gaps ({report.summary.autopilot_blockers} blockers)"
    )

    artifact_path = None
    if write_artifact:
        layout = RunFileLayout(run_id=run_id, project_id=project_id)
        layout.ensure_directories()

        gaps_dir = layout.base_dir / "gaps"
        gaps_dir.mkdir(exist_ok=True)

        artifact_path = gaps_dir / "gap_report_v1.json"
        report.save_to_file(artifact_path)
        logger.info(f"Wrote gap report: {artifact_path}")

    return GapScanResult(report=report, artifact_path=artifact_path)
