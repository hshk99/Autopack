"""Plan proposer library API (BUILD-179).

Provides a thin library façade for the plan proposer, suitable for CLI wrappers
and programmatic use. All business logic remains in plan_proposer.py.

Usage:
    from autopack.planning.api import propose_plan_from_files

    result = propose_plan_from_files(
        run_id="my-run",
        project_id="autopack",
        workspace_root=Path.cwd(),
        write_artifact=True,
    )
    print(result.proposal.summary)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..file_layout import RunFileLayout
from ..gaps.models import GapReportV1
from ..intention_anchor.v2 import IntentionAnchorV2
from .models import PlanProposalV1
from .plan_proposer import propose_plan

logger = logging.getLogger(__name__)


@dataclass
class PlanProposalResult:
    """Result of a plan proposal operation."""

    proposal: PlanProposalV1
    """The generated plan proposal."""

    artifact_path: Optional[Path] = None
    """Path to saved artifact, if write_artifact=True."""

    @property
    def total_actions(self) -> int:
        """Total number of proposed actions."""
        return self.proposal.summary.total_actions

    @property
    def auto_approved_count(self) -> int:
        """Number of actions that can be auto-approved."""
        return self.proposal.summary.auto_approved_actions

    @property
    def requires_approval_count(self) -> int:
        """Number of actions requiring manual approval."""
        return self.proposal.summary.requires_approval_actions

    @property
    def blocked_count(self) -> int:
        """Number of blocked actions."""
        return self.proposal.summary.blocked_actions


def propose_plan_from_files(
    *,
    run_id: str,
    project_id: str,
    workspace_root: Optional[Path] = None,
    anchor_path: Optional[Path] = None,
    gap_report_path: Optional[Path] = None,
    write_artifact: bool = False,
) -> PlanProposalResult:
    """Propose plan from anchor and gap report files.

    This is the primary library API for plan proposal. It loads artifacts
    from standard locations (or specified paths) and proposes a plan.

    Args:
        run_id: Run identifier for artifact paths.
        project_id: Project identifier.
        workspace_root: Workspace root directory (default: cwd).
        anchor_path: Path to intention anchor v2 JSON (auto-detects if None).
        gap_report_path: Path to gap report v1 JSON (auto-detects if None).
        write_artifact: If True, write plan proposal to run-local artifact.

    Returns:
        PlanProposalResult with the proposal and optional artifact path.

    Raises:
        FileNotFoundError: If anchor or gap report not found.
        pydantic.ValidationError: If proposal fails schema validation.
    """
    workspace = (workspace_root or Path.cwd()).resolve()
    layout = RunFileLayout(run_id=run_id, project_id=project_id)

    # Load intention anchor v2
    if anchor_path is None:
        anchor_path = layout.base_dir / "intention_v2.json"

    if not anchor_path.exists():
        raise FileNotFoundError(
            f"Intention anchor not found: {anchor_path}. "
            "Create an anchor first or specify anchor_path."
        )

    logger.info(f"Loading intention anchor from: {anchor_path}")
    anchor = IntentionAnchorV2.load_from_file(anchor_path)

    # Load gap report v1
    if gap_report_path is None:
        gap_report_path = layout.base_dir / "gaps" / "gap_report_v1.json"

    if not gap_report_path.exists():
        raise FileNotFoundError(
            f"Gap report not found: {gap_report_path}. "
            "Run gap scanner first or specify gap_report_path."
        )

    logger.info(f"Loading gap report from: {gap_report_path}")
    gap_report = GapReportV1.load_from_file(gap_report_path)

    # Propose plan
    logger.info("Proposing plan...")
    proposal = propose_plan(
        anchor=anchor,
        gap_report=gap_report,
        workspace_root=workspace,
    )

    # Validate against schema
    proposal.validate_against_schema()

    logger.info(
        f"Generated {proposal.summary.total_actions} actions "
        f"({proposal.summary.auto_approved_actions} auto-approved, "
        f"{proposal.summary.requires_approval_actions} require approval, "
        f"{proposal.summary.blocked_actions} blocked)"
    )

    artifact_path = None
    if write_artifact:
        layout.ensure_directories()

        planning_dir = layout.base_dir / "planning"
        planning_dir.mkdir(exist_ok=True)

        artifact_path = planning_dir / "plan_proposal_v1.json"
        proposal.save_to_file(artifact_path)
        logger.info(f"Wrote plan proposal: {artifact_path}")

    return PlanProposalResult(proposal=proposal, artifact_path=artifact_path)
