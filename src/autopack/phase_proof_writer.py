"""
Helper for writing phase proofs from autonomous_executor.

BUILD-161 Phase A: Intention-first loop integration.
"""

from datetime import datetime
from typing import Optional
import logging

from autopack.phase_proof import PhaseProof, PhaseChange, PhaseVerification, PhaseProofStorage

logger = logging.getLogger(__name__)


def write_minimal_phase_proof(
    run_id: str,
    project_id: Optional[str],
    phase_id: str,
    success: bool,
    created_at: datetime,
    completed_at: datetime,
    error_summary: Optional[str] = None,
) -> None:
    """
    Write a minimal phase proof artifact (BUILD-161 Phase A).

    This is a minimal implementation that writes bounded proof artifacts
    without full change/verification tracking (which would require more
    extensive executor instrumentation).

    Future enhancements can add detailed metrics (files changed, tests run, etc.).

    Args:
        run_id: Run ID
        project_id: Project ID (optional)
        phase_id: Phase ID
        success: True if phase succeeded
        created_at: Phase start timestamp
        completed_at: Phase completion timestamp
        error_summary: Error summary if failed (max 500 chars)
    """
    try:
        duration_seconds = (completed_at - created_at).total_seconds()

        # Create minimal proof with placeholder metrics
        # TODO: Enhance with real change tracking when executor instrumentation is added
        proof = PhaseProof(
            proof_id=f"{run_id}-{phase_id}",
            run_id=run_id,
            phase_id=phase_id,
            created_at=created_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            changes=PhaseChange(
                files_created=0,  # TODO: Track actual file changes
                files_modified=0,
                files_deleted=0,
                key_changes=[],
                change_summary="Phase execution completed (detailed change tracking not yet instrumented)",
            ),
            verification=PhaseVerification(
                tests_passed=0,  # TODO: Track actual test results
                tests_failed=0,
                probes_executed=[],
                contracts_verified=[],
                verification_summary="Phase verification completed (detailed verification tracking not yet instrumented)",
            ),
            success=success,
            error_summary=error_summary[:500] if error_summary else None,
            schema_version="1.0",
            metrics_placeholder=True,  # Mark placeholder metrics explicitly
        )

        PhaseProofStorage.save_proof(proof)
        logger.info(
            f"[PhaseProof] Wrote proof for {phase_id}: success={success}, duration={duration_seconds:.1f}s"
        )

    except Exception as e:
        # Phase proof writing is best-effort and should never fail the phase
        logger.warning(f"[PhaseProof] Failed to write proof for {phase_id} (non-fatal): {e}")
