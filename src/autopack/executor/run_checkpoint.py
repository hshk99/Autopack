"""
Run checkpoint and rollback management.

[Phase C5 / PR-EXE-4] Extracted from autonomous_executor.py.

This module provides git-based checkpoint and rollback operations for:
- Run-level checkpoints (saves branch/commit before run starts)
- Rollback to pre-run state (Doctor's rollback_run action)
- Audit logging for rollback actions
- Checkpoint listing and management

All git subprocess calls are consolidated here for testability.
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def create_checkpoint(run_id: str, phase_id: str, message: str) -> str:
    """
    Create a git tag savepoint for checkpoint/rollback.

    Note: This function creates a lightweight git tag at the current HEAD.
    For tag-based checkpoints, the caller should ensure changes are committed first.

    Args:
        run_id: Unique identifier for the run
        phase_id: Phase identifier
        message: Human-readable message (unused in tag name but logged)

    Returns:
        Tag name if successful, empty string on failure
    """
    try:
        # Generate deterministic tag name
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        tag_name = f"autopack-{run_id}-{phase_id}-{timestamp}"

        # Create lightweight tag at current HEAD
        # Note: workspace/cwd should be passed as parameter in actual usage
        # This is a simplified version - actual implementation should accept workspace
        result = subprocess.run(
            ["git", "tag", tag_name],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning(f"[Checkpoint] Failed to create tag {tag_name}: {result.stderr}")
            return ""

        logger.info(f"[Checkpoint] Created tag: {tag_name}")
        return tag_name

    except subprocess.TimeoutExpired:
        logger.warning("[Checkpoint] Timeout creating git tag")
        return ""
    except Exception as e:
        logger.warning(f"[Checkpoint] Exception creating checkpoint: {e}")
        return ""


def rollback_to_checkpoint(checkpoint_id: str, workspace: Path) -> bool:
    """
    Roll back working tree to a specific checkpoint (git tag or commit).

    This performs a hard reset to the checkpoint, discarding all uncommitted changes.

    Args:
        checkpoint_id: Git tag name or commit SHA to rollback to
        workspace: Path to the git repository

    Returns:
        True if rollback succeeded, False otherwise
    """
    if not checkpoint_id:
        logger.error("[Checkpoint] Cannot rollback: no checkpoint_id provided")
        return False

    try:
        workspace = Path(workspace).resolve()

        # Hard reset to checkpoint
        reset_result = subprocess.run(
            ["git", "reset", "--hard", checkpoint_id],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if reset_result.returncode != 0:
            logger.error(f"[Checkpoint] Failed to reset to {checkpoint_id}: {reset_result.stderr}")
            return False

        logger.info(f"[Checkpoint] Successfully reset to {checkpoint_id}")
        return True

    except subprocess.TimeoutExpired:
        logger.error("[Checkpoint] Timeout during git reset")
        return False
    except Exception as e:
        logger.error(f"[Checkpoint] Exception during rollback: {e}")
        return False


def write_audit_log(run_id: str, phase_id: str, action: str, details: dict) -> bool:
    """
    Write checkpoint/rollback action to audit log.

    Args:
        run_id: Unique identifier for the run
        phase_id: Phase identifier (can be empty for run-level actions)
        action: Action performed (e.g., "checkpoint_created", "rollback_executed")
        details: Additional details (checkpoint_id, reason, etc.)

    Returns:
        True if log written successfully, False otherwise
    """
    try:
        # Import here to avoid circular dependencies
        from autopack.file_layout import RunFileLayout

        layout = RunFileLayout(run_id, project_id=details.get("project_id"))
        layout.ensure_directories()

        audit_log = layout.base_dir / "checkpoint_audit.log"

        timestamp = datetime.utcnow().isoformat()
        checkpoint_id = details.get("checkpoint_id", "unknown")
        reason = details.get("reason", "")

        log_entry = (
            f"{timestamp} | Run: {run_id} | Phase: {phase_id} | "
            f"Action: {action} | Checkpoint: {checkpoint_id}"
        )
        if reason:
            log_entry += f" | Reason: {reason}"
        log_entry += "\n"

        with open(audit_log, "a", encoding="utf-8") as f:
            f.write(log_entry)

        logger.debug(f"[Checkpoint] Audit log written to {audit_log}")
        return True

    except Exception as e:
        logger.warning(f"[Checkpoint] Failed to write audit log: {e}")
        return False


def list_checkpoints(run_id: str, workspace: Path) -> List[str]:
    """
    List available checkpoints (git tags) for a specific run.

    Args:
        run_id: Unique identifier for the run
        workspace: Path to the git repository

    Returns:
        List of checkpoint tag names matching the run_id prefix
    """
    try:
        workspace = Path(workspace).resolve()

        # List all tags
        result = subprocess.run(
            ["git", "tag", "-l", f"autopack-{run_id}-*"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning(f"[Checkpoint] Failed to list tags: {result.stderr}")
            return []

        # Parse tag names
        tags = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return tags

    except subprocess.TimeoutExpired:
        logger.warning("[Checkpoint] Timeout listing git tags")
        return []
    except Exception as e:
        logger.warning(f"[Checkpoint] Exception listing checkpoints: {e}")
        return []


def create_run_checkpoint(
    workspace: Path,
) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Create a run-level checkpoint before execution starts.

    [Phase C5] Stores current branch name and commit SHA for rollback support.
    This is used by Doctor's rollback_run action to revert the entire run.

    Args:
        workspace: Path to the git repository

    Returns:
        Tuple of (success, branch_name, commit_sha, error_message)
        - success: True if checkpoint created successfully
        - branch_name: Current branch name (or "HEAD" if detached)
        - commit_sha: Current commit SHA
        - error_message: Error message if failed, None otherwise
    """
    try:
        workspace = Path(workspace).resolve()

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
            return False, None, None, f"git_branch_failed: {error_msg}"

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
            return False, None, None, f"git_commit_failed: {error_msg}"

        current_commit = commit_result.stdout.strip()

        logger.info(
            f"[RunCheckpoint] Created run checkpoint: branch={current_branch}, commit={current_commit[:8]}"
        )
        return True, current_branch, current_commit, None

    except subprocess.TimeoutExpired:
        logger.warning("[RunCheckpoint] Timeout creating run checkpoint")
        return False, None, None, "git_timeout"
    except Exception as e:
        logger.warning(f"[RunCheckpoint] Exception creating run checkpoint: {e}")
        return False, None, None, f"exception: {str(e)}"


