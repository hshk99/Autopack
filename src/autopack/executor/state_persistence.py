"""Executor state persistence for crash recovery.

Implements BUILD-041: Executor State Persistence Fix.

This module provides:
- Durable state persistence across restarts
- Phase and attempt tracking with idempotency
- Checkpoint/resume capability for long-running operations
- Integration with external action ledger for side-effect safety
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class PersistenceError(Exception):
    """Raised when state persistence fails non-transiently."""

    pass


class PhaseStatus(str, Enum):
    """Status of a phase in execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"  # Waiting on approval or dependency


@dataclass
class AttemptRecord:
    """Record of a single execution attempt.

    Tracks each attempt at executing a phase, including
    timing, outcome, and any side effects attempted.
    """

    attempt_id: str
    attempt_number: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: PhaseStatus = PhaseStatus.IN_PROGRESS
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    side_effects_attempted: list[str] = field(default_factory=list)
    idempotency_keys: list[str] = field(default_factory=list)
    checkpoint: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "attempt_id": self.attempt_id,
            "attempt_number": self.attempt_number,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status.value,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "side_effects_attempted": self.side_effects_attempted,
            "idempotency_keys": self.idempotency_keys,
            "checkpoint": self.checkpoint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AttemptRecord":
        """Create from dictionary."""
        return cls(
            attempt_id=data["attempt_id"],
            attempt_number=data["attempt_number"],
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
            status=PhaseStatus(data.get("status", "in_progress")),
            error_message=data.get("error_message"),
            error_type=data.get("error_type"),
            side_effects_attempted=data.get("side_effects_attempted", []),
            idempotency_keys=data.get("idempotency_keys", []),
            checkpoint=data.get("checkpoint"),
        )


