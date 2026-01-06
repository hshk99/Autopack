"""
Helper for writing phase proofs from autonomous_executor.

BUILD-161 Phase A: Intention-first loop integration.
BUILD-180: Added deterministic git-based metrics.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

from autopack.phase_proof import PhaseProof, PhaseChange, PhaseVerification, PhaseProofStorage
from autopack.proof_metrics import get_proof_metrics, ProofMetrics

logger = logging.getLogger(__name__)


def write_minimal_phase_proof(
    run_id: str,
    project_id: Optional[str],
    phase_id: str,
    success: bool,
    created_at: datetime,
    completed_at: datetime,
    error_summary: Optional[str] = None,
    workspace_root: Optional[Path] = None,
) -> None:
    """
    Write a minimal phase proof artifact (BUILD-161 Phase A, BUILD-180 metrics).

    This implementation writes bounded proof artifacts with deterministic
    git-based metrics when available (BUILD-180).

    Args:
        run_id: Run ID
        project_id: Project ID (optional)
        phase_id: Phase ID
        success: True if phase succeeded
        created_at: Phase start timestamp
        completed_at: Phase completion timestamp
        error_summary: Error summary if failed (max 500 chars)
        workspace_root: Workspace root for git metrics (optional)
    """
    try:
        duration_seconds = (completed_at - created_at).total_seconds()

        # BUILD-180: Get real metrics from git when workspace is available.
        # Direction: treat current working directory as the workspace by default
        # (executor runs inside the workspace). Callers may override explicitly.
        metrics = ProofMetrics(
            files_modified=0,
            changed_file_sample=[],
            metrics_placeholder=True,
        )

        metrics_workspace = workspace_root or Path.cwd()
        metrics = get_proof_metrics(metrics_workspace)
        logger.debug(
            f"[PhaseProof] Got metrics: files_modified={metrics.files_modified}, "
            f"placeholder={metrics.metrics_placeholder}"
        )

        # Build change summary
        if metrics.metrics_placeholder:
            change_summary = "Phase execution completed (git metrics unavailable)"
        else:
            file_list = ", ".join(metrics.changed_file_sample[:5])
            if len(metrics.changed_file_sample) > 5:
                file_list += f" (+{len(metrics.changed_file_sample) - 5} more)"
            change_summary = (
                f"Modified {metrics.files_modified} files: {file_list}"
                if file_list
                else "No files modified"
            )

        # Create proof with real or placeholder metrics
        proof = PhaseProof(
            proof_id=f"{run_id}-{phase_id}",
            run_id=run_id,
            phase_id=phase_id,
            created_at=created_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            changes=PhaseChange(
                files_created=0,  # Would need more instrumentation
                files_modified=metrics.files_modified,
                files_deleted=0,  # Would need more instrumentation
                key_changes=metrics.changed_file_sample[:10],
                change_summary=change_summary,
            ),
            verification=PhaseVerification(
                tests_passed=metrics.tests_passed,
                tests_failed=metrics.tests_failed,
                probes_executed=[],
                contracts_verified=[],
                verification_summary="Phase verification completed",
            ),
            success=success,
            error_summary=error_summary[:500] if error_summary else None,
            schema_version="1.0",
            metrics_placeholder=metrics.metrics_placeholder,
        )

        PhaseProofStorage.save_proof(proof)
        logger.info(
            f"[PhaseProof] Wrote proof for {phase_id}: success={success}, "
            f"duration={duration_seconds:.1f}s, files_modified={metrics.files_modified}, "
            f"placeholder={metrics.metrics_placeholder}"
        )

    except Exception as e:
        # Phase proof writing is best-effort and should never fail the phase
        logger.warning(f"[PhaseProof] Failed to write proof for {phase_id} (non-fatal): {e}")
