"""Run checkpoint module for git-based rollback support.

Extracted from autonomous_executor.py for PR-EXE-4.
Provides git checkpoint creation and rollback for:
- Creating pre-run checkpoints (branch + commit SHA)
- Rolling back entire runs to pre-run state
- Audit trail logging for rollback actions

Uses RunFileLayout for audit log persistence.
"""

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RunCheckpoint:
    """Represents a git checkpoint for a run.

    Stores the branch name and commit SHA at the time the checkpoint was created.
    Used to restore the repository to its pre-run state if rollback is needed.
    """
    branch: str
    commit: str
    created_at: datetime

    def short_commit(self) -> str:
        """Return abbreviated commit SHA (first 8 characters)."""
        return self.commit[:8] if self.commit else "unknown"


@dataclass
class CheckpointResult:
    """Result of a checkpoint operation.

    Attributes:
        success: Whether the operation succeeded
        checkpoint: The created checkpoint (if success)
        error: Error message (if failed)
    """
    success: bool
    checkpoint: Optional[RunCheckpoint] = None
    error: Optional[str] = None


@dataclass
class RollbackResult:
    """Result of a rollback operation.

    Attributes:
        success: Whether the rollback succeeded
        error: Error message (if failed)
        clean_failed: Whether git clean failed (non-fatal)
        branch_failed: Whether branch checkout failed (non-fatal)
    """
    success: bool
    error: Optional[str] = None
    clean_failed: bool = False
    branch_failed: bool = False


def create_run_checkpoint(workspace: Path) -> CheckpointResult:
    """Create a git checkpoint before run execution starts.

    [Phase C5] Branch-based rollback support for Doctor rollback_run action.

    Stores current branch name and commit SHA so we can rollback the entire
    run if Doctor determines the run should be abandoned.

    Args:
        workspace: Path to the git repository workspace

    Returns:
        CheckpointResult with checkpoint data on success, error on failure
    """
    try:
        # Get current branch name
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if branch_result.returncode != 0:
            error_msg = branch_result.stderr.strip()
            logger.warning(f"[RunCheckpoint] Failed to get current branch: {error_msg}")
            return CheckpointResult(
                success=False,
                error=f"git_branch_failed: {error_msg}",
            )

        current_branch = branch_result.stdout.strip()

        # Get current commit SHA
        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if commit_result.returncode != 0:
            error_msg = commit_result.stderr.strip()
            logger.warning(f"[RunCheckpoint] Failed to get current commit: {error_msg}")
            return CheckpointResult(
                success=False,
                error=f"git_commit_failed: {error_msg}",
            )

        current_commit = commit_result.stdout.strip()

        # Create checkpoint
        checkpoint = RunCheckpoint(
            branch=current_branch,
            commit=current_commit,
            created_at=datetime.utcnow(),
        )

        logger.info(
            f"[RunCheckpoint] Created run checkpoint: branch={current_branch}, "
            f"commit={checkpoint.short_commit()}"
        )
        return CheckpointResult(success=True, checkpoint=checkpoint)

    except subprocess.TimeoutExpired:
        logger.warning("[RunCheckpoint] Timeout creating run checkpoint")
        return CheckpointResult(success=False, error="git_timeout")
    except Exception as e:
        logger.warning(f"[RunCheckpoint] Exception creating run checkpoint: {e}")
        return CheckpointResult(success=False, error=f"exception: {str(e)}")