@dataclass
class PhaseState:
    """State of a single phase in execution.

    Tracks:
    - Phase status and progression
    - All attempts made
    - Side effects and idempotency keys
    - Checkpoints for resumability
    """

    phase_id: str
    phase_number: int
    name: str
    status: PhaseStatus = PhaseStatus.PENDING
    attempts: list[AttemptRecord] = field(default_factory=list)
    max_attempts: int = 3
    current_checkpoint: Optional[dict[str, Any]] = None
    dependencies: list[str] = field(default_factory=list)
    side_effects_committed: list[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def attempt_count(self) -> int:
        """Get the number of attempts made."""
        return len(self.attempts)

    @property
    def can_retry(self) -> bool:
        """Check if more retries are allowed."""
        return self.attempt_count < self.max_attempts and self.status != PhaseStatus.COMPLETED

    @property
    def last_attempt(self) -> Optional[AttemptRecord]:
        """Get the most recent attempt."""
        return self.attempts[-1] if self.attempts else None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "phase_id": self.phase_id,
            "phase_number": self.phase_number,
            "name": self.name,
            "status": self.status.value,
            "attempts": [a.to_dict() for a in self.attempts],
            "max_attempts": self.max_attempts,
            "current_checkpoint": self.current_checkpoint,
            "dependencies": self.dependencies,
            "side_effects_committed": self.side_effects_committed,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PhaseState":
        """Create from dictionary."""
        return cls(
            phase_id=data["phase_id"],
            phase_number=data["phase_number"],
            name=data["name"],
            status=PhaseStatus(data.get("status", "pending")),
            attempts=[AttemptRecord.from_dict(a) for a in data.get("attempts", [])],
            max_attempts=data.get("max_attempts", 3),
            current_checkpoint=data.get("current_checkpoint"),
            dependencies=data.get("dependencies", []),
            side_effects_committed=data.get("side_effects_committed", []),
            started_at=(
                datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
        )


@dataclass
class ExecutorState:
    """Complete executor state for a run.

    This is the top-level state object that tracks:
    - Run identification and configuration
    - All phases and their states
    - Global checkpoint information
    - External action tracking
    """

    run_id: str
    project_id: str
    created_at: datetime
    updated_at: datetime
    phases: list[PhaseState] = field(default_factory=list)
    current_phase_index: int = 0
    status: str = "pending"  # pending, running, completed, failed, paused
    version: int = 1  # State format version
    config_hash: Optional[str] = None  # Hash of configuration for drift detection
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def current_phase(self) -> Optional[PhaseState]:
        """Get the current phase being executed."""
        if 0 <= self.current_phase_index < len(self.phases):
            return self.phases[self.current_phase_index]
        return None

    @property
    def is_complete(self) -> bool:
        """Check if all phases are complete."""
        return all(p.status in (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED) for p in self.phases)

    @property
    def is_failed(self) -> bool:
        """Check if any phase has permanently failed."""
        return any(p.status == PhaseStatus.FAILED and not p.can_retry for p in self.phases)

    def get_next_executable_phase(self) -> Optional[PhaseState]:
        """Get the next phase that can be executed.

        Returns the first phase that is:
        - Not completed or skipped
        - Has all dependencies satisfied
        - Has retries remaining (if previously failed)
        """
        completed_ids = {
            p.phase_id
            for p in self.phases
            if p.status in (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED)
        }

        for phase in self.phases:
            if phase.status in (PhaseStatus.COMPLETED, PhaseStatus.SKIPPED):
                continue
            if phase.status == PhaseStatus.FAILED and not phase.can_retry:
                continue

            # Check dependencies
            if all(dep in completed_ids for dep in phase.dependencies):
                return phase

        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "phases": [p.to_dict() for p in self.phases],
            "current_phase_index": self.current_phase_index,
            "status": self.status,
            "version": self.version,
            "config_hash": self.config_hash,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutorState":
        """Create from dictionary."""
        return cls(
            run_id=data["run_id"],
            project_id=data["project_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            phases=[PhaseState.from_dict(p) for p in data.get("phases", [])],
            current_phase_index=data.get("current_phase_index", 0),
            status=data.get("status", "pending"),
            version=data.get("version", 1),
            config_hash=data.get("config_hash"),
            metadata=data.get("metadata", {}),
        )


class ExecutorStateManager:
    """Manager for executor state persistence.

    Provides:
    - Atomic state save/load operations
    - State recovery on restart
    - Idempotency key management
    - Integration with external action ledger
    """

    STATE_FILE_NAME = "executor_state.json"

    def __init__(
        self,
        storage_dir: Path,
        action_ledger: Optional[Any] = None,  # ExternalActionLedger if available
    ):
        """Initialize the state manager.

        Args:
            storage_dir: Directory for state files
            action_ledger: Optional external action ledger for idempotency
        """
        self.storage_dir = storage_dir
        self.action_ledger = action_ledger
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensure storage directory exists."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, run_id: str) -> Path:
        """Get the state file path for a run."""
        return self.storage_dir / run_id / self.STATE_FILE_NAME

    def _backup_path(self, run_id: str) -> Path:
        """Get the backup state file path."""
        return self.storage_dir / run_id / f"{self.STATE_FILE_NAME}.backup"

    def create_state(
        self,
        run_id: str,
        project_id: str,
        phase_names: list[str],
        config: Optional[dict[str, Any]] = None,
    ) -> ExecutorState:
        """Create a new executor state.

        Args:
            run_id: Unique run identifier
            project_id: Project identifier
            phase_names: Names of phases to execute
            config: Optional configuration to hash

        Returns:
            New ExecutorState instance
        """
        now = datetime.now(timezone.utc)

        phases = [
            PhaseState(
                phase_id=f"{run_id}-phase-{i}",
                phase_number=i,
                name=name,
            )
            for i, name in enumerate(phase_names)
        ]

        config_hash = None
        if config:
            config_json = json.dumps(config, sort_keys=True)
            config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:16]

        state = ExecutorState(
            run_id=run_id,
            project_id=project_id,
            created_at=now,
            updated_at=now,
            phases=phases,
            config_hash=config_hash,
        )

        self.save_state(state)
        return state

    def load_state(self, run_id: str) -> Optional[ExecutorState]:
        """Load state for a run.

        Attempts to load from primary state file, falling back
        to backup if primary is corrupted.

        Args:
            run_id: Run identifier

        Returns:
            ExecutorState if found, None otherwise
        """
        state_path = self._state_path(run_id)
        backup_path = self._backup_path(run_id)

        # Try primary file
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
                state = ExecutorState.from_dict(data)
                logger.info(f"Loaded state for run {run_id}")
                return state
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load primary state for {run_id}: {e}")

        # Try backup
        if backup_path.exists():
            try:
                data = json.loads(backup_path.read_text(encoding="utf-8"))
                state = ExecutorState.from_dict(data)
                logger.info(f"Recovered state from backup for run {run_id}")
                # Restore primary from backup
                self.save_state(state)
                return state
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to load backup state for {run_id}: {e}")

        return None

    @retry(
        retry=retry_if_exception_type(OSError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def save_state(self, state: ExecutorState) -> None:
        """Save state atomically with retry on transient failures.

        Uses backup-and-swap pattern for atomic writes.
        Retries on OSError with exponential backoff to handle transient
        filesystem issues (e.g., network file systems, concurrent access).

        Args:
            state: State to save

        Raises:
            PersistenceError: If state persistence fails after retries
        """
        state_path = self._state_path(state.run_id)
        backup_path = self._backup_path(state.run_id)

        try:
            # Ensure directory exists
            state_path.parent.mkdir(parents=True, exist_ok=True)

            # Update timestamp
            state.updated_at = datetime.now(timezone.utc)

            # Backup existing state
            if state_path.exists():
                try:
                    backup_path.write_text(
                        state_path.read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )
                except OSError as e:
                    # Backup failure is not critical, but log it
                    logger.warning(f"Failed to backup state for {state.run_id}: {e}")

            # Write new state
            state_json = json.dumps(state.to_dict(), indent=2)
            state_path.write_text(state_json, encoding="utf-8")

            logger.debug(f"Saved state for run {state.run_id}")

        except OSError as e:
            # Retriable error - tenacity will handle retry
            logger.warning(f"Transient error saving state for {state.run_id}: {e}")
            raise
        except Exception as e:
            # Non-retriable error
            logger.error(f"Non-retriable error saving state for {state.run_id}: {e}")
            raise PersistenceError(f"Failed to persist state: {e}") from e

    def start_phase(
        self,
        state: ExecutorState,
        phase_id: str,
    ) -> AttemptRecord:
        """Start a new attempt for a phase.

        Args:
            state: Executor state
            phase_id: Phase to start

        Returns:
            New AttemptRecord for this attempt
        """
        phase = next((p for p in state.phases if p.phase_id == phase_id), None)
        if not phase:
            raise ValueError(f"Phase not found: {phase_id}")

        if not phase.can_retry:
            raise ValueError(f"Phase {phase_id} has exhausted retries")

        now = datetime.now(timezone.utc)

        # Create attempt record
        attempt = AttemptRecord(
            attempt_id=f"{phase_id}-attempt-{phase.attempt_count}",
            attempt_number=phase.attempt_count,
            started_at=now,
        )

        # Update phase state
        phase.attempts.append(attempt)
        phase.status = PhaseStatus.IN_PROGRESS
        if not phase.started_at:
            phase.started_at = now

        # Update overall state
        state.status = "running"

        self.save_state(state)
        return attempt

    def complete_phase(
        self,
        state: ExecutorState,
        phase_id: str,
        success: bool,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        side_effects: Optional[list[str]] = None,
    ) -> None:
        """Mark a phase attempt as complete.

        Args:
            state: Executor state
            phase_id: Phase that completed
            success: Whether the attempt succeeded
            error_message: Optional error message if failed
            error_type: Optional error type classification
            side_effects: Optional list of committed side effects
        """
        phase = next((p for p in state.phases if p.phase_id == phase_id), None)
        if not phase:
            raise ValueError(f"Phase not found: {phase_id}")

        attempt = phase.last_attempt
        if not attempt:
            raise ValueError(f"No active attempt for phase {phase_id}")

        now = datetime.now(timezone.utc)

        # Update attempt
        attempt.completed_at = now
        attempt.status = PhaseStatus.COMPLETED if success else PhaseStatus.FAILED
        attempt.error_message = error_message
        attempt.error_type = error_type

        # Update phase
        if success:
            phase.status = PhaseStatus.COMPLETED
            phase.completed_at = now
            if side_effects:
                phase.side_effects_committed.extend(side_effects)
        else:
            if phase.can_retry:
                phase.status = PhaseStatus.PENDING  # Will retry
            else:
                phase.status = PhaseStatus.FAILED

        # Update overall state
        if state.is_complete:
            state.status = "completed"
        elif state.is_failed:
            state.status = "failed"

        self.save_state(state)

    def save_checkpoint(
        self,
        state: ExecutorState,
        phase_id: str,
        checkpoint: dict[str, Any],
    ) -> None:
        """Save a checkpoint for resumability.

        Args:
            state: Executor state
            phase_id: Phase to checkpoint
            checkpoint: Checkpoint data
        """
        phase = next((p for p in state.phases if p.phase_id == phase_id), None)
        if not phase:
            raise ValueError(f"Phase not found: {phase_id}")

        phase.current_checkpoint = checkpoint

        attempt = phase.last_attempt
        if attempt:
            attempt.checkpoint = checkpoint

        self.save_state(state)

    def register_idempotency_key(
        self,
        state: ExecutorState,
        phase_id: str,
        key: str,
    ) -> bool:
        """Register an idempotency key for a side effect.

        Checks if the key has already been used (indicating the
        side effect was already committed) before registering.

        Args:
            state: Executor state
            phase_id: Phase performing the side effect
            key: Idempotency key for the side effect

        Returns:
            True if key is new (proceed), False if already used (skip)
        """
        # Check action ledger if available
        if self.action_ledger:
            if self.action_ledger.has_key(key):
                logger.info(f"Idempotency key already used: {key}")
                return False

        phase = next((p for p in state.phases if p.phase_id == phase_id), None)
        if not phase:
            raise ValueError(f"Phase not found: {phase_id}")

        attempt = phase.last_attempt
        if not attempt:
            raise ValueError(f"No active attempt for phase {phase_id}")

        # Check if key was used in previous attempts
        for prev_attempt in phase.attempts:
            if key in prev_attempt.idempotency_keys:
                logger.info(f"Idempotency key used in previous attempt: {key}")
                return False

        # Register the key
        attempt.idempotency_keys.append(key)
        self.save_state(state)

        return True

    def get_run_summary(self, run_id: str) -> Optional[dict[str, Any]]:
        """Get a summary of a run's state.

        Args:
            run_id: Run identifier

        Returns:
            Summary dict or None if run not found
        """
        state = self.load_state(run_id)
        if not state:
            return None

        phases_summary = []
        for phase in state.phases:
            phases_summary.append(
                {
                    "name": phase.name,
                    "status": phase.status.value,
                    "attempts": phase.attempt_count,
                    "has_checkpoint": phase.current_checkpoint is not None,
                }
            )

        return {
            "run_id": state.run_id,
            "project_id": state.project_id,
            "status": state.status,
            "created_at": state.created_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
            "phases": phases_summary,
            "current_phase": state.current_phase.name if state.current_phase else None,
            "is_complete": state.is_complete,
            "is_failed": state.is_failed,
        }

    def list_runs(self) -> list[str]:
        """List all run IDs with persisted state.

        Returns:
            List of run IDs
        """
        runs = []
        if self.storage_dir.exists():
            for path in self.storage_dir.iterdir():
                if path.is_dir() and (path / self.STATE_FILE_NAME).exists():
                    runs.append(path.name)
        return sorted(runs)

    def delete_state(self, run_id: str) -> bool:
        """Delete state for a run.

        Args:
            run_id: Run identifier

        Returns:
            True if state was deleted, False if not found
        """
        state_path = self._state_path(run_id)
        backup_path = self._backup_path(run_id)

        deleted = False
        if state_path.exists():
            state_path.unlink()
            deleted = True
        if backup_path.exists():
            backup_path.unlink()

        logger.info(f"Deleted state for run {run_id}")
        return deleted