def rollback_to_run_checkpoint(
    workspace: Path,
    checkpoint_branch: Optional[str],
    checkpoint_commit: str,
    reason: str,
) -> Tuple[bool, Optional[str]]:
    """
    Rollback entire run to pre-run checkpoint.

    [Phase C5] Implements Doctor rollback_run action support.
    Resets working tree to the commit/branch that existed before run started.
    This is a destructive operation that discards all patches applied during the run.

    Args:
        workspace: Path to the git repository
        checkpoint_branch: Branch name to return to (or None if detached HEAD)
        checkpoint_commit: Commit SHA to reset to
        reason: Reason for rollback (for logging)

    Returns:
        Tuple of (success, error_message)
    """
    if not checkpoint_commit:
        logger.error("[RunCheckpoint] No checkpoint commit set - cannot rollback run")
        return False, "no_checkpoint_commit"

    try:
        workspace = Path(workspace).resolve()

        logger.warning(
            f"[RunCheckpoint] Rolling back entire run to checkpoint: {checkpoint_commit[:8]}"
        )
        logger.warning(f"[RunCheckpoint] Reason: {reason}")

        # Reset to checkpoint commit (hard reset discards all changes)
        reset_result = subprocess.run(
            ["git", "reset", "--hard", checkpoint_commit],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if reset_result.returncode != 0:
            error_msg = reset_result.stderr.strip()
            logger.error(f"[RunCheckpoint] Failed to reset to checkpoint: {error_msg}")
            return False, f"git_reset_failed: {error_msg}"

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
            # Non-fatal - reset succeeded

        # If we were on a named branch, try to return to it
        if checkpoint_branch and checkpoint_branch != "HEAD":
            checkout_result = subprocess.run(
                ["git", "checkout", checkpoint_branch],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if checkout_result.returncode != 0:
                logger.warning(f"[RunCheckpoint] Could not return to branch {checkpoint_branch}")
                # Non-fatal - we're at the right commit

        logger.info("[RunCheckpoint] Successfully rolled back run to pre-run state")
        return True, None

    except subprocess.TimeoutExpired:
        logger.error("[RunCheckpoint] Timeout rolling back to run checkpoint")
        return False, "git_timeout"
    except Exception as e:
        logger.error(f"[RunCheckpoint] Exception during run rollback: {e}")
        return False, f"exception: {str(e)}"


def create_deletion_savepoint(
    workspace: Path,
    phase_id: str,
    run_id: str,
    net_deletion: int,
) -> Optional[str]:
    """
    Create a git tag savepoint before applying large deletions.

    This allows easy recovery if the deletion was a mistake.
    If there are uncommitted changes, they are committed first before creating the tag.

    Args:
        workspace: Path to the git repository
        phase_id: Phase identifier
        run_id: Run identifier
        net_deletion: Number of net lines being deleted

    Returns:
        Tag name if successful, None otherwise
    """
    try:
        workspace = Path(workspace).resolve()

        # Generate tag name
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        tag_name = f"save-before-deletion-{phase_id}-{timestamp}"

        # Check if there are uncommitted changes
        diff_result = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=workspace,
            capture_output=True,
        )

        if diff_result.returncode != 0:
            # There are uncommitted changes - create a temporary commit first
            subprocess.run(
                ["git", "add", "-A"],
                cwd=workspace,
                check=True,
                capture_output=True,
                timeout=30,
            )

            commit_msg = (
                f"[SAVE POINT] Before {phase_id} deletion ({net_deletion} lines)\n\n"
                f"Automatic save point created by Autopack before large deletion.\n"
                f"Phase: {phase_id}\n"
                f"Net deletion: {net_deletion} lines\n"
                f"Run: {run_id}\n\n"
                f"To restore:\n"
                f"  git reset --hard {tag_name}\n"
                f"  # or\n"
                f"  git checkout {tag_name} -- <file>\n"
            )

            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=workspace,
                check=True,
                capture_output=True,
                timeout=30,
            )

        # Create lightweight tag at current HEAD
        subprocess.run(
            ["git", "tag", tag_name],
            cwd=workspace,
            check=True,
            capture_output=True,
            timeout=10,
        )

        logger.info(f"[{phase_id}] Created save point tag: {tag_name}")
        logger.info(f"[{phase_id}] To restore: git reset --hard {tag_name}")

        return tag_name

    except subprocess.TimeoutExpired:
        logger.warning(f"[{phase_id}] Timeout creating save point")
        return None
    except Exception as e:
        logger.warning(f"[{phase_id}] Failed to create save point: {e}")
        return None