def rollback_to_checkpoint(
    workspace: Path,
    checkpoint: RunCheckpoint,
    reason: str,
) -> RollbackResult:
    """Rollback entire run to pre-run checkpoint.

    [Phase C5] Implements Doctor rollback_run action support.

    Resets working tree to the commit/branch that existed before run started.
    This is a destructive operation that discards all patches applied during the run.

    Args:
        workspace: Path to the git repository workspace
        checkpoint: The checkpoint to rollback to
        reason: Reason for rollback (for logging/audit)

    Returns:
        RollbackResult with success status and any non-fatal warnings
    """
    if not checkpoint.commit:
        logger.error("[RunCheckpoint] No checkpoint commit set - cannot rollback run")
        return RollbackResult(success=False, error="no_checkpoint_commit")

    clean_failed = False
    branch_failed = False

    try:
        logger.warning(
            f"[RunCheckpoint] Rolling back entire run to checkpoint: {checkpoint.short_commit()}"
        )
        logger.warning(f"[RunCheckpoint] Reason: {reason}")

        # Reset to checkpoint commit (hard reset discards all changes)
        reset_result = subprocess.run(
            ["git", "reset", "--hard", checkpoint.commit],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if reset_result.returncode != 0:
            error_msg = reset_result.stderr.strip()
            logger.error(f"[RunCheckpoint] Failed to reset to checkpoint: {error_msg}")
            return RollbackResult(success=False, error=f"git_reset_failed: {error_msg}")

        # Clean untracked files (same as RollbackManager safe clean logic)
        clean_result = subprocess.run(
            ["git", "clean", "-fd"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if clean_result.returncode != 0:
            error_msg = clean_result.stderr.strip()
            logger.warning(f"[RunCheckpoint] Failed to clean untracked files: {error_msg}")
            clean_failed = True
            # Non-fatal - reset succeeded

        # If we were on a named branch, try to return to it
        if checkpoint.branch and checkpoint.branch != "HEAD":
            checkout_result = subprocess.run(
                ["git", "checkout", checkpoint.branch],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if checkout_result.returncode != 0:
                logger.warning(
                    f"[RunCheckpoint] Could not return to branch {checkpoint.branch}"
                )
                branch_failed = True
                # Non-fatal - we're at the right commit

        logger.info("[RunCheckpoint] Successfully rolled back run to pre-run state")

        return RollbackResult(
            success=True,
            clean_failed=clean_failed,
            branch_failed=branch_failed,
        )

    except subprocess.TimeoutExpired:
        logger.error("[RunCheckpoint] Timeout rolling back to run checkpoint")
        return RollbackResult(success=False, error="git_timeout")
    except Exception as e:
        logger.error(f"[RunCheckpoint] Exception during run rollback: {e}")
        return RollbackResult(success=False, error=f"exception: {str(e)}")


def log_run_rollback_action(
    run_id: str,
    checkpoint: RunCheckpoint,
    reason: str,
    project_id: Optional[str] = None,
) -> bool:
    """Log run rollback action to audit file.

    [Phase C5] Audit trail for run-level rollbacks.

    Args:
        run_id: The run identifier
        checkpoint: The checkpoint that was rolled back to
        reason: Reason for rollback
        project_id: Optional project identifier for file layout

    Returns:
        True if logging succeeded, False otherwise
    """
    try:
        # Import here to avoid circular import
        from autopack.file_layout import RunFileLayout

        layout = RunFileLayout(run_id, project_id=project_id)
        layout.ensure_directories()

        rollback_log = layout.base_dir / "run_rollback.log"

        timestamp = datetime.utcnow().isoformat()
        log_entry = (
            f"{timestamp} | Run: {run_id} | "
            f"Checkpoint: {checkpoint.short_commit()} | "
            f"Reason: {reason}\n"
        )

        with open(rollback_log, "a", encoding="utf-8") as f:
            f.write(log_entry)

        logger.info(f"[RunCheckpoint] Logged run rollback to {rollback_log}")
        return True

    except Exception as e:
        logger.warning(f"[RunCheckpoint] Failed to write run rollback audit log: {e}")
        return False


def perform_full_rollback(
    workspace: Path,
    checkpoint: RunCheckpoint,
    reason: str,
    run_id: str,
    project_id: Optional[str] = None,
) -> RollbackResult:
    """Perform a full rollback with audit logging.

    Combines rollback_to_checkpoint and log_run_rollback_action into a single
    operation for convenience.

    Args:
        workspace: Path to the git repository workspace
        checkpoint: The checkpoint to rollback to
        reason: Reason for rollback
        run_id: The run identifier for audit logging
        project_id: Optional project identifier for file layout

    Returns:
        RollbackResult from the rollback operation
    """
    result = rollback_to_checkpoint(workspace, checkpoint, reason)

    if result.success:
        # Log the rollback action (best-effort, don't fail if logging fails)
        log_run_rollback_action(run_id, checkpoint, reason, project_id)

    return result
