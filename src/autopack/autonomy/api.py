"""Autopilot library API (BUILD-179).

Provides a thin library façade for the autopilot controller, suitable for CLI
wrappers and programmatic use. All business logic remains in autopilot.py.

Usage:
    from autopack.autonomy.api import run_autopilot

    result = run_autopilot(
        run_id="my-run",
        project_id="autopack",
        enabled=True,
        write_artifact=True,
    )
    print(result.session.status)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..file_layout import RunFileLayout
from ..intention_anchor.v2 import IntentionAnchorV2
from .autopilot import AutopilotController
from .models import AutopilotSessionV1

logger = logging.getLogger(__name__)


@dataclass
class AutopilotResult:
    """Result of an autopilot session."""

    session: AutopilotSessionV1
    """The autopilot session with execution results."""

    artifact_path: Optional[Path] = None
    """Path to saved artifact, if write_artifact=True."""

    @property
    def status(self) -> str:
        """Session status (e.g., 'completed', 'disabled', 'failed')."""
        return self.session.status

    @property
    def is_disabled(self) -> bool:
        """True if autopilot was not enabled."""
        return self.session.status == "disabled"

    @property
    def executed_count(self) -> int:
        """Number of actions executed."""
        if self.session.execution_summary:
            return self.session.execution_summary.executed_actions
        return 0

    @property
    def successful_count(self) -> int:
        """Number of successful actions."""
        if self.session.execution_summary:
            return self.session.execution_summary.successful_actions
        return 0

    @property
    def failed_count(self) -> int:
        """Number of failed actions."""
        if self.session.execution_summary:
            return self.session.execution_summary.failed_actions
        return 0

    @property
    def approval_requests_count(self) -> int:
        """Number of actions requiring approval."""
        return len(self.session.approval_requests)


def load_anchor(
    *,
    run_id: str,
    project_id: str,
    anchor_path: Optional[Path] = None,
) -> IntentionAnchorV2:
    """Load an intention anchor for a run.

    Args:
        run_id: Run identifier.
        project_id: Project identifier.
        anchor_path: Explicit path to anchor file (auto-detects if None).

    Returns:
        Loaded IntentionAnchorV2.

    Raises:
        FileNotFoundError: If anchor file doesn't exist.
    """
    layout = RunFileLayout(run_id=run_id, project_id=project_id)

    if anchor_path is None:
        anchor_path = layout.base_dir / "intention_v2.json"

    if not anchor_path.exists():
        raise FileNotFoundError(
            f"Intention anchor not found: {anchor_path}. "
            "Create an anchor first or specify anchor_path."
        )

    logger.info(f"Loading intention anchor from: {anchor_path}")
    return IntentionAnchorV2.load_from_file(anchor_path)


def run_autopilot(
    *,
    run_id: str,
    project_id: str,
    workspace_root: Optional[Path] = None,
    anchor_path: Optional[Path] = None,
    enabled: bool = False,
    write_artifact: bool = False,
) -> AutopilotResult:
    """Run an autopilot session.

    This is the primary library API for autopilot execution. By default,
    autopilot is DISABLED (safe-by-default). Pass enabled=True to actually
    execute actions.

    Args:
        run_id: Run identifier.
        project_id: Project identifier.
        workspace_root: Workspace root directory (default: cwd).
        anchor_path: Path to intention anchor v2 JSON (auto-detects if None).
        enabled: REQUIRED to be True for actual execution (default: False).
        write_artifact: If True, write session to run-local artifact.

    Returns:
        AutopilotResult with the session and optional artifact path.

    Raises:
        FileNotFoundError: If anchor not found.
        RuntimeError: If controller encounters an error.
    """
    workspace = (workspace_root or Path.cwd()).resolve()

    # Load anchor
    anchor = load_anchor(
        run_id=run_id,
        project_id=project_id,
        anchor_path=anchor_path,
    )

    if not enabled:
        logger.warning("Autopilot is DISABLED by default (dry-run mode).")
        logger.warning("Use enabled=True to execute actions.")

    # Create controller
    controller = AutopilotController(
        workspace_root=workspace,
        project_id=project_id,
        run_id=run_id,
        enabled=enabled,
    )

    # Run session
    logger.info("Starting autopilot session...")
    session = controller.run_session(anchor)

    logger.info(f"Session {session.session_id}: {session.status}")

    if session.execution_summary:
        summary = session.execution_summary
        logger.info(
            f"Executed {summary.executed_actions}/{summary.total_actions} actions "
            f"({summary.successful_actions} successful, {summary.failed_actions} failed)"
        )

    if session.approval_requests:
        logger.info(f"{len(session.approval_requests)} action(s) require approval")

    artifact_path = None
    if write_artifact:
        artifact_path = controller.save_session()
        logger.info(f"Wrote session: {artifact_path}")

    return AutopilotResult(session=session, artifact_path=artifact_path)