def create_execute_fix_checkpoint(workspace: Path, phase_id: str) -> bool:
    """
    Create a git checkpoint before Doctor execute_fix.

    Per GPT_RESPONSE9, create a git commit checkpoint before executing
    potentially destructive fix commands.

    Args:
        workspace: Path to the git repository
        phase_id: Phase identifier

    Returns:
        True if checkpoint created successfully (or no changes to commit), False on error
    """
    try:
        workspace = Path(workspace).resolve()

        logger.info("[Doctor] Creating git checkpoint before execute_fix...")

        # Stage all changes
        add_result = subprocess.run(
            ["git", "add", "-A"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if add_result.returncode != 0:
            logger.warning(f"[Doctor] Failed to stage changes: {add_result.stderr}")
            return False

        # Commit changes
        commit_result = subprocess.run(
            ["git", "commit", "-m", f"[Autopack] Pre-execute_fix checkpoint for {phase_id}"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if commit_result.returncode == 0:
            logger.info("[Doctor] Git checkpoint created successfully")
            return True
        else:
            # Check if it's just "nothing to commit"
            if "nothing to commit" in commit_result.stdout.lower():
                logger.info("[Doctor] No changes to checkpoint (clean state)")
                return True
            else:
                logger.warning(f"[Doctor] Failed to commit checkpoint: {commit_result.stderr}")
                return False

    except subprocess.TimeoutExpired:
        logger.warning("[Doctor] Timeout creating git checkpoint")
        return False
    except Exception as e:
        logger.warning(f"[Doctor] Failed to create git checkpoint: {e}")
        return False


# =============================================================================
# IMP-REL-015: EXECUTOR CRASH RECOVERY WITH STATE PERSISTENCE
# =============================================================================
# These classes and functions support automatic recovery from executor crashes
# mid-run. State is persisted to JSON file and checked on startup.


import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict


@dataclass
class ExecutorState:
    """Snapshot of executor state for crash recovery.

    Captures the essential state needed to resume an interrupted run:
    - run_id: Identifies which run was interrupted
    - current_wave: Which wave was being executed (for wave-based execution)
    - completed_phases: Phases that finished successfully
    - pending_phases: Phases remaining to execute
    - in_progress_phase: Phase that was executing when crash occurred
    - iteration_count: Loop iteration number for progress tracking
    - status: 'in_progress' while running, 'completed' when finished cleanly
    """

    run_id: str
    status: str = "in_progress"
    current_wave: int = 0
    completed_phases: List[str] = field(default_factory=list)
    pending_phases: List[str] = field(default_factory=list)
    in_progress_phase: Optional[str] = None
    iteration_count: int = 0
    phases_executed: int = 0
    phases_failed: int = 0
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutorState":
        """Create from dictionary (JSON deserialization)."""
        return cls(**data)


class ExecutorStateCheckpoint:
    """Manages executor state persistence for crash recovery.

    IMP-REL-015: Provides checkpoint/recovery mechanism so that if the executor
    process crashes mid-run, the next startup can detect and resume from the
    last known state instead of starting over or leaving orphaned phases.

    State is persisted to a JSON file in the .autopack directory.
    """

    CHECKPOINT_DIR = Path(".autopack")
    CHECKPOINT_FILENAME = "executor_state.json"

    def __init__(self, run_id: str, workspace: Path):
        """Initialize checkpoint manager.

        Args:
            run_id: Unique run identifier
            workspace: Workspace root path
        """
        self.run_id = run_id
        self.workspace = Path(workspace).resolve()
        self._checkpoint_path = self.workspace / self.CHECKPOINT_DIR / self.CHECKPOINT_FILENAME

    @property
    def checkpoint_path(self) -> Path:
        """Get path to checkpoint file."""
        return self._checkpoint_path

    def save_state(self, state: ExecutorState) -> bool:
        """Persist current executor state to checkpoint file.

        Called periodically during execution (e.g., on each phase transition)
        to capture progress. If the process crashes, this state can be recovered.

        Args:
            state: Current executor state to persist

        Returns:
            True if save succeeded, False otherwise
        """
        try:
            # Ensure directory exists
            self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

            # Update timestamp
            state.timestamp = datetime.utcnow().isoformat()
            state.status = "in_progress"

            # Write atomically by writing to temp file first
            temp_path = self._checkpoint_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(state.to_dict(), indent=2))
            temp_path.replace(self._checkpoint_path)

            logger.debug(
                f"[IMP-REL-015] Checkpoint saved: phase={state.in_progress_phase}, "
                f"iteration={state.iteration_count}, "
                f"completed={len(state.completed_phases)}"
            )
            return True

        except Exception as e:
            logger.warning(f"[IMP-REL-015] Failed to save checkpoint: {e}")
            return False

    def recover_interrupted_run(self) -> Optional[ExecutorState]:
        """Detect and restore state from an interrupted run.

        Checks if a checkpoint file exists with status='in_progress', indicating
        the previous execution crashed without completing cleanly.

        Returns:
            ExecutorState if interrupted run found, None otherwise
        """
        if not self._checkpoint_path.exists():
            logger.debug("[IMP-REL-015] No checkpoint file found - clean start")
            return None

        try:
            state_data = json.loads(self._checkpoint_path.read_text())
            state = ExecutorState.from_dict(state_data)

            # Only recover if same run_id and status is in_progress (not completed)
            if state.run_id != self.run_id:
                logger.debug(
                    f"[IMP-REL-015] Checkpoint for different run: {state.run_id} != {self.run_id}"
                )
                return None

            if state.status == "completed":
                logger.debug("[IMP-REL-015] Previous run completed cleanly - no recovery needed")
                return None

            # Found interrupted run
            logger.warning(
                f"[IMP-REL-015] Detected interrupted run: "
                f"run_id={state.run_id}, "
                f"wave={state.current_wave}, "
                f"in_progress_phase={state.in_progress_phase}, "
                f"completed_phases={len(state.completed_phases)}, "
                f"timestamp={state.timestamp}"
            )
            return state

        except json.JSONDecodeError as e:
            logger.warning(f"[IMP-REL-015] Corrupted checkpoint file: {e}")
            return None
        except Exception as e:
            logger.warning(f"[IMP-REL-015] Failed to read checkpoint: {e}")
            return None

    def mark_completed(self) -> bool:
        """Mark current run as cleanly completed.

        Called when run finishes successfully. Updates status to 'completed'
        so the next startup knows not to attempt recovery.

        Returns:
            True if update succeeded, False otherwise
        """
        if not self._checkpoint_path.exists():
            # No checkpoint to update - that's fine
            return True

        try:
            state_data = json.loads(self._checkpoint_path.read_text())

            # Only update if this is our run
            if state_data.get("run_id") != self.run_id:
                logger.debug(f"[IMP-REL-015] Checkpoint for different run - not marking complete")
                return True

            state_data["status"] = "completed"
            state_data["timestamp"] = datetime.utcnow().isoformat()
            self._checkpoint_path.write_text(json.dumps(state_data, indent=2))

            logger.info(
                f"[IMP-REL-015] Run marked completed: {self.run_id} "
                f"(phases_executed={state_data.get('phases_executed', 0)})"
            )
            return True

        except Exception as e:
            logger.warning(f"[IMP-REL-015] Failed to mark run complete: {e}")
            return False

    def clear_checkpoint(self) -> bool:
        """Remove checkpoint file (optional cleanup).

        Args:
            None

        Returns:
            True if cleared or didn't exist, False on error
        """
        if not self._checkpoint_path.exists():
            return True

        try:
            self._checkpoint_path.unlink()
            logger.debug(f"[IMP-REL-015] Checkpoint cleared: {self._checkpoint_path}")
            return True
        except Exception as e:
            logger.warning(f"[IMP-REL-015] Failed to clear checkpoint: {e}")
            return False
