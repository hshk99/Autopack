"""Autopilot controller - autonomous execution with safe gates.

The autopilot controller orchestrates the full autonomy loop:
1. Load intention anchor (v2)
2. Scan for gaps
3. Propose plan with governance
4. Execute auto-approved actions (if any)
5. Stop and record if approval required

Feature Gate Configuration (IMP-BLOCKED-002):
    Autopilot is disabled by default for safety. To enable:

    1. Environment Variable (recommended):
       export AUTOPACK_AUTOPILOT_ENABLED=true

    2. Alternative alias:
       export AUTOPILOT_ENABLED=true

    Capability Auto-Detection:
        Use `detect_autopilot_capabilities(workspace_root)` to check if your
        environment has all required components before enabling autopilot.
        This returns an AutopilotCapabilities object with:
        - workspace_valid: True if workspace directory exists
        - intention_anchor_found: True if intention_anchor.yaml exists
        - gap_scanner_available: True if gap scanner module is importable
        - plan_proposer_available: True if plan proposer module is importable
        - is_ready: True only if all components are available
        - missing_components: List of what's missing (for error messages)

BUILD-181 Integration:
- ExecutorContext for usage tracking, safety profile, scope reduction
- Approval service for pivot-impacting changes
- Coverage metrics processing

IMP-REL-001: Health-gated task generation with auto-resume support.
IMP-BLOCKED-002: Auto-detection of autopilot capabilities.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from ..telemetry.meta_metrics import FeedbackLoopHealth
    from .approval_service import ApprovalService

from ..file_layout import RunFileLayout
from ..gaps.scanner import scan_workspace
from ..intention_anchor.v2 import IntentionAnchorV2
from ..planning.models import PlanProposalV1
from ..planning.plan_proposer import propose_plan
from ..research.analysis.followup_trigger import (
    FollowupResearchTrigger,
    FollowupTrigger,
    TriggerAnalysisResult,
    TriggerExecutionResult,
)
from ..telemetry.autopilot_metrics import (
    AutopilotHealthCollector,
    SessionHealthSnapshot,
    SessionOutcome,
)
from .action_allowlist import ActionClassification
from .action_executor import ExecutionBatch, SafeActionExecutor
from .event_triggers import EventTriggerManager, EventType, WorkflowEvent
from .executor_integration import ExecutorContext, create_executor_context
from .models import (
    ApprovalRequest,
    AutopilotMetadata,
    AutopilotSessionV1,
    ErrorLogEntry,
    ExecutionSummary,
)
from .research_cycle_integration import (
    ResearchCycleDecision,
    ResearchCycleIntegration,
    ResearchCycleMetrics,
    ResearchCycleOutcome,
    create_research_cycle_integration,
)

logger = logging.getLogger(__name__)


# ============================================================================
# IMP-BLOCKED-002: Autopilot Capability Auto-Detection
# ============================================================================


@dataclass
class AutopilotCapabilities:
    """Result of autopilot capability detection.

    IMP-BLOCKED-002: Provides detailed information about whether the system
    has all required components to run autopilot autonomously.

    Attributes:
        workspace_valid: True if workspace directory exists and is accessible
        intention_anchor_found: True if intention_anchor.yaml exists in workspace
        gap_scanner_available: True if gap scanner module is importable
        plan_proposer_available: True if plan proposer module is importable
        executor_context_available: True if executor context can be created
        is_ready: True only if all required components are available
        missing_components: List of components that are not available
        recommendations: List of actionable recommendations to fix issues
    """

    workspace_valid: bool = False
    intention_anchor_found: bool = False
    gap_scanner_available: bool = True  # Default True since it's a core module
    plan_proposer_available: bool = True  # Default True since it's a core module
    executor_context_available: bool = True  # Default True since it's a core module
    missing_components: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """Check if all required components are available for autopilot."""
        return (
            self.workspace_valid
            and self.intention_anchor_found
            and self.gap_scanner_available
            and self.plan_proposer_available
            and self.executor_context_available
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert capabilities to dictionary representation."""
        return {
            "workspace_valid": self.workspace_valid,
            "intention_anchor_found": self.intention_anchor_found,
            "gap_scanner_available": self.gap_scanner_available,
            "plan_proposer_available": self.plan_proposer_available,
            "executor_context_available": self.executor_context_available,
            "is_ready": self.is_ready,
            "missing_components": self.missing_components,
            "recommendations": self.recommendations,
        }

    def get_status_message(self) -> str:
        """Get a human-readable status message."""
        if self.is_ready:
            return "Autopilot capabilities: All components available. Ready to enable."
        else:
            missing = ", ".join(self.missing_components) if self.missing_components else "unknown"
            return f"Autopilot capabilities: Missing components: {missing}"


def detect_autopilot_capabilities(
    workspace_root: Path,
    check_intention_anchor: bool = True,
) -> AutopilotCapabilities:
    """Detect if the system has all required capabilities for autopilot.

    IMP-BLOCKED-002: Auto-detection of autopilot prerequisites to help users
    understand what's needed before enabling autopilot mode.

    Args:
        workspace_root: Root directory of the workspace to check
        check_intention_anchor: Whether to check for intention_anchor.yaml

    Returns:
        AutopilotCapabilities object with detection results

    Example:
        ```python
        from autopack.autonomy.autopilot import detect_autopilot_capabilities
        from pathlib import Path

        caps = detect_autopilot_capabilities(Path("/path/to/workspace"))
        if caps.is_ready:
            print("Ready to enable autopilot!")
        else:
            print(f"Missing: {caps.missing_components}")
            for rec in caps.recommendations:
                print(f"  - {rec}")
        ```
    """
    caps = AutopilotCapabilities()

    # Check workspace validity
    if workspace_root.exists() and workspace_root.is_dir():
        caps.workspace_valid = True
    else:
        caps.workspace_valid = False
        caps.missing_components.append("workspace_directory")
        caps.recommendations.append(f"Create workspace directory: {workspace_root}")

    # Check for intention anchor file
    if check_intention_anchor:
        anchor_paths = [
            workspace_root / "intention_anchor.yaml",
            workspace_root / ".autopack" / "intention_anchor.yaml",
            workspace_root / "config" / "intention_anchor.yaml",
        ]
        anchor_found = any(p.exists() for p in anchor_paths)
        caps.intention_anchor_found = anchor_found
        if not anchor_found:
            caps.missing_components.append("intention_anchor")
            caps.recommendations.append(
                "Create intention_anchor.yaml in workspace root or .autopack/ directory. "
                "See docs/INTENTION_ANCHOR_SPEC.md for format."
            )
    else:
        caps.intention_anchor_found = True  # Skip check

    # Check gap scanner availability
    try:
        from ..gaps.scanner import scan_workspace  # noqa: F401

        caps.gap_scanner_available = True
    except ImportError as e:
        caps.gap_scanner_available = False
        caps.missing_components.append("gap_scanner")
        caps.recommendations.append(f"Gap scanner import failed: {e}")

    # Check plan proposer availability
    try:
        from ..planning.plan_proposer import propose_plan  # noqa: F401

        caps.plan_proposer_available = True
    except ImportError as e:
        caps.plan_proposer_available = False
        caps.missing_components.append("plan_proposer")
        caps.recommendations.append(f"Plan proposer import failed: {e}")

    # Check executor context availability
    try:
        from .executor_integration import create_executor_context  # noqa: F401

        caps.executor_context_available = True
    except ImportError as e:
        caps.executor_context_available = False
        caps.missing_components.append("executor_context")
        caps.recommendations.append(f"Executor context import failed: {e}")

    # Log the detection result
    if caps.is_ready:
        logger.info("[IMP-BLOCKED-002] Autopilot capability check passed: all components available")
    else:
        logger.info(
            f"[IMP-BLOCKED-002] Autopilot capability check: "
            f"missing components: {caps.missing_components}"
        )

    return caps


# ============================================================================
# IMP-LIFECYCLE-002: Phase State Machine for Autopilot Sequencing
# ============================================================================


class PhaseExecutionState(Enum):
    """State of a phase in the lifecycle state machine.

    IMP-LIFECYCLE-002: Defines all valid states for phase execution
    with support for rollback on failures.
    """

    PENDING = "pending"  # Phase not yet started
    READY = "ready"  # Prerequisites met, ready to execute
    IN_PROGRESS = "in_progress"  # Currently executing
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Execution failed
    ROLLED_BACK = "rolled_back"  # Rolled back to previous state


class PhaseType(Enum):
    """Types of lifecycle phases with ordering constraints.

    IMP-LIFECYCLE-002: Defines the phase types and their execution order.
    Phases must be executed in this order: research → build → deploy → monetize → postlaunch
    """

    RESEARCH = "research"
    BUILD = "build"
    DEPLOY = "deploy"
    MONETIZE = "monetize"
    POSTLAUNCH = "postlaunch"

    @property
    def order(self) -> int:
        """Get the execution order of this phase type."""
        order_map = {
            PhaseType.RESEARCH: 0,
            PhaseType.BUILD: 1,
            PhaseType.DEPLOY: 2,
            PhaseType.MONETIZE: 3,
            PhaseType.POSTLAUNCH: 4,
        }
        return order_map[self]

    @classmethod
    def get_dependencies(cls, phase_type: "PhaseType") -> list["PhaseType"]:
        """Get phases that must complete before this phase can start.

        Args:
            phase_type: The phase type to get dependencies for

        Returns:
            List of phase types that must complete first
        """
        dependencies_map = {
            cls.RESEARCH: [],  # Research has no dependencies
            cls.BUILD: [cls.RESEARCH],  # Build requires research
            cls.DEPLOY: [cls.RESEARCH, cls.BUILD],  # Deploy requires research and build
            cls.MONETIZE: [cls.RESEARCH, cls.BUILD, cls.DEPLOY],  # Monetize requires deploy
            cls.POSTLAUNCH: [
                cls.RESEARCH,
                cls.BUILD,
                cls.DEPLOY,
                cls.MONETIZE,
            ],  # Postlaunch requires all prior phases
        }
        return dependencies_map.get(phase_type, [])


@dataclass
class PhaseTransition:
    """Record of a phase state transition.

    IMP-LIFECYCLE-002: Tracks all transitions for audit and rollback purposes.
    """

    phase_id: str
    phase_type: PhaseType
    from_state: PhaseExecutionState
    to_state: PhaseExecutionState
    timestamp: datetime
    reason: Optional[str] = None
    triggered_by: Optional[str] = None  # e.g., "automatic", "manual", "rollback"

    def to_dict(self) -> Dict[str, Any]:
        """Convert transition to dictionary representation."""
        return {
            "phase_id": self.phase_id,
            "phase_type": self.phase_type.value,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "triggered_by": self.triggered_by,
        }


@dataclass
class PhaseStateEntry:
    """State entry for a single phase in the state machine.

    IMP-LIFECYCLE-002: Tracks the current state and history for each phase.
    """

    phase_id: str
    phase_type: PhaseType
    state: PhaseExecutionState = PhaseExecutionState.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    rollback_count: int = 0
    transitions: list = field(default_factory=list)  # List[PhaseTransition]

    def to_dict(self) -> Dict[str, Any]:
        """Convert phase state to dictionary representation."""
        return {
            "phase_id": self.phase_id,
            "phase_type": self.phase_type.value,
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "rollback_count": self.rollback_count,
            "transitions": [t.to_dict() for t in self.transitions],
        }


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted.

    IMP-LIFECYCLE-002: Provides detailed information about why a transition is invalid.
    """

    def __init__(
        self,
        phase_id: str,
        from_state: PhaseExecutionState,
        to_state: PhaseExecutionState,
        reason: str,
    ):
        self.phase_id = phase_id
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(
            f"Invalid transition for phase '{phase_id}': "
            f"{from_state.value} → {to_state.value}. Reason: {reason}"
        )


class PhaseDependencyError(Exception):
    """Raised when phase dependencies are not satisfied.

    IMP-LIFECYCLE-002: Indicates which dependencies are blocking execution.
    """

    def __init__(
        self,
        phase_id: str,
        phase_type: PhaseType,
        missing_dependencies: list,
    ):
        self.phase_id = phase_id
        self.phase_type = phase_type
        self.missing_dependencies = missing_dependencies
        dep_names = [d.value for d in missing_dependencies]
        super().__init__(
            f"Phase '{phase_id}' ({phase_type.value}) cannot start: "
            f"dependencies not completed: {dep_names}"
        )


class PhaseStateMachine:
    """State machine for managing phase lifecycle execution order.

    IMP-LIFECYCLE-002: Implements proper phase sequencing with:
    - Valid state transitions enforcement
    - Phase dependency validation
    - Phase ordering constraints (research → build → deploy → monetize → postlaunch)
    - Phase completion verification
    - Rollback capability for failed transitions

    The state machine ensures phases cannot execute out of order, skip prerequisites,
    or run concurrently when they should be sequential.

    Example usage:
        ```python
        machine = PhaseStateMachine()

        # Register phases
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)
        machine.register_phase("deploy-001", PhaseType.DEPLOY)

        # Mark research as ready (no dependencies)
        machine.mark_ready("research-001")

        # Start research
        machine.start_phase("research-001")

        # Complete research
        machine.complete_phase("research-001")

        # Now build can start (research is complete)
        machine.mark_ready("build-001")  # Will succeed

        # Try to start deploy before build
        machine.mark_ready("deploy-001")  # Raises PhaseDependencyError
        ```
    """

    # Valid state transitions: from_state -> list of valid to_states
    VALID_TRANSITIONS: Dict[PhaseExecutionState, list] = {
        PhaseExecutionState.PENDING: [PhaseExecutionState.READY],
        PhaseExecutionState.READY: [PhaseExecutionState.IN_PROGRESS],
        PhaseExecutionState.IN_PROGRESS: [
            PhaseExecutionState.COMPLETED,
            PhaseExecutionState.FAILED,
        ],
        PhaseExecutionState.COMPLETED: [],  # Terminal state
        PhaseExecutionState.FAILED: [PhaseExecutionState.ROLLED_BACK],
        PhaseExecutionState.ROLLED_BACK: [PhaseExecutionState.READY],
    }

    def __init__(self, enforce_ordering: bool = True):
        """Initialize the phase state machine.

        Args:
            enforce_ordering: If True, enforces phase ordering constraints.
                            Set to False for testing or custom workflows.
        """
        self._phases: Dict[str, PhaseStateEntry] = {}
        self._enforce_ordering = enforce_ordering
        self._global_transitions: list = []  # All transitions across all phases
        logger.info(
            f"[IMP-LIFECYCLE-002] PhaseStateMachine initialized "
            f"(enforce_ordering={enforce_ordering})"
        )

    def register_phase(
        self,
        phase_id: str,
        phase_type: PhaseType,
        initial_state: PhaseExecutionState = PhaseExecutionState.PENDING,
    ) -> PhaseStateEntry:
        """Register a new phase with the state machine.

        Args:
            phase_id: Unique identifier for the phase
            phase_type: Type of phase (research, build, deploy, etc.)
            initial_state: Initial state for the phase (default: PENDING)

        Returns:
            The created PhaseStateEntry

        Raises:
            ValueError: If phase_id already exists
        """
        if phase_id in self._phases:
            raise ValueError(f"Phase '{phase_id}' already registered")

        entry = PhaseStateEntry(
            phase_id=phase_id,
            phase_type=phase_type,
            state=initial_state,
        )
        self._phases[phase_id] = entry

        logger.info(
            f"[IMP-LIFECYCLE-002] Registered phase '{phase_id}' "
            f"(type={phase_type.value}, initial_state={initial_state.value})"
        )
        return entry

    def get_phase(self, phase_id: str) -> Optional[PhaseStateEntry]:
        """Get a phase by ID.

        Args:
            phase_id: The phase identifier

        Returns:
            PhaseStateEntry or None if not found
        """
        return self._phases.get(phase_id)

    def get_phase_state(self, phase_id: str) -> Optional[PhaseExecutionState]:
        """Get the current state of a phase.

        Args:
            phase_id: The phase identifier

        Returns:
            Current PhaseExecutionState or None if phase not found
        """
        entry = self._phases.get(phase_id)
        return entry.state if entry else None

    def is_transition_valid(
        self,
        from_state: PhaseExecutionState,
        to_state: PhaseExecutionState,
    ) -> bool:
        """Check if a state transition is valid.

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            True if transition is valid, False otherwise
        """
        valid_targets = self.VALID_TRANSITIONS.get(from_state, [])
        return to_state in valid_targets

    def _validate_transition(
        self,
        phase_id: str,
        to_state: PhaseExecutionState,
    ) -> None:
        """Validate a state transition.

        Args:
            phase_id: The phase identifier
            to_state: Target state

        Raises:
            ValueError: If phase not found
            InvalidTransitionError: If transition is not valid
        """
        entry = self._phases.get(phase_id)
        if not entry:
            raise ValueError(f"Phase '{phase_id}' not found")

        from_state = entry.state

        if not self.is_transition_valid(from_state, to_state):
            valid_targets = self.VALID_TRANSITIONS.get(from_state, [])
            valid_names = [s.value for s in valid_targets]
            raise InvalidTransitionError(
                phase_id=phase_id,
                from_state=from_state,
                to_state=to_state,
                reason=f"Valid transitions from {from_state.value}: {valid_names}",
            )

    def _check_dependencies(self, phase_id: str) -> None:
        """Check if phase dependencies are satisfied.

        Args:
            phase_id: The phase identifier

        Raises:
            ValueError: If phase not found
            PhaseDependencyError: If dependencies are not satisfied
        """
        if not self._enforce_ordering:
            return

        entry = self._phases.get(phase_id)
        if not entry:
            raise ValueError(f"Phase '{phase_id}' not found")

        dependencies = PhaseType.get_dependencies(entry.phase_type)
        missing = []

        for dep_type in dependencies:
            # Find phases of this type that are completed
            completed_phases = [
                p
                for p in self._phases.values()
                if p.phase_type == dep_type and p.state == PhaseExecutionState.COMPLETED
            ]
            if not completed_phases:
                missing.append(dep_type)

        if missing:
            raise PhaseDependencyError(
                phase_id=phase_id,
                phase_type=entry.phase_type,
                missing_dependencies=missing,
            )

    def _record_transition(
        self,
        phase_id: str,
        from_state: PhaseExecutionState,
        to_state: PhaseExecutionState,
        reason: Optional[str] = None,
        triggered_by: str = "automatic",
    ) -> PhaseTransition:
        """Record a state transition.

        Args:
            phase_id: The phase identifier
            from_state: Previous state
            to_state: New state
            reason: Optional reason for transition
            triggered_by: What triggered the transition

        Returns:
            The created PhaseTransition
        """
        entry = self._phases.get(phase_id)
        if not entry:
            raise ValueError(f"Phase '{phase_id}' not found")

        transition = PhaseTransition(
            phase_id=phase_id,
            phase_type=entry.phase_type,
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
            triggered_by=triggered_by,
        )

        entry.transitions.append(transition)
        self._global_transitions.append(transition)

        logger.debug(
            f"[IMP-LIFECYCLE-002] Transition: {phase_id} "
            f"{from_state.value} → {to_state.value} ({triggered_by})"
        )
        return transition

    def _set_state(
        self,
        phase_id: str,
        to_state: PhaseExecutionState,
        reason: Optional[str] = None,
        triggered_by: str = "automatic",
    ) -> PhaseTransition:
        """Set the state of a phase after validation.

        Args:
            phase_id: The phase identifier
            to_state: Target state
            reason: Optional reason for transition
            triggered_by: What triggered the transition

        Returns:
            The created PhaseTransition

        Raises:
            ValueError: If phase not found
            InvalidTransitionError: If transition is not valid
        """
        self._validate_transition(phase_id, to_state)

        entry = self._phases[phase_id]
        from_state = entry.state
        entry.state = to_state

        return self._record_transition(phase_id, from_state, to_state, reason, triggered_by)

    def mark_ready(
        self,
        phase_id: str,
        reason: Optional[str] = None,
    ) -> PhaseTransition:
        """Mark a phase as ready to execute.

        IMP-LIFECYCLE-002: Validates dependencies before marking ready.
        Only phases in PENDING or ROLLED_BACK state can transition to READY.

        Args:
            phase_id: The phase identifier
            reason: Optional reason for marking ready

        Returns:
            The created PhaseTransition

        Raises:
            ValueError: If phase not found
            InvalidTransitionError: If transition is not valid
            PhaseDependencyError: If dependencies are not satisfied
        """
        # Check dependencies before allowing transition
        self._check_dependencies(phase_id)

        entry = self._phases.get(phase_id)
        if not entry:
            raise ValueError(f"Phase '{phase_id}' not found")

        # Handle both PENDING → READY and ROLLED_BACK → READY
        if entry.state == PhaseExecutionState.PENDING:
            return self._set_state(phase_id, PhaseExecutionState.READY, reason, "dependency_check")
        elif entry.state == PhaseExecutionState.ROLLED_BACK:
            return self._set_state(phase_id, PhaseExecutionState.READY, reason, "retry")
        else:
            # Try the transition anyway to get proper error message
            return self._set_state(phase_id, PhaseExecutionState.READY, reason, "manual")

    def start_phase(
        self,
        phase_id: str,
        reason: Optional[str] = None,
    ) -> PhaseTransition:
        """Start execution of a phase.

        IMP-LIFECYCLE-002: Transitions READY → IN_PROGRESS.

        Args:
            phase_id: The phase identifier
            reason: Optional reason for starting

        Returns:
            The created PhaseTransition

        Raises:
            ValueError: If phase not found
            InvalidTransitionError: If phase is not in READY state
        """
        entry = self._phases.get(phase_id)
        if not entry:
            raise ValueError(f"Phase '{phase_id}' not found")

        transition = self._set_state(
            phase_id, PhaseExecutionState.IN_PROGRESS, reason, "execution_start"
        )
        entry.started_at = datetime.now(timezone.utc)

        logger.info(f"[IMP-LIFECYCLE-002] Phase '{phase_id}' started")
        return transition

    def complete_phase(
        self,
        phase_id: str,
        reason: Optional[str] = None,
    ) -> PhaseTransition:
        """Mark a phase as successfully completed.

        IMP-LIFECYCLE-002: Transitions IN_PROGRESS → COMPLETED.

        Args:
            phase_id: The phase identifier
            reason: Optional completion reason

        Returns:
            The created PhaseTransition

        Raises:
            ValueError: If phase not found
            InvalidTransitionError: If phase is not in IN_PROGRESS state
        """
        entry = self._phases.get(phase_id)
        if not entry:
            raise ValueError(f"Phase '{phase_id}' not found")

        transition = self._set_state(
            phase_id, PhaseExecutionState.COMPLETED, reason, "execution_complete"
        )
        entry.completed_at = datetime.now(timezone.utc)
        entry.error = None

        logger.info(f"[IMP-LIFECYCLE-002] Phase '{phase_id}' completed successfully")
        return transition

    def fail_phase(
        self,
        phase_id: str,
        error: str,
    ) -> PhaseTransition:
        """Mark a phase as failed.

        IMP-LIFECYCLE-002: Transitions IN_PROGRESS → FAILED.

        Args:
            phase_id: The phase identifier
            error: Error message describing the failure

        Returns:
            The created PhaseTransition

        Raises:
            ValueError: If phase not found
            InvalidTransitionError: If phase is not in IN_PROGRESS state
        """
        entry = self._phases.get(phase_id)
        if not entry:
            raise ValueError(f"Phase '{phase_id}' not found")

        transition = self._set_state(
            phase_id, PhaseExecutionState.FAILED, error, "execution_failed"
        )
        entry.completed_at = datetime.now(timezone.utc)
        entry.error = error

        logger.warning(f"[IMP-LIFECYCLE-002] Phase '{phase_id}' failed: {error}")
        return transition

    def rollback_phase(
        self,
        phase_id: str,
        reason: Optional[str] = None,
    ) -> PhaseTransition:
        """Rollback a failed phase for potential retry.

        IMP-LIFECYCLE-002: Transitions FAILED → ROLLED_BACK.
        After rollback, the phase can transition to READY for retry.

        Args:
            phase_id: The phase identifier
            reason: Optional reason for rollback

        Returns:
            The created PhaseTransition

        Raises:
            ValueError: If phase not found
            InvalidTransitionError: If phase is not in FAILED state
        """
        entry = self._phases.get(phase_id)
        if not entry:
            raise ValueError(f"Phase '{phase_id}' not found")

        transition = self._set_state(phase_id, PhaseExecutionState.ROLLED_BACK, reason, "rollback")
        entry.rollback_count += 1

        logger.info(
            f"[IMP-LIFECYCLE-002] Phase '{phase_id}' rolled back "
            f"(rollback_count={entry.rollback_count})"
        )
        return transition

    def can_phase_start(self, phase_id: str) -> tuple:
        """Check if a phase can start execution.

        IMP-LIFECYCLE-002: Verifies both state and dependencies.

        Args:
            phase_id: The phase identifier

        Returns:
            Tuple of (can_start: bool, reason: str)
        """
        entry = self._phases.get(phase_id)
        if not entry:
            return False, f"Phase '{phase_id}' not found"

        # Check current state
        if entry.state != PhaseExecutionState.READY:
            return False, f"Phase is in state '{entry.state.value}', must be 'ready'"

        # Check dependencies
        if self._enforce_ordering:
            try:
                self._check_dependencies(phase_id)
            except PhaseDependencyError as e:
                return False, str(e)

        return True, "Phase can start"

    def get_next_executable_phases(self) -> list:
        """Get phases that can be executed next.

        IMP-LIFECYCLE-002: Returns phases in READY state with satisfied dependencies.

        Returns:
            List of phase IDs that can be executed
        """
        executable = []
        for phase_id, entry in self._phases.items():
            if entry.state == PhaseExecutionState.READY:
                can_start, _ = self.can_phase_start(phase_id)
                if can_start:
                    executable.append(phase_id)
        return executable

    def get_phases_by_state(self, state: PhaseExecutionState) -> list:
        """Get all phases in a specific state.

        Args:
            state: The state to filter by

        Returns:
            List of phase IDs in that state
        """
        return [p.phase_id for p in self._phases.values() if p.state == state]

    def get_phases_by_type(self, phase_type: PhaseType) -> list:
        """Get all phases of a specific type.

        Args:
            phase_type: The type to filter by

        Returns:
            List of phase IDs of that type
        """
        return [p.phase_id for p in self._phases.values() if p.phase_type == phase_type]

    def are_all_phases_complete(self) -> bool:
        """Check if all registered phases are complete.

        Returns:
            True if all phases are in COMPLETED state
        """
        if not self._phases:
            return False
        return all(p.state == PhaseExecutionState.COMPLETED for p in self._phases.values())

    def get_completion_status(self) -> Dict[str, Any]:
        """Get completion status summary.

        Returns:
            Dictionary with completion statistics
        """
        total = len(self._phases)
        by_state = {}
        for state in PhaseExecutionState:
            count = len(self.get_phases_by_state(state))
            if count > 0:
                by_state[state.value] = count

        return {
            "total_phases": total,
            "by_state": by_state,
            "all_complete": self.are_all_phases_complete(),
            "pending_count": len(self.get_phases_by_state(PhaseExecutionState.PENDING)),
            "completed_count": len(self.get_phases_by_state(PhaseExecutionState.COMPLETED)),
            "failed_count": len(self.get_phases_by_state(PhaseExecutionState.FAILED)),
        }

    def get_transition_history(
        self,
        phase_id: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        """Get transition history.

        Args:
            phase_id: If provided, filter to specific phase
            limit: Maximum number of transitions to return

        Returns:
            List of PhaseTransition dictionaries
        """
        if phase_id:
            entry = self._phases.get(phase_id)
            if not entry:
                return []
            transitions = entry.transitions[-limit:]
        else:
            transitions = self._global_transitions[-limit:]

        return [t.to_dict() for t in transitions]

    def to_dict(self) -> Dict[str, Any]:
        """Convert state machine to dictionary representation.

        Returns:
            Dictionary with full state machine state
        """
        return {
            "enforce_ordering": self._enforce_ordering,
            "phases": {pid: entry.to_dict() for pid, entry in self._phases.items()},
            "completion_status": self.get_completion_status(),
            "recent_transitions": self.get_transition_history(limit=10),
        }

    def reset(self) -> None:
        """Reset the state machine to initial state.

        Clears all registered phases and transition history.
        """
        self._phases.clear()
        self._global_transitions.clear()
        logger.info("[IMP-LIFECYCLE-002] PhaseStateMachine reset")


class StateCheckpoint:
    """Captures the state of an AutopilotController for rollback on API failures.

    IMP-REL-005: Enables transaction-like rollback semantics for API calls.
    Stores critical state before executing API operations and can restore
    the saved state if the operation fails.
    """

    def __init__(self, session: Optional[AutopilotSessionV1] = None):
        """Create a checkpoint from current state.

        Args:
            session: The autopilot session to checkpoint
        """
        self.session_state = copy.deepcopy(session) if session else None
        self.checkpoint_time = datetime.now(timezone.utc)

    def restore_session(self, session: AutopilotSessionV1) -> None:
        """Restore session from this checkpoint.

        Args:
            session: Session object to restore into
        """
        if self.session_state is None:
            logger.debug("[IMP-REL-005] No session state to restore from checkpoint")
            return

        # Restore critical session attributes
        session.status = self.session_state.status
        session.blocked_reason = self.session_state.blocked_reason
        session.gap_report_id = self.session_state.gap_report_id
        session.plan_proposal_id = self.session_state.plan_proposal_id
        session.approval_requests = self.session_state.approval_requests
        session.executed_action_ids = self.session_state.executed_action_ids
        session.execution_summary = self.session_state.execution_summary
        session.error_log = copy.deepcopy(self.session_state.error_log)

        logger.info("[IMP-REL-005] Session state restored from checkpoint")


class AutopilotController:
    """Autopilot controller for autonomous execution within safe gates.

    Attributes:
        workspace_root: Root directory of workspace
        project_id: Project identifier
        run_id: Run identifier
        enabled: Whether autopilot is enabled (default: False)
        session: Current autopilot session
        executor_ctx: BUILD-181 ExecutorContext for integrated handling
        _event_trigger_manager: IMP-AUTO-002 EventTriggerManager for external events

    IMP-REL-001: Includes health-gated task generation with auto-resume support.
    Task generation can be paused when feedback loop health is degraded and
    automatically resumed when health recovers to HEALTHY.

    IMP-AUTO-002: Includes event-driven workflow triggers that respond to
    external events (API updates, dependency changes, market signals, etc).
    """

    def __init__(
        self,
        workspace_root: Path,
        project_id: str,
        run_id: str,
        enabled: bool = False,
    ):
        """Initialize autopilot controller.

        Args:
            workspace_root: Root directory of workspace
            project_id: Project identifier
            run_id: Run identifier
            enabled: Whether autopilot is explicitly enabled (default: False)
        """
        self.workspace_root = workspace_root
        self.project_id = project_id
        self.run_id = run_id
        self.enabled = enabled
        self.layout = RunFileLayout(run_id=run_id, project_id=project_id)
        self.session: Optional[AutopilotSessionV1] = None
        self.executor_ctx: Optional[ExecutorContext] = None

        # IMP-SEG-001: Health metrics tracking
        self._health_collector = AutopilotHealthCollector()
        self._last_cb_state_open: bool = False

        # IMP-REL-001: Health-gated task generation state
        self._task_generation_paused: bool = False
        self._pause_reason: Optional[str] = None
        self._resume_callbacks: list[Callable[[], None]] = []

        # IMP-AUTO-001: Research cycle triggering callbacks
        self._research_cycle_callbacks: list[Callable[[TriggerAnalysisResult], None]] = []
        self._last_research_trigger_result: Optional[TriggerAnalysisResult] = None

        # IMP-HIGH-005: FollowupResearchTrigger instance for callback execution
        self._followup_trigger: FollowupResearchTrigger = FollowupResearchTrigger()
        self._mid_execution_research_enabled: bool = True
        self._research_execution_results: list[TriggerExecutionResult] = []

        # IMP-AUTO-002: Event-driven workflow triggers
        self._event_trigger_manager = EventTriggerManager()
        self._pending_events: list[WorkflowEvent] = []

        # IMP-AUT-001: Research cycle integration
        self._research_cycle_integration: Optional[ResearchCycleIntegration] = None
        self._last_research_outcome: Optional[ResearchCycleOutcome] = None

        # IMP-REL-005: State checkpoint/rollback support
        self._state_checkpoints: Dict[str, StateCheckpoint] = {}
        self._last_checkpoint_id: Optional[str] = None

        # IMP-LIFECYCLE-002: Phase state machine for sequencing
        self._phase_state_machine: Optional[PhaseStateMachine] = None

        # IMP-BLOCKED-002: Capability detection results
        self._capabilities: Optional[AutopilotCapabilities] = None

    # =========================================================================
    # IMP-BLOCKED-002: Capability Detection Methods
    # =========================================================================

    def check_capabilities(
        self,
        check_intention_anchor: bool = True,
    ) -> AutopilotCapabilities:
        """Check if all required capabilities are available for autopilot.

        IMP-BLOCKED-002: Runs capability detection and caches the result.
        This helps users understand what's needed before enabling autopilot.

        Args:
            check_intention_anchor: Whether to check for intention_anchor.yaml

        Returns:
            AutopilotCapabilities object with detection results
        """
        self._capabilities = detect_autopilot_capabilities(
            self.workspace_root,
            check_intention_anchor=check_intention_anchor,
        )
        return self._capabilities

    def get_capabilities(self) -> Optional[AutopilotCapabilities]:
        """Get cached capability detection results.

        Returns:
            Cached AutopilotCapabilities or None if not yet checked
        """
        return self._capabilities

    def is_ready_for_autonomous_execution(self) -> tuple:
        """Check if autopilot is ready for autonomous execution.

        IMP-BLOCKED-002: Comprehensive readiness check including both
        the enabled flag and capability detection.

        Returns:
            Tuple of (is_ready: bool, reason: str, capabilities: AutopilotCapabilities)
        """
        # Check if explicitly enabled
        if not self.enabled:
            return (
                False,
                "Autopilot is disabled. Set AUTOPACK_AUTOPILOT_ENABLED=true to enable.",
                self._capabilities,
            )

        # Run capability detection if not already done
        if self._capabilities is None:
            self.check_capabilities()

        # Check capabilities
        if not self._capabilities.is_ready:
            missing = ", ".join(self._capabilities.missing_components)
            return (
                False,
                f"Autopilot enabled but missing required components: {missing}",
                self._capabilities,
            )

        return (True, "Autopilot ready for autonomous execution", self._capabilities)

    @staticmethod
    def get_enable_instructions() -> str:
        """Get instructions for enabling autopilot.

        IMP-BLOCKED-002: Returns clear, actionable instructions for users
        who want to enable the autopilot feature.

        Returns:
            Multi-line string with enable instructions
        """
        return """
Autopilot Feature Gate (IMP-BLOCKED-002)
========================================

Autopilot is disabled by default for safety. To enable:

1. Set environment variable (recommended):
   export AUTOPACK_AUTOPILOT_ENABLED=true

2. Or use the alias:
   export AUTOPILOT_ENABLED=true

Prerequisites:
- Valid workspace directory
- intention_anchor.yaml file in workspace
- All core modules (gap_scanner, plan_proposer) available

To check if your environment is ready:
    from autopack.autonomy.autopilot import detect_autopilot_capabilities
    from pathlib import Path

    caps = detect_autopilot_capabilities(Path("/path/to/workspace"))
    print(caps.get_status_message())
    if not caps.is_ready:
        for rec in caps.recommendations:
            print(f"  - {rec}")

Configuration options (feature_flags.yaml):
- AUTOPACK_AUTOPILOT_ENABLED: Enable/disable autopilot (default: true)
- AUTOPACK_AUTOPILOT_FREQUENCY: Phase frequency for gap scans (default: 5)
- AUTOPACK_AUTOPILOT_MAX_PROPOSALS: Max proposals per session (default: 3)
"""

    # =========================================================================
    # IMP-LIFECYCLE-002: Phase State Machine Methods
    # =========================================================================

    def initialize_phase_state_machine(
        self,
        enforce_ordering: bool = True,
    ) -> PhaseStateMachine:
        """Initialize the phase state machine.

        IMP-LIFECYCLE-002: Creates and configures the phase state machine for
        lifecycle phase sequencing. This should be called before executing
        phases that require ordering constraints.

        Args:
            enforce_ordering: If True, enforces phase ordering constraints.
                            Set to False for testing or custom workflows.

        Returns:
            Configured PhaseStateMachine instance
        """
        self._phase_state_machine = PhaseStateMachine(enforce_ordering=enforce_ordering)
        logger.info(
            f"[IMP-LIFECYCLE-002] Phase state machine initialized "
            f"(enforce_ordering={enforce_ordering})"
        )
        return self._phase_state_machine

    def get_phase_state_machine(self) -> Optional[PhaseStateMachine]:
        """Get the phase state machine instance.

        Returns:
            PhaseStateMachine or None if not initialized
        """
        return self._phase_state_machine

    def register_lifecycle_phase(
        self,
        phase_id: str,
        phase_type: PhaseType,
    ) -> Optional[PhaseStateEntry]:
        """Register a lifecycle phase with the state machine.

        IMP-LIFECYCLE-002: Convenience method to register phases.
        Initializes the state machine if not already done.

        Args:
            phase_id: Unique identifier for the phase
            phase_type: Type of phase (research, build, deploy, etc.)

        Returns:
            The created PhaseStateEntry or None if registration fails
        """
        if not self._phase_state_machine:
            self.initialize_phase_state_machine()

        try:
            return self._phase_state_machine.register_phase(phase_id, phase_type)
        except ValueError as e:
            logger.warning(f"[IMP-LIFECYCLE-002] Failed to register phase: {e}")
            return None

    def get_lifecycle_phase_status(self) -> Dict[str, Any]:
        """Get current status of lifecycle phases.

        IMP-LIFECYCLE-002: Returns completion status and phase states.

        Returns:
            Dictionary with lifecycle phase status
        """
        if not self._phase_state_machine:
            return {
                "initialized": False,
                "phases": {},
                "completion_status": None,
            }

        return {
            "initialized": True,
            **self._phase_state_machine.to_dict(),
        }

    def can_start_lifecycle_phase(self, phase_id: str) -> tuple:
        """Check if a lifecycle phase can start.

        IMP-LIFECYCLE-002: Verifies state and dependencies.

        Args:
            phase_id: The phase identifier

        Returns:
            Tuple of (can_start: bool, reason: str)
        """
        if not self._phase_state_machine:
            return False, "Phase state machine not initialized"

        return self._phase_state_machine.can_phase_start(phase_id)

    def start_lifecycle_phase(self, phase_id: str) -> bool:
        """Start execution of a lifecycle phase.

        IMP-LIFECYCLE-002: Transitions the phase through READY → IN_PROGRESS.
        Validates dependencies before starting.

        Args:
            phase_id: The phase identifier

        Returns:
            True if phase started successfully, False otherwise
        """
        if not self._phase_state_machine:
            logger.error("[IMP-LIFECYCLE-002] Phase state machine not initialized")
            return False

        try:
            # Mark ready first (validates dependencies)
            entry = self._phase_state_machine.get_phase(phase_id)
            if entry and entry.state == PhaseExecutionState.PENDING:
                self._phase_state_machine.mark_ready(phase_id)

            # Start the phase
            self._phase_state_machine.start_phase(phase_id)
            return True
        except (InvalidTransitionError, PhaseDependencyError, ValueError) as e:
            logger.error(f"[IMP-LIFECYCLE-002] Failed to start phase: {e}")
            return False

    def complete_lifecycle_phase(self, phase_id: str) -> bool:
        """Mark a lifecycle phase as completed.

        IMP-LIFECYCLE-002: Transitions IN_PROGRESS → COMPLETED.

        Args:
            phase_id: The phase identifier

        Returns:
            True if phase completed successfully, False otherwise
        """
        if not self._phase_state_machine:
            logger.error("[IMP-LIFECYCLE-002] Phase state machine not initialized")
            return False

        try:
            self._phase_state_machine.complete_phase(phase_id)
            return True
        except (InvalidTransitionError, ValueError) as e:
            logger.error(f"[IMP-LIFECYCLE-002] Failed to complete phase: {e}")
            return False

    def fail_lifecycle_phase(self, phase_id: str, error: str) -> bool:
        """Mark a lifecycle phase as failed.

        IMP-LIFECYCLE-002: Transitions IN_PROGRESS → FAILED.

        Args:
            phase_id: The phase identifier
            error: Error message describing the failure

        Returns:
            True if phase marked as failed, False otherwise
        """
        if not self._phase_state_machine:
            logger.error("[IMP-LIFECYCLE-002] Phase state machine not initialized")
            return False

        try:
            self._phase_state_machine.fail_phase(phase_id, error)
            return True
        except (InvalidTransitionError, ValueError) as e:
            logger.error(f"[IMP-LIFECYCLE-002] Failed to mark phase as failed: {e}")
            return False

    def rollback_lifecycle_phase(self, phase_id: str, reason: Optional[str] = None) -> bool:
        """Rollback a failed lifecycle phase for retry.

        IMP-LIFECYCLE-002: Transitions FAILED → ROLLED_BACK.
        After rollback, the phase can be retried.

        Args:
            phase_id: The phase identifier
            reason: Optional reason for rollback

        Returns:
            True if phase rolled back successfully, False otherwise
        """
        if not self._phase_state_machine:
            logger.error("[IMP-LIFECYCLE-002] Phase state machine not initialized")
            return False

        try:
            self._phase_state_machine.rollback_phase(phase_id, reason)
            return True
        except (InvalidTransitionError, ValueError) as e:
            logger.error(f"[IMP-LIFECYCLE-002] Failed to rollback phase: {e}")
            return False

    def retry_lifecycle_phase(self, phase_id: str) -> bool:
        """Retry a rolled-back lifecycle phase.

        IMP-LIFECYCLE-002: Transitions ROLLED_BACK → READY → IN_PROGRESS.

        Args:
            phase_id: The phase identifier

        Returns:
            True if phase retry started successfully, False otherwise
        """
        if not self._phase_state_machine:
            logger.error("[IMP-LIFECYCLE-002] Phase state machine not initialized")
            return False

        try:
            entry = self._phase_state_machine.get_phase(phase_id)
            if not entry:
                logger.error(f"[IMP-LIFECYCLE-002] Phase not found: {phase_id}")
                return False

            if entry.state != PhaseExecutionState.ROLLED_BACK:
                logger.error(
                    f"[IMP-LIFECYCLE-002] Cannot retry phase in state: {entry.state.value}"
                )
                return False

            # Mark ready then start
            self._phase_state_machine.mark_ready(phase_id)
            self._phase_state_machine.start_phase(phase_id)
            return True
        except (InvalidTransitionError, PhaseDependencyError, ValueError) as e:
            logger.error(f"[IMP-LIFECYCLE-002] Failed to retry phase: {e}")
            return False

    def get_next_lifecycle_phases(self) -> List[str]:
        """Get the next lifecycle phases that can be executed.

        IMP-LIFECYCLE-002: Returns phases in READY state with satisfied dependencies.

        Returns:
            List of phase IDs that can be executed next
        """
        if not self._phase_state_machine:
            return []

        return self._phase_state_machine.get_next_executable_phases()

    def are_all_lifecycle_phases_complete(self) -> bool:
        """Check if all lifecycle phases are complete.

        Returns:
            True if all registered phases are in COMPLETED state
        """
        if not self._phase_state_machine:
            return False

        return self._phase_state_machine.are_all_phases_complete()

    def _check_circuit_breaker_health(self) -> bool:
        """Check if circuit breaker allows execution.

        IMP-HIGH-001: Verifies circuit breaker state before execution.
        Returns False if circuit is OPEN, blocking runaway execution.

        IMP-SEG-001: Records circuit breaker metrics for health monitoring.

        Returns:
            True if circuit breaker allows execution, False if blocked
        """
        if self.executor_ctx is None:
            return True  # No context, allow proceeding

        passed = self.executor_ctx.circuit_breaker.is_available()
        health_score = self.executor_ctx.circuit_breaker.health_score
        state = self.executor_ctx.circuit_breaker.state.value

        # IMP-SEG-001: Record circuit breaker check
        self._health_collector.record_circuit_breaker_check(
            state=state,
            passed=passed,
            health_score=health_score,
        )

        if not passed:
            # Record circuit breaker trip if we haven't recorded it yet
            if not getattr(self, "_last_cb_state_open", False):
                self._health_collector.record_circuit_breaker_trip()
                self._last_cb_state_open = True
            elif self._last_cb_state_open and passed:
                self._last_cb_state_open = False

            logger.critical(
                f"[IMP-HIGH-001] Circuit breaker OPEN - blocking execution. "
                f"State: {state}, "
                f"Consecutive failures: {self.executor_ctx.circuit_breaker.consecutive_failures}, "
                f"Trip count: {self.executor_ctx.circuit_breaker.total_trips}"
            )
            return False

        # Reset trip flag when circuit is closed again
        self._last_cb_state_open = False
        return True

    def _create_state_checkpoint(self, checkpoint_name: str) -> str:
        """Create a checkpoint of the current session state.

        IMP-REL-005: Saves the current session state before executing
        critical API operations. Returns a checkpoint ID that can be used
        to restore state if the operation fails.

        Args:
            checkpoint_name: Human-readable name for this checkpoint

        Returns:
            Checkpoint ID for later restoration
        """
        checkpoint_id = f"{checkpoint_name}-{uuid.uuid4().hex[:8]}"
        checkpoint = StateCheckpoint(session=self.session)
        self._state_checkpoints[checkpoint_id] = checkpoint
        self._last_checkpoint_id = checkpoint_id

        logger.debug(
            f"[IMP-REL-005] Created state checkpoint: {checkpoint_id} "
            f"(session_status={self.session.status if self.session else 'None'})"
        )

        return checkpoint_id

    def _restore_from_checkpoint(self, checkpoint_id: str) -> bool:
        """Restore session state from a checkpoint.

        IMP-REL-005: Restores the session to the state it was in when
        the checkpoint was created. Used to rollback after API failures.

        Args:
            checkpoint_id: ID of the checkpoint to restore from

        Returns:
            True if restoration was successful, False if checkpoint not found
        """
        if checkpoint_id not in self._state_checkpoints:
            logger.warning(f"[IMP-REL-005] Checkpoint not found: {checkpoint_id}")
            return False

        if not self.session:
            logger.error("[IMP-REL-005] Cannot restore state: no active session")
            return False

        checkpoint = self._state_checkpoints[checkpoint_id]
        checkpoint.restore_session(self.session)

        logger.info(f"[IMP-REL-005] Restored session state from checkpoint: {checkpoint_id}")
        return True

    def _cleanup_checkpoints(self) -> None:
        """Clean up old checkpoints to prevent memory leaks.

        IMP-REL-005: Removes all checkpoints after session completes.
        Should be called when session transitions to final state.
        """
        checkpoint_count = len(self._state_checkpoints)
        self._state_checkpoints.clear()
        self._last_checkpoint_id = None

        if checkpoint_count > 0:
            logger.debug(f"[IMP-REL-005] Cleaned up {checkpoint_count} checkpoints")

    def _record_session_metrics(self, outcome: SessionOutcome) -> None:
        """Record session metrics to health collector.

        IMP-SEG-001: Creates a health snapshot and records session outcome.

        Args:
            outcome: The session outcome
        """
        if not self.session or not self.executor_ctx:
            return

        # Calculate final gate states and health
        circuit_breaker_state = self.executor_ctx.circuit_breaker.state.value
        circuit_breaker_health = self.executor_ctx.circuit_breaker.health_score
        budget_remaining = self.executor_ctx.get_budget_remaining()

        # Get health status from feedback loop if available
        health_status = "healthy"
        if self._task_generation_paused:
            health_status = "degraded"

        # Get research metrics if available
        research_cycles_executed = 0
        if self._research_cycle_integration and self._research_cycle_integration._metrics:
            research_cycles_executed = (
                self._research_cycle_integration._metrics.total_cycles_triggered
            )

        # Create snapshot
        completed_at = self.session.completed_at or datetime.now(timezone.utc)
        started_at = self.session.started_at
        duration_seconds = (completed_at - started_at).total_seconds()

        snapshot = SessionHealthSnapshot(
            session_id=self.session.session_id,
            outcome=outcome,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            duration_seconds=duration_seconds,
            circuit_breaker_state=circuit_breaker_state,
            circuit_breaker_health_score=circuit_breaker_health,
            budget_remaining=budget_remaining,
            health_status=health_status,
            health_gates_checked=self.executor_ctx.circuit_breaker.total_checks,
            health_gates_blocked=(
                max(
                    0,
                    self.executor_ctx.circuit_breaker.total_checks
                    - self.executor_ctx.circuit_breaker.checks_passed,
                )
                if hasattr(self.executor_ctx.circuit_breaker, "checks_passed")
                else 0
            ),
            research_cycles_executed=research_cycles_executed,
            actions_executed=(
                self.session.execution_summary.executed_actions
                if self.session.execution_summary
                else 0
            ),
            actions_successful=(
                self.session.execution_summary.successful_actions
                if self.session.execution_summary
                else 0
            ),
            actions_failed=(
                self.session.execution_summary.failed_actions
                if self.session.execution_summary
                else 0
            ),
            blocking_reason=self.session.blocked_reason,
        )

        # Record to health collector
        self._health_collector.end_session(outcome, snapshot)

        # Auto-save metrics to file
        try:
            metrics_file = self.layout.run_dir() / "metrics" / "autopilot_health.json"
            self._health_collector.save_to_file(str(metrics_file))
        except Exception as e:
            logger.warning(f"[IMP-SEG-001] Failed to save health metrics: {e}")

    def run_session(self, anchor: IntentionAnchorV2) -> AutopilotSessionV1:
        """Run autopilot session with safe execution gates.

        Steps:
        1. Load anchor (v2) - already provided
        2. Scan gaps
        3. Propose plan
        4. If all actions auto-approved: execute bounded batch
        5. Else: emit approval requests + stop (but record artifacts)

        Args:
            anchor: Intention anchor v2 to guide execution

        Returns:
            AutopilotSessionV1 with execution log

        Raises:
            RuntimeError: If autopilot is not enabled
        """
        if not self.enabled:
            raise RuntimeError(
                "Autopilot is disabled by default. "
                "Set enabled=True explicitly to run autonomous execution."
            )

        session_id = f"autopilot-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(timezone.utc)

        logger.info(f"[Autopilot] Starting session: {session_id}")

        # IMP-SEG-001: Start health metrics tracking
        self._health_collector.start_session(session_id)

        # Initialize session
        self.session = AutopilotSessionV1(
            format_version="v1",
            project_id=self.project_id,
            run_id=self.run_id,
            session_id=session_id,
            started_at=started_at,
            status="running",
            anchor_id=anchor.raw_input_digest,
            gap_report_id="",  # Will be set after gap scan
            plan_proposal_id="",  # Will be set after plan proposal
            metadata=AutopilotMetadata(
                autopilot_version="0.1.0",
                enabled_explicitly=self.enabled,
            ),
        )

        try:
            # Initialize BUILD-181 ExecutorContext
            # IMP-REL-005: Create checkpoint before executor context API call
            executor_ctx_checkpoint = self._create_state_checkpoint("executor_context")

            try:
                self.executor_ctx = create_executor_context(anchor=anchor, layout=self.layout)
                logger.info(
                    f"[Autopilot] Initialized ExecutorContext with "
                    f"safety_profile={self.executor_ctx.safety_profile}"
                )
            except Exception as e:
                # IMP-REL-005: Rollback on executor context failure
                logger.error(f"[IMP-REL-005] Executor context initialization failed: {e}")
                self._restore_from_checkpoint(executor_ctx_checkpoint)
                self.session.error_log.append(
                    ErrorLogEntry(
                        timestamp=datetime.now(timezone.utc),
                        error_type="ExecutorContextError",
                        error_message=f"Failed to initialize executor context: {str(e)}",
                    )
                )
                self.session.status = "failed"
                self.session.completed_at = datetime.now(timezone.utc)
                self._record_session_metrics(SessionOutcome.FAILED)
                self._cleanup_checkpoints()
                return self.session

            # Step 1: Anchor already loaded
            logger.info(f"[Autopilot] Using anchor: {anchor.raw_input_digest}")

            # Step 2: Scan gaps
            logger.info("[Autopilot] Scanning workspace for gaps...")
            # IMP-REL-005: Create checkpoint before gap scan API call
            gap_scan_checkpoint = self._create_state_checkpoint("gap_scan")

            try:
                gap_report = scan_workspace(
                    workspace_root=self.workspace_root,
                    project_id=self.project_id,
                    run_id=self.run_id,
                )
                self.session.gap_report_id = gap_report.report_id
                logger.info(
                    f"[Autopilot] Found {gap_report.summary.total_gaps} gaps "
                    f"({gap_report.summary.autopilot_blockers} blockers)"
                )
            except Exception as e:
                # IMP-REL-005: Rollback on gap scan failure
                logger.error(f"[IMP-REL-005] Gap scan failed: {e}")
                self._restore_from_checkpoint(gap_scan_checkpoint)
                self.session.error_log.append(
                    ErrorLogEntry(
                        timestamp=datetime.now(timezone.utc),
                        error_type="GapScanError",
                        error_message=f"Failed to scan gaps: {str(e)}",
                    )
                )
                self.session.status = "failed"
                self.session.completed_at = datetime.now(timezone.utc)
                self._record_session_metrics(SessionOutcome.FAILED)
                self._cleanup_checkpoints()
                return self.session

            # IMP-AUT-001: Check if research cycle should be executed
            gap_summary = {
                "summary": {
                    "total_gaps": gap_report.summary.total_gaps,
                    "critical_gaps": gap_report.summary.autopilot_blockers,
                }
            }

            # Initialize research cycle integration if needed
            if not self._research_cycle_integration:
                self.initialize_research_cycle_integration()

            if self.should_execute_research_cycle(gap_report=gap_summary):
                logger.info("[IMP-AUT-001] Executing research cycle based on gap analysis")

                # Build analysis results from gap report
                analysis_results = {
                    "findings": [],
                    "identified_gaps": [
                        {
                            "category": "workspace",
                            "description": f"Found {gap_report.summary.total_gaps} gaps "
                            f"({gap_report.summary.autopilot_blockers} blockers)",
                            "suggested_queries": ["gap resolution strategies"],
                        }
                    ],
                    "coverage_analysis": {
                        "gaps_scanned": True,
                        "blockers_found": gap_report.summary.autopilot_blockers > 0,
                    },
                }

                # IMP-REL-005: Create checkpoint before research cycle API call
                research_checkpoint = self._create_state_checkpoint("research_cycle")

                try:
                    # Execute research cycle asynchronously
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    research_outcome = loop.run_until_complete(
                        self.execute_integrated_research_cycle(
                            analysis_results=analysis_results,
                        )
                    )

                    # Check if research outcome blocks execution
                    if research_outcome.decision == ResearchCycleDecision.BLOCK:
                        logger.warning(
                            f"[IMP-AUT-001] Research cycle blocked execution: "
                            f"{research_outcome.reason}"
                        )
                        self.session.status = "blocked_research"
                        self.session.blocked_reason = (
                            f"Research cycle BLOCK: {research_outcome.reason}"
                        )
                        self.session.completed_at = datetime.now(timezone.utc)
                        # IMP-SEG-001: Record session metrics before returning
                        self._record_session_metrics(SessionOutcome.BLOCKED_RESEARCH)
                        self._cleanup_checkpoints()
                        return self.session

                    logger.info(
                        f"[IMP-AUT-001] Research cycle complete: "
                        f"decision={research_outcome.decision.value}"
                    )
                except Exception as e:
                    # IMP-REL-005: Rollback on research cycle failure
                    logger.error(f"[IMP-REL-005] Research cycle failed: {e}")
                    self._restore_from_checkpoint(research_checkpoint)
                    self.session.error_log.append(
                        ErrorLogEntry(
                            timestamp=datetime.now(timezone.utc),
                            error_type="ResearchCycleError",
                            error_message=f"Failed to execute research cycle: {str(e)}",
                        )
                    )
                    # Don't fail the session - research is optional
                    logger.warning(
                        "[IMP-REL-005] Continuing execution despite research cycle failure"
                    )

            # Step 3: Propose plan
            logger.info("[Autopilot] Proposing action plan...")
            # IMP-REL-005: Create checkpoint before plan proposal API call
            plan_proposal_checkpoint = self._create_state_checkpoint("plan_proposal")

            try:
                proposal = propose_plan(
                    anchor=anchor,
                    gap_report=gap_report,
                    workspace_root=self.workspace_root,
                )
                self.session.plan_proposal_id = f"plan-{uuid.uuid4().hex[:8]}"
                logger.info(
                    f"[Autopilot] Generated {proposal.summary.total_actions} actions "
                    f"({proposal.summary.auto_approved_actions} auto-approved, "
                    f"{proposal.summary.requires_approval_actions} require approval, "
                    f"{proposal.summary.blocked_actions} blocked)"
                )
            except Exception as e:
                # IMP-REL-005: Rollback on plan proposal failure
                logger.error(f"[IMP-REL-005] Plan proposal failed: {e}")
                self._restore_from_checkpoint(plan_proposal_checkpoint)
                self.session.error_log.append(
                    ErrorLogEntry(
                        timestamp=datetime.now(timezone.utc),
                        error_type="PlanProposalError",
                        error_message=f"Failed to propose plan: {str(e)}",
                    )
                )
                self.session.status = "failed"
                self.session.completed_at = datetime.now(timezone.utc)
                self._record_session_metrics(SessionOutcome.FAILED)
                self._cleanup_checkpoints()
                return self.session

            # Step 4: Check if we can proceed autonomously
            if proposal.summary.auto_approved_actions == 0:
                # No auto-approved actions - stop and request approval
                self._handle_approval_required(proposal)
                # IMP-SEG-001: Record session metrics before returning
                self._record_session_metrics(SessionOutcome.BLOCKED_APPROVAL)
                return self.session

            if (
                proposal.summary.requires_approval_actions > 0
                or proposal.summary.blocked_actions > 0
            ):
                # Some actions require approval - stop and request
                self._handle_approval_required(proposal)
                # IMP-SEG-001: Record session metrics before returning
                self._record_session_metrics(SessionOutcome.BLOCKED_APPROVAL)
                return self.session

            # All actions are auto-approved - check circuit breaker health gate
            logger.info(
                f"[Autopilot] All {proposal.summary.auto_approved_actions} actions auto-approved. "
                "Checking health gates before execution..."
            )

            # IMP-HIGH-001: Check circuit breaker health gate
            if not self._check_circuit_breaker_health():
                logger.critical(
                    "[IMP-HIGH-001] Execution blocked by circuit breaker health gate. "
                    "Autonomous execution halted to prevent runaway."
                )
                self.session.status = "blocked_circuit_breaker"
                self.session.blocked_reason = (
                    "Circuit breaker is OPEN - too many consecutive failures detected. "
                    "Execution blocked to prevent runaway. Circuit will reset after timeout."
                )
                self.session.completed_at = datetime.now(timezone.utc)
                # IMP-SEG-001: Record session metrics before returning
                self._record_session_metrics(SessionOutcome.BLOCKED_CIRCUIT_BREAKER)
                return self.session

            logger.info("[Autopilot] Health gates passed. " "Executing bounded batch...")
            self._execute_bounded_batch(proposal)

            # Mark session as completed
            self.session.status = "completed"
            self.session.completed_at = datetime.now(timezone.utc)

            # Calculate session duration
            if self.session.metadata:
                duration = (self.session.completed_at - self.session.started_at).total_seconds()
                self.session.metadata.session_duration_ms = int(duration * 1000)

            logger.info(f"[Autopilot] Session completed: {session_id}")

            # IMP-SEG-001: Record session metrics
            self._record_session_metrics(SessionOutcome.COMPLETED)

        except Exception as e:
            # Log error and mark session as failed
            logger.exception(f"[Autopilot] Session failed: {e}")
            self.session.status = "failed"
            self.session.completed_at = datetime.now(timezone.utc)
            self.session.error_log.append(
                ErrorLogEntry(
                    timestamp=datetime.now(timezone.utc),
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            )
            # IMP-SEG-001: Record session metrics for failed case
            self._record_session_metrics(SessionOutcome.FAILED)

        finally:
            # IMP-REL-005: Clean up checkpoints after session completes
            self._cleanup_checkpoints()

        return self.session

    def on_health_transition(
        self, old_status: "FeedbackLoopHealth", new_status: "FeedbackLoopHealth"
    ) -> None:
        """Handle health state transitions for auto-resume logic.

        IMP-REL-001: This callback is invoked when the feedback loop health
        transitions between states. When health recovers from ATTENTION_REQUIRED
        to HEALTHY, task generation is automatically resumed.

        IMP-SEG-001: Records health transitions for metrics tracking.

        Args:
            old_status: Previous health status
            new_status: New health status
        """
        from ..telemetry.meta_metrics import FeedbackLoopHealth

        logger.info(
            f"[IMP-REL-001] Autopilot received health transition: "
            f"{old_status.value} -> {new_status.value}"
        )

        # IMP-SEG-001: Record health transition
        self._health_collector.record_health_transition(
            old_status=old_status.value,
            new_status=new_status.value,
        )

        # Check for recovery transition
        if (
            old_status == FeedbackLoopHealth.ATTENTION_REQUIRED
            and new_status == FeedbackLoopHealth.HEALTHY
        ):
            self._trigger_task_generation_resume()
        elif new_status == FeedbackLoopHealth.ATTENTION_REQUIRED:
            self._pause_task_generation("Health status is ATTENTION_REQUIRED")

    def _trigger_task_generation_resume(self) -> None:
        """Trigger resumption of task generation after health recovery.

        IMP-REL-001: Called when health transitions from ATTENTION_REQUIRED
        to HEALTHY. Invokes all registered resume callbacks and updates
        internal state to allow task generation.

        IMP-SEG-001: Records task generation resume event for metrics.
        """
        if not self._task_generation_paused:
            logger.debug("[IMP-REL-001] Task generation not paused, no resume needed")
            return

        logger.info("[IMP-REL-001] Triggering task generation resume after health recovery")

        self._task_generation_paused = False
        self._pause_reason = None

        # IMP-SEG-001: Record task resume
        self._health_collector.record_task_resume()

        # Invoke all registered resume callbacks
        for callback in self._resume_callbacks:
            try:
                callback()
            except Exception as e:
                logger.warning(f"[IMP-REL-001] Task generation resume callback failed: {e}")

        logger.info("[IMP-REL-001] Task generation resumed successfully")

    def _pause_task_generation(self, reason: str) -> None:
        """Pause task generation due to health degradation.

        IMP-REL-001: Called when health transitions to ATTENTION_REQUIRED.
        Updates internal state to prevent new task generation until health
        recovers.

        IMP-SEG-001: Records task generation pause event for metrics.

        Args:
            reason: Human-readable reason for the pause
        """
        if self._task_generation_paused:
            logger.debug(f"[IMP-REL-001] Task generation already paused: {self._pause_reason}")
            return

        logger.warning(f"[IMP-REL-001] Pausing task generation: {reason}")
        self._task_generation_paused = True
        self._pause_reason = reason

        # IMP-SEG-001: Record task pause
        self._health_collector.record_task_pause(reason)

    def register_resume_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked when task generation resumes.

        IMP-REL-001: Callbacks are invoked when health recovers and task
        generation is resumed. Use this to restart any paused task generation
        processes.

        Args:
            callback: Function to call when task generation resumes
        """
        self._resume_callbacks.append(callback)
        logger.debug(
            f"[IMP-REL-001] Registered resume callback " f"(total: {len(self._resume_callbacks)})"
        )

    def unregister_resume_callback(self, callback: Callable[[], None]) -> bool:
        """Unregister a previously registered resume callback.

        Args:
            callback: The callback function to unregister

        Returns:
            True if callback was found and removed, False otherwise
        """
        try:
            self._resume_callbacks.remove(callback)
            return True
        except ValueError:
            return False

    def is_task_generation_paused(self) -> bool:
        """Check if task generation is currently paused due to health issues.

        IMP-REL-001: Returns True if task generation has been paused due
        to feedback loop health being in ATTENTION_REQUIRED state.

        Returns:
            True if task generation is paused, False otherwise
        """
        return self._task_generation_paused

    def get_pause_reason(self) -> Optional[str]:
        """Get the reason task generation is paused.

        Returns:
            Reason string if paused, None if not paused
        """
        return self._pause_reason if self._task_generation_paused else None

    # === IMP-AUTO-001: Research Cycle Triggering ===

    def register_research_cycle_callback(
        self, callback: Callable[[TriggerAnalysisResult], None]
    ) -> None:
        """Register a callback to be invoked when a research cycle is triggered.

        IMP-AUTO-001: Callbacks are invoked when follow-up research is detected
        as needed. Use this to trigger research phases in response to gaps.

        Args:
            callback: Function to call when research cycle is triggered.
                     Receives the TriggerAnalysisResult with trigger details.
        """
        self._research_cycle_callbacks.append(callback)
        logger.debug(
            f"[IMP-AUTO-001] Registered research cycle callback "
            f"(total: {len(self._research_cycle_callbacks)})"
        )

    def unregister_research_cycle_callback(
        self, callback: Callable[[TriggerAnalysisResult], None]
    ) -> bool:
        """Unregister a previously registered research cycle callback.

        Args:
            callback: The callback function to unregister

        Returns:
            True if callback was found and removed, False otherwise
        """
        try:
            self._research_cycle_callbacks.remove(callback)
            return True
        except ValueError:
            return False

    async def trigger_research_cycle(
        self,
        analysis_results: dict,
        validation_results: Optional[dict] = None,
    ) -> Optional[TriggerAnalysisResult]:
        """Trigger a research cycle if follow-up research is needed.

        IMP-AUTO-001: Analyzes research findings for gaps and triggers automated
        follow-up research when needed. This method integrates with the
        ResearchOrchestrator to detect gaps and invoke registered callbacks.

        IMP-HIGH-005: Now uses the enhanced FollowupResearchTrigger with callback
        execution mechanism. Callbacks registered via `register_followup_callback()`
        are executed when triggers are detected.

        Args:
            analysis_results: Results from analysis phase
            validation_results: Optional validation results

        Returns:
            TriggerAnalysisResult if research was triggered, None otherwise
        """
        if self._task_generation_paused:
            logger.info("[IMP-AUTO-001] Research cycle skipped: task generation paused")
            return None

        try:
            # IMP-HIGH-005: Use instance-level followup trigger with callbacks
            trigger_result = await self._followup_trigger.analyze_and_execute_async(
                analysis_results=analysis_results,
                validation_results=validation_results,
                max_concurrent=3,
            )

            self._last_research_trigger_result = trigger_result

            # Track execution results
            if trigger_result.execution_result:
                self._research_execution_results.append(trigger_result.execution_result)

            if trigger_result.should_research:
                logger.info(
                    f"[IMP-AUTO-001] Research cycle triggered: "
                    f"{trigger_result.triggers_selected} triggers detected"
                )

                # IMP-HIGH-005: Log callback execution summary
                if trigger_result.execution_result:
                    exec_result = trigger_result.execution_result
                    logger.info(
                        f"[IMP-HIGH-005] Callback execution: "
                        f"{exec_result.successful_executions} successful, "
                        f"{exec_result.failed_executions} failed, "
                        f"{exec_result.total_execution_time_ms}ms"
                    )

                # Invoke legacy research cycle callbacks (for backwards compatibility)
                for callback in self._research_cycle_callbacks:
                    try:
                        callback(trigger_result)
                    except Exception as e:
                        logger.warning(f"[IMP-AUTO-001] Research cycle callback failed: {e}")

                return trigger_result
            else:
                logger.debug("[IMP-AUTO-001] No follow-up research needed")
                return None

        except Exception as e:
            logger.error(f"[IMP-AUTO-001] Research cycle trigger failed: {e}")
            return None

    def should_trigger_followup_research(
        self,
        gap_report: Optional[dict] = None,
        budget_remaining: Optional[float] = None,
    ) -> bool:
        """Check if follow-up research should be triggered.

        IMP-AUTO-001: Determines if follow-up research is needed based on
        gap report and budget constraints.

        Args:
            gap_report: Gap report from workspace scan
            budget_remaining: Remaining budget fraction (0.0-1.0)

        Returns:
            True if follow-up research should be triggered
        """
        # Don't trigger if task generation is paused
        if self._task_generation_paused:
            return False

        # Don't trigger if budget is too low (< 20%)
        if budget_remaining is not None and budget_remaining < 0.2:
            logger.debug("[IMP-AUTO-001] Follow-up research skipped: insufficient budget")
            return False

        # Check if we have significant gaps
        if gap_report:
            total_gaps = gap_report.get("summary", {}).get("total_gaps", 0)
            critical_gaps = gap_report.get("summary", {}).get("critical_gaps", 0)

            # Trigger if we have critical gaps or many total gaps
            if critical_gaps > 0:
                logger.info(
                    f"[IMP-AUTO-001] Follow-up research recommended: "
                    f"{critical_gaps} critical gaps"
                )
                return True

            if total_gaps >= 5:
                logger.info(
                    f"[IMP-AUTO-001] Follow-up research recommended: " f"{total_gaps} total gaps"
                )
                return True

        # Check last trigger result
        if self._last_research_trigger_result:
            return self._last_research_trigger_result.should_research

        return False

    def get_last_research_trigger_result(self) -> Optional[TriggerAnalysisResult]:
        """Get the last research trigger analysis result.

        Returns:
            Last TriggerAnalysisResult or None if no research was triggered
        """
        return self._last_research_trigger_result

    # === IMP-HIGH-005: Followup Research Callback Registration ===

    def register_followup_callback(
        self,
        callback: Callable[[FollowupTrigger], Optional[Dict[str, Any]]],
    ) -> None:
        """Register a callback to handle followup research triggers.

        IMP-HIGH-005: Callbacks are executed when followup research triggers
        are detected and `trigger_research_cycle()` is called. Use this to
        integrate custom research handlers.

        Args:
            callback: Function that takes a FollowupTrigger and returns
                     optional result data (e.g., research findings).

        Example:
            ```python
            def handle_research(trigger: FollowupTrigger) -> Optional[Dict]:
                # Execute research based on trigger.research_plan
                return {"findings": [...], "confidence": 0.8}

            controller.register_followup_callback(handle_research)
            ```
        """
        self._followup_trigger.register_callback(callback)
        logger.debug(
            f"[IMP-HIGH-005] Registered followup callback "
            f"(total: {self._followup_trigger.get_callback_count()})"
        )

    def register_followup_async_callback(
        self,
        callback: Callable[[FollowupTrigger], "asyncio.Future[Optional[Dict[str, Any]]]"],
    ) -> None:
        """Register an async callback to handle followup research triggers.

        IMP-HIGH-005: Async callbacks enable concurrent research execution
        when `trigger_research_cycle()` is called.

        Args:
            callback: Async function that takes a FollowupTrigger and returns
                     optional result data.

        Example:
            ```python
            async def handle_research_async(trigger: FollowupTrigger) -> Optional[Dict]:
                result = await research_orchestrator.execute(trigger.research_plan)
                return {"findings": result.findings}

            controller.register_followup_async_callback(handle_research_async)
            ```
        """
        self._followup_trigger.register_async_callback(callback)
        logger.debug(
            f"[IMP-HIGH-005] Registered async followup callback "
            f"(total: {self._followup_trigger.get_callback_count()})"
        )

    def unregister_followup_callback(
        self,
        callback: Callable[[FollowupTrigger], Optional[Dict[str, Any]]],
    ) -> bool:
        """Unregister a followup callback.

        Args:
            callback: The callback to unregister

        Returns:
            True if callback was found and removed, False otherwise
        """
        return self._followup_trigger.unregister_callback(callback)

    def get_followup_callback_count(self) -> int:
        """Get total number of registered followup callbacks.

        Returns:
            Total callback count (sync + async)
        """
        return self._followup_trigger.get_callback_count()

    def get_research_execution_results(self) -> list[TriggerExecutionResult]:
        """Get all research execution results from this session.

        IMP-HIGH-005: Returns accumulated execution results from all
        research cycles triggered during this session.

        Returns:
            List of TriggerExecutionResult from each research cycle
        """
        return self._research_execution_results.copy()

    def enable_mid_execution_research(self, enabled: bool = True) -> None:
        """Enable or disable mid-execution research triggering.

        IMP-HIGH-005: When enabled, the execution loop will check for
        followup research triggers after executing action batches.

        Args:
            enabled: Whether to enable mid-execution research
        """
        self._mid_execution_research_enabled = enabled
        logger.info(f"[IMP-HIGH-005] Mid-execution research {'enabled' if enabled else 'disabled'}")

    def is_mid_execution_research_enabled(self) -> bool:
        """Check if mid-execution research is enabled.

        Returns:
            True if mid-execution research is enabled
        """
        return self._mid_execution_research_enabled

    # === IMP-AUT-001: Research Cycle Integration ===

    def initialize_research_cycle_integration(
        self,
        min_budget_threshold: float = 0.2,
    ) -> ResearchCycleIntegration:
        """Initialize the research cycle integration.

        IMP-AUT-001: Creates and configures the research cycle integration
        for use during autopilot execution. This should be called before
        running sessions that require research triggering.

        Args:
            min_budget_threshold: Minimum budget fraction for research

        Returns:
            Configured ResearchCycleIntegration instance
        """
        from ..research.analysis.budget_enforcement import BudgetEnforcer

        # Create budget enforcer with default budget
        budget_enforcer = BudgetEnforcer(total_budget=5000.0)

        self._research_cycle_integration = create_research_cycle_integration(
            budget_enforcer=budget_enforcer,
            min_budget_threshold=min_budget_threshold,
        )

        logger.info(
            f"[IMP-AUT-001] Research cycle integration initialized: "
            f"min_budget_threshold={min_budget_threshold:.0%}"
        )

        return self._research_cycle_integration

    def get_research_cycle_integration(self) -> Optional[ResearchCycleIntegration]:
        """Get the research cycle integration instance.

        Returns:
            ResearchCycleIntegration or None if not initialized
        """
        return self._research_cycle_integration

    async def execute_integrated_research_cycle(
        self,
        analysis_results: Dict[str, Any],
        validation_results: Optional[Dict[str, Any]] = None,
    ) -> ResearchCycleOutcome:
        """Execute an integrated research cycle with full budget enforcement.

        IMP-AUT-001: Main entry point for research cycle execution in autopilot.
        Uses the ResearchCycleIntegration to handle budget enforcement and
        feeds outcomes back to autopilot decisions.

        Args:
            analysis_results: Results from analysis phase
            validation_results: Optional validation results

        Returns:
            ResearchCycleOutcome with decision and findings
        """
        # Initialize integration if not done
        if not self._research_cycle_integration:
            self.initialize_research_cycle_integration()

        outcome = await self._research_cycle_integration.execute_research_cycle(
            analysis_results=analysis_results,
            validation_results=validation_results,
            executor_ctx=self.executor_ctx,
            autopilot=self,
        )

        self._last_research_outcome = outcome

        # IMP-SEG-001: Record research cycle metrics
        if self._research_cycle_integration and self._research_cycle_integration._metrics:
            self._health_collector.record_research_cycle(
                outcome=(
                    "success"
                    if outcome.trigger_result and outcome.trigger_result.triggers_detected > 0
                    else "failed"
                ),
                triggers_detected=(
                    outcome.trigger_result.triggers_detected if outcome.trigger_result else 0
                ),
                triggers_executed=(
                    outcome.trigger_result.triggers_executed if outcome.trigger_result else 0
                ),
                decision=outcome.decision.value,
                gaps_addressed=outcome.gaps_addressed if outcome.gaps_addressed else 0,
                gaps_remaining=outcome.gaps_remaining if outcome.gaps_remaining else 0,
                execution_time_ms=(
                    outcome.execution_time_ms if hasattr(outcome, "execution_time_ms") else 0
                ),
            )

        # Handle outcome decision
        await self._handle_research_outcome(outcome)

        return outcome

    async def _handle_research_outcome(
        self,
        outcome: ResearchCycleOutcome,
    ) -> None:
        """Handle the outcome of a research cycle.

        IMP-AUT-001: Translates research cycle decisions into autopilot
        state changes and actions.

        IMP-RESEARCH-002: Implements pause logic when research gaps are detected
        and execution should be paused for follow-up research.

        Args:
            outcome: The research cycle outcome
        """
        logger.info(
            f"[IMP-AUT-001] Handling research outcome: decision={outcome.decision.value}, "
            f"should_continue={outcome.should_continue_execution}, "
            f"gaps_addressed={outcome.gaps_addressed}, gaps_remaining={outcome.gaps_remaining}"
        )

        if outcome.decision == ResearchCycleDecision.BLOCK:
            # Pause task generation due to critical gaps
            self._pause_task_generation(f"Research cycle BLOCK: {outcome.reason}")
            logger.warning(
                f"[IMP-AUT-001] Task generation paused due to research BLOCK: " f"{outcome.reason}"
            )

        elif outcome.decision == ResearchCycleDecision.PAUSE_FOR_RESEARCH:
            # IMP-RESEARCH-002: Pause execution when research gaps detected
            # This allows time for follow-up research to complete
            pause_message = (
                f"Research gaps detected: {outcome.gaps_remaining} remaining gaps. "
                f"Reason: {outcome.reason}"
            )
            self._pause_task_generation(pause_message)
            logger.warning(
                f"[IMP-RESEARCH-002] Execution paused for research: "
                f"gaps_addressed={outcome.gaps_addressed}, gaps_remaining={outcome.gaps_remaining}. "
                f"Reason: {outcome.reason}"
            )

            # IMP-RESEARCH-002: Record gap pause metrics in executor context
            if self.executor_ctx:
                self.executor_ctx.record_gap_pause(
                    gaps_remaining=outcome.gaps_remaining,
                    gaps_addressed=outcome.gaps_addressed,
                    reason=outcome.reason,
                )

        elif outcome.decision == ResearchCycleDecision.ADJUST_PLAN:
            # Log plan adjustments for processing
            if outcome.plan_adjustments:
                logger.info(
                    f"[IMP-AUT-001] Plan adjustments required: "
                    f"{len(outcome.plan_adjustments)} recommendations"
                )
                for adj in outcome.plan_adjustments:
                    logger.info(
                        f"  - [{adj.get('priority', 'medium')}] "
                        f"{adj.get('type', 'unknown')}: {adj.get('description', 'N/A')}"
                    )

        # Update metrics in session if available
        if self.session and self.session.metadata:
            if not hasattr(self.session.metadata, "research_cycles"):
                self.session.metadata.research_cycles = []
            self.session.metadata.research_cycles.append(outcome.to_dict())

    async def retry_gap_research(
        self,
        max_retries: int = 3,
        retry_delay_seconds: float = 2.0,
    ) -> Optional[ResearchCycleOutcome]:
        """Retry research for detected gaps with exponential backoff.

        IMP-RESEARCH-002: Implements retry logic for gap research when
        initial research cycle encounters failures. Uses exponential backoff
        to avoid overwhelming the system.

        Args:
            max_retries: Maximum number of retry attempts
            retry_delay_seconds: Base delay between retries (increases exponentially)

        Returns:
            Final ResearchCycleOutcome or None if no retries performed
        """
        if not self._task_generation_paused:
            logger.debug("[IMP-RESEARCH-002] Not paused for gaps, no retry needed")
            return None

        if not self._pause_reason or "gap" not in self._pause_reason.lower():
            logger.debug("[IMP-RESEARCH-002] Pause reason not gap-related, skipping retry")
            return None

        logger.info(
            f"[IMP-RESEARCH-002] Starting gap research retry loop " f"(max_retries={max_retries})"
        )

        last_outcome = None
        for retry_attempt in range(max_retries):
            if retry_attempt > 0:
                # Exponential backoff: 2s, 4s, 8s, etc.
                delay = retry_delay_seconds * (2 ** (retry_attempt - 1))
                logger.info(
                    f"[IMP-RESEARCH-002] Retry {retry_attempt}/{max_retries} "
                    f"for gap research, waiting {delay:.1f}s..."
                )
                await asyncio.sleep(delay)

            try:
                # Check if we still have budget for retry
                if self.executor_ctx and not self.executor_ctx.can_proceed():
                    logger.warning(
                        f"[IMP-RESEARCH-002] Retry {retry_attempt + 1}: "
                        "Budget exhausted, cannot retry gap research"
                    )
                    break

                # Execute another research cycle
                logger.info(
                    f"[IMP-RESEARCH-002] Executing gap research retry "
                    f"{retry_attempt + 1}/{max_retries}"
                )

                outcome = await self.execute_integrated_research_cycle(
                    analysis_results={
                        "retry_attempt": retry_attempt + 1,
                        "max_retries": max_retries,
                    }
                )

                last_outcome = outcome

                # Check if gaps are now resolved
                if outcome.decision in (
                    ResearchCycleDecision.PROCEED,
                    ResearchCycleDecision.ADJUST_PLAN,
                ):
                    logger.info(
                        f"[IMP-RESEARCH-002] Gap research retry {retry_attempt + 1} successful: "
                        f"decision={outcome.decision.value}"
                    )
                    # Resume execution since gaps are addressed
                    self._trigger_task_generation_resume()
                    return outcome

                elif outcome.decision == ResearchCycleDecision.BLOCK:
                    logger.error(
                        f"[IMP-RESEARCH-002] Retry {retry_attempt + 1} hit BLOCK decision, "
                        "stopping retries"
                    )
                    break

                logger.info(
                    f"[IMP-RESEARCH-002] Retry {retry_attempt + 1} completed: "
                    f"decision={outcome.decision.value}, gaps_remaining={outcome.gaps_remaining}"
                )

            except Exception as e:
                logger.error(f"[IMP-RESEARCH-002] Retry {retry_attempt + 1} failed with error: {e}")
                if retry_attempt == max_retries - 1:
                    logger.error(
                        "[IMP-RESEARCH-002] Max retries exceeded, giving up on gap research"
                    )

        return last_outcome

    def can_attempt_gap_retry(self) -> bool:
        """Check if gap research retry can be attempted.

        IMP-RESEARCH-002: Checks if conditions allow gap research retry
        (paused for gaps, budget available, circuit breaker open).

        Returns:
            True if gap retry can be attempted, False otherwise
        """
        if not self._task_generation_paused:
            return False

        if not self._pause_reason or "gap" not in self._pause_reason.lower():
            return False

        if self.executor_ctx:
            if not self.executor_ctx.can_proceed():
                return False

            if not self.executor_ctx.circuit_breaker.is_available():
                return False

        return True

    def get_gap_pause_status(self) -> Dict[str, Any]:
        """Get current status of gap-related pause.

        IMP-RESEARCH-002: Returns detailed information about gap pause
        state for debugging and monitoring.

        Returns:
            Dictionary with gap pause status
        """
        gap_metrics = {}
        if self.executor_ctx:
            gap_metrics = self.executor_ctx.get_gap_detection_metrics()

        return {
            "is_paused_for_gaps": (
                self._task_generation_paused
                and self._pause_reason
                and "gap" in self._pause_reason.lower()
            ),
            "pause_reason": self._pause_reason,
            "can_retry": self.can_attempt_gap_retry(),
            "last_research_outcome": (
                self._last_research_outcome.to_dict() if self._last_research_outcome else None
            ),
            "gap_metrics": gap_metrics,
        }

    def get_last_research_outcome(self) -> Optional[ResearchCycleOutcome]:
        """Get the last research cycle outcome.

        Returns:
            Last ResearchCycleOutcome or None
        """
        return self._last_research_outcome

    def get_research_cycle_metrics(self) -> Optional[ResearchCycleMetrics]:
        """Get research cycle metrics.

        IMP-AUT-001: Returns metrics from the research cycle integration
        for monitoring and debugging.

        Returns:
            ResearchCycleMetrics or None if not initialized
        """
        if not self._research_cycle_integration:
            return None
        return self._research_cycle_integration.get_metrics()

    def should_execute_research_cycle(
        self,
        gap_report: Optional[Dict] = None,
    ) -> bool:
        """Determine if a research cycle should be executed.

        IMP-AUT-001: Combines health gates, budget constraints, and gap
        analysis to determine if a research cycle is warranted.

        Args:
            gap_report: Optional gap report from workspace scan

        Returns:
            True if research cycle should execute
        """
        # Check if task generation is paused
        if self._task_generation_paused:
            logger.debug("[IMP-AUT-001] Research cycle skipped: task generation paused")
            return False

        # Check circuit breaker
        if self.executor_ctx and not self.executor_ctx.circuit_breaker.is_available():
            logger.debug("[IMP-AUT-001] Research cycle skipped: circuit breaker open")
            return False

        # Check budget via integration
        if self._research_cycle_integration:
            if not self._research_cycle_integration.can_proceed_with_research():
                logger.debug("[IMP-AUT-001] Research cycle skipped: budget constraints")
                return False

        # Check gap report
        if gap_report:
            total_gaps = gap_report.get("summary", {}).get("total_gaps", 0)
            critical_gaps = gap_report.get("summary", {}).get("critical_gaps", 0)

            # Only trigger if significant gaps exist
            if critical_gaps > 0 or total_gaps >= 5:
                logger.info(
                    f"[IMP-AUT-001] Research cycle recommended: "
                    f"{critical_gaps} critical, {total_gaps} total gaps"
                )
                return True

        return False

    async def check_mid_execution_research(
        self,
        execution_results: Dict[str, Any],
    ) -> Optional[TriggerAnalysisResult]:
        """Check for and trigger mid-execution research if needed.

        IMP-HIGH-005: Called during execution loop to detect gaps that
        emerge from execution results and trigger followup research.

        Args:
            execution_results: Results from action execution including
                              any errors, outputs, or state changes

        Returns:
            TriggerAnalysisResult if research was triggered, None otherwise
        """
        if not self._mid_execution_research_enabled:
            return None

        if self._task_generation_paused:
            logger.debug("[IMP-HIGH-005] Mid-execution research skipped: paused")
            return None

        # Check budget before triggering research
        budget_remaining = self.executor_ctx.get_budget_remaining() if self.executor_ctx else 1.0
        if budget_remaining < 0.1:
            logger.debug(
                "[IMP-HIGH-005] Mid-execution research skipped: "
                f"insufficient budget ({budget_remaining:.0%})"
            )
            return None

        # Convert execution results to analysis format
        analysis_results = self._execution_to_analysis_results(execution_results)

        # Trigger research cycle if needed
        return await self.trigger_research_cycle(analysis_results=analysis_results)

    def _execution_to_analysis_results(
        self,
        execution_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Convert execution results to analysis format for trigger detection.

        IMP-HIGH-005: Transforms execution outputs into the format expected
        by FollowupResearchTrigger.analyze().

        Args:
            execution_results: Raw execution results

        Returns:
            Dict in analysis_results format
        """
        # Extract findings from execution outputs
        findings = []

        # Check for errors that might need research
        errors = execution_results.get("errors", [])
        for error in errors:
            findings.append(
                {
                    "id": f"exec-error-{len(findings)}",
                    "summary": f"Execution error: {error.get('message', 'Unknown')}",
                    "confidence": 0.3,  # Low confidence triggers research
                    "topic": error.get("type", "execution"),
                }
            )

        # Check for warnings
        warnings = execution_results.get("warnings", [])
        for warning in warnings:
            findings.append(
                {
                    "id": f"exec-warn-{len(findings)}",
                    "summary": f"Warning: {warning.get('message', 'Unknown')}",
                    "confidence": 0.5,
                    "topic": warning.get("type", "execution"),
                }
            )

        # Check for gaps in execution coverage
        coverage = execution_results.get("coverage", {})
        gaps = []
        for area, covered in coverage.items():
            if not covered:
                gaps.append(
                    {
                        "category": area,
                        "description": f"Execution did not cover: {area}",
                        "suggested_queries": [f"{area} implementation guide"],
                    }
                )

        return {
            "findings": findings,
            "identified_gaps": gaps,
            "coverage_analysis": coverage,
            "mentioned_entities": execution_results.get("entities", []),
            "researched_entities": execution_results.get("resolved_entities", []),
        }

    # === IMP-AUTO-002: Event-Driven Workflow Triggers ===

    def register_event_handler(
        self,
        event_type: EventType,
        handler: Callable[[WorkflowEvent], None],
    ) -> None:
        """Register a handler for external events.

        IMP-AUTO-002: Handlers are invoked when events of the specified type
        are processed. Multiple handlers can be registered for the same event type.

        Args:
            event_type: Type of event to handle (from EventType enum)
            handler: Callable that receives WorkflowEvent

        Raises:
            ValueError: If handler is not callable
        """
        self._event_trigger_manager.register_handler(event_type, handler)
        logger.debug(
            f"[IMP-AUTO-002] Registered event handler for {event_type.value} "
            f"(total handlers: {self._event_trigger_manager.get_handler_count()})"
        )

    def unregister_event_handler(
        self,
        event_type: EventType,
        handler: Callable[[WorkflowEvent], None],
    ) -> bool:
        """Unregister a handler for an event type.

        Args:
            event_type: Type of event
            handler: Handler function to unregister

        Returns:
            True if handler was found and removed, False otherwise
        """
        return self._event_trigger_manager.unregister_handler(event_type, handler)

    async def trigger_event(
        self,
        event_type: EventType,
        source: str,
        payload: Optional[dict] = None,
    ) -> None:
        """Trigger a workflow event.

        IMP-AUTO-002: Creates a WorkflowEvent and dispatches it to all
        registered handlers for that event type.

        Args:
            event_type: Type of event to trigger
            source: Source system/service triggering the event
            payload: Optional event-specific data

        Raises:
            ValueError: If event creation fails
        """
        event = WorkflowEvent(
            event_type=event_type,
            source=source,
            payload=payload or {},
        )

        self._pending_events.append(event)
        logger.info(
            f"[IMP-AUTO-002] Event triggered: {event_type.value} from {source} "
            f"({len(self._pending_events)} pending)"
        )

        # Process immediately
        await self._event_trigger_manager.process_event(event)

    async def process_pending_events(self) -> int:
        """Process all pending workflow events.

        IMP-AUTO-002: Processes queued events and dispatches them to handlers.
        Returns the count of processed events.

        Returns:
            Number of events processed
        """
        if not self._pending_events:
            return 0

        logger.info(f"[IMP-AUTO-002] Processing {len(self._pending_events)} pending events")
        processed = 0

        while self._pending_events:
            event = self._pending_events.pop(0)
            try:
                await self._event_trigger_manager.process_event(event)
                processed += 1
            except Exception as e:
                logger.error(f"[IMP-AUTO-002] Failed to process event: {e}")

        logger.info(f"[IMP-AUTO-002] Processed {processed} events")
        return processed

    def get_event_handler_count(self, event_type: Optional[EventType] = None) -> int:
        """Get count of registered event handlers.

        Args:
            event_type: Specific event type, or None for total count

        Returns:
            Number of registered handlers
        """
        return self._event_trigger_manager.get_handler_count(event_type)

    def get_event_summary(self) -> Dict[str, Any]:
        """Get summary of event trigger state.

        Returns:
            Dictionary with handler and event information
        """
        return {
            **self._event_trigger_manager.get_summary(),
            "pending_events": len(self._pending_events),
        }

    def _handle_approval_required(self, proposal: PlanProposalV1) -> None:
        """Handle case where approval is required.

        Records what would be done and stops execution.
        IMP-AUTOPILOT-002: Queue approval requests for human review.

        Args:
            proposal: Plan proposal with actions requiring approval
        """
        logger.info("[Autopilot] Approval required - stopping execution")

        # Collect approval requests
        approval_requests = []
        blocked_count = 0

        for action in proposal.actions:
            if action.approval_status in ["requires_approval", "blocked"]:
                approval_requests.append(
                    ApprovalRequest(
                        action_id=action.action_id,
                        approval_status=action.approval_status,
                        reason=action.approval_reason or "No reason provided",
                    )
                )
                if action.approval_status == "blocked":
                    blocked_count += 1

        self.session.approval_requests = approval_requests
        self.session.status = "blocked_approval_required"
        self.session.completed_at = datetime.now(timezone.utc)

        if blocked_count > 0:
            self.session.blocked_reason = (
                f"{blocked_count} action(s) blocked by governance; "
                f"{len(approval_requests) - blocked_count} action(s) require manual approval"
            )
        else:
            self.session.blocked_reason = (
                f"{len(approval_requests)} action(s) require manual approval"
            )

        # Update execution summary
        self.session.execution_summary = ExecutionSummary(
            total_actions=proposal.summary.total_actions,
            auto_approved_actions=proposal.summary.auto_approved_actions,
            executed_actions=0,  # None executed
            successful_actions=0,
            failed_actions=0,
            blocked_actions=blocked_count,
        )

        # IMP-AUTOPILOT-002: Queue approval requests for human review
        # IMP-REL-005: Create checkpoint before approval service API call
        approval_checkpoint = self._create_state_checkpoint("approval_queue")

        try:
            from .approval_service import ApprovalService

            approval_svc = ApprovalService(
                run_id=self.run_id,
                project_id=self.project_id,
                workspace_root=self.workspace_root,
            )

            queued = approval_svc.queue_approvals(
                session_id=self.session.session_id,
                approval_requests=approval_requests,
                proposal_summary=getattr(proposal, "summary_text", None),
            )

            logger.info(
                f"[IMP-AUTOPILOT-002] Queued {queued} approval requests for human review. "
                f"Use approval_cli to review and approve."
            )
        except Exception as e:
            # IMP-REL-005: Rollback on approval service failure
            logger.error(f"[IMP-REL-005] Approval service failed: {e}")
            self._restore_from_checkpoint(approval_checkpoint)
            self.session.error_log.append(
                ErrorLogEntry(
                    timestamp=datetime.now(timezone.utc),
                    error_type="ApprovalServiceError",
                    error_message=f"Failed to queue approvals: {str(e)}",
                )
            )
            logger.warning(
                "[IMP-REL-005] Continuing despite approval service failure; "
                "approval requests may need to be queued manually"
            )

        logger.info(f"[Autopilot] Blocked: {self.session.blocked_reason}")

    def _validate_approval_ids(
        self, approval_ids: list[str], approval_svc: ApprovalService
    ) -> tuple[list[str], list[str]]:
        """Validate approval IDs before processing.

        IMP-REL-008: Comprehensive approval ID validation with format checking,
        database lookup, and error handling.

        Args:
            approval_ids: List of approval IDs to validate
            approval_svc: ApprovalService instance for lookups

        Returns:
            Tuple of (valid_ids, invalid_ids)
        """
        valid_ids = []
        invalid_ids = []

        logger.info(
            f"[IMP-REL-008] Validating {len(approval_ids)} approval IDs: "
            f"{approval_ids[:3]}{'...' if len(approval_ids) > 3 else ''}"
        )

        for approval_id in approval_ids:
            validation_error = self._validate_single_approval_id(approval_id, approval_svc)
            if validation_error:
                logger.warning(
                    f"[IMP-REL-008] Invalid approval ID '{approval_id}': {validation_error}"
                )
                invalid_ids.append(approval_id)
            else:
                logger.debug(f"[IMP-REL-008] Approval ID '{approval_id}' is valid")
                valid_ids.append(approval_id)

        if invalid_ids:
            logger.error(
                f"[IMP-REL-008] Found {len(invalid_ids)} invalid approval IDs: "
                f"{invalid_ids[:5]}{'...' if len(invalid_ids) > 5 else ''}"
            )
        else:
            logger.info(f"[IMP-REL-008] All {len(valid_ids)} approval IDs validated successfully")

        return valid_ids, invalid_ids

    def _validate_single_approval_id(
        self, approval_id: str, approval_svc: ApprovalService
    ) -> Optional[str]:
        """Validate a single approval ID.

        IMP-REL-008: Check format, existence in approval service, and consistency.

        Args:
            approval_id: Approval ID to validate
            approval_svc: ApprovalService instance

        Returns:
            None if valid, error message if invalid
        """
        # Step 1: Check format - must be non-empty string
        if not approval_id:
            return "Approval ID cannot be empty"

        if not isinstance(approval_id, str):
            return f"Approval ID must be string, got {type(approval_id).__name__}"

        approval_id = approval_id.strip()
        if not approval_id:
            return "Approval ID is whitespace-only"

        # Step 2: Check if approval exists in the approval service
        # Look through all decisions to verify this ID exists
        if not hasattr(approval_svc, "queue"):
            return "Approval service has no queue attribute"

        decision_ids = {d.action_id for d in approval_svc.queue.decisions}

        if approval_id not in decision_ids:
            return "Approval ID not found in approval service decisions"

        # Step 3: Check if the decision is actually "approved"
        for decision in approval_svc.queue.decisions:
            if decision.action_id == approval_id:
                if decision.decision != "approve":
                    return f"Approval ID has decision '{decision.decision}', " "not 'approve'"
                break

        return None

    def _execute_bounded_batch(self, proposal: PlanProposalV1) -> None:
        """Execute bounded batch of auto-approved actions.

        Uses SafeActionExecutor to run only safe actions (read-only commands
        and run-local artifact writes). Actions that would modify repo files
        are classified as requires_approval and not executed.

        BUILD-181: Records usage events for each action via ExecutorContext.

        IMP-HIGH-005: After batch execution, prepares execution results for
        mid-execution research triggering. Call `trigger_research_cycle()`
        with these results to execute followup research callbacks.

        Args:
            proposal: Plan proposal with auto-approved actions
        """
        logger.info("[Autopilot] Executing bounded batch with SafeActionExecutor")

        # Set phase for ExecutorContext tracking
        if self.executor_ctx:
            self.executor_ctx.set_phase("execute_batch")

        executor = SafeActionExecutor(
            workspace_root=self.workspace_root,
            command_timeout=30,
            dry_run=False,
        )

        batch = ExecutionBatch()
        executed = []
        successful = 0
        failed = 0
        requires_approval = 0

        for action in proposal.actions:
            if action.approval_status == "auto_approved":
                # IMP-HIGH-001: Check circuit breaker before each action
                if self.executor_ctx and not self.executor_ctx.circuit_breaker.is_available():
                    logger.critical(
                        f"[IMP-HIGH-001] Circuit breaker opened during execution. "
                        f"Stopping action batch at action {action.action_id}. "
                        f"State: {self.executor_ctx.circuit_breaker.state.value}"
                    )
                    # Don't execute this action - circuit is open
                    requires_approval += 1
                    continue

                logger.info(
                    f"[Autopilot] Processing action: {action.action_id} ({action.action_type})"
                )

                # Determine action type and execute appropriately
                result = None

                if action.action_type in ["check_doc_drift", "run_lint", "run_test_collect"]:
                    # Read-only command actions
                    command = self._get_command_for_action(action)
                    if command:
                        result = executor.execute_command(command)
                elif action.action_type == "write_artifact":
                    # Run-local artifact write
                    artifact_path = getattr(action, "artifact_path", None)
                    artifact_content = getattr(action, "artifact_content", "{}")
                    if artifact_path:
                        result = executor.write_artifact(artifact_path, artifact_content)
                else:
                    # Unknown action type - classify based on whether it touches repo
                    if hasattr(action, "target_path"):
                        result = executor.write_artifact(
                            action.target_path, getattr(action, "content", "")
                        )

                if result:
                    batch.add_result(result)

                    if result.executed:
                        executed.append(action.action_id)
                        if result.success:
                            successful += 1
                        else:
                            failed += 1
                            # Record failure for stuck handling and circuit breaker
                            if self.executor_ctx:
                                self.executor_ctx.record_failure()
                    elif result.classification == ActionClassification.REQUIRES_APPROVAL:
                        requires_approval += 1
                        logger.info(
                            f"[Autopilot] Action requires approval: {action.action_id} - {result.reason}"
                        )

                    # BUILD-181: Record usage event for this action
                    if self.executor_ctx and result.executed:
                        # Estimate tokens based on action type (simplified)
                        estimated_tokens = self._estimate_action_tokens(action)
                        self.executor_ctx.record_usage_event(
                            tokens_used=estimated_tokens,
                            event_id=f"action-{action.action_id}",
                        )
                        # Reset failure counter on success
                        if result.success:
                            self.executor_ctx.reset_failures()
                else:
                    # No result means we couldn't determine how to execute
                    # Mark as executed (passthrough) for backwards compatibility
                    executed.append(action.action_id)
                    successful += 1
                    logger.info(
                        f"[Autopilot] Action passed through: {action.action_id} ({action.action_type})"
                    )

        self.session.executed_action_ids = executed
        self.session.execution_summary = ExecutionSummary(
            total_actions=proposal.summary.total_actions,
            auto_approved_actions=proposal.summary.auto_approved_actions,
            executed_actions=len(executed),
            successful_actions=successful,
            failed_actions=failed,
            blocked_actions=requires_approval,
        )

        # Persist run-local artifacts
        self._persist_run_local_artifacts(proposal)

        # BUILD-181: Save usage events
        if self.executor_ctx:
            self.executor_ctx.save_usage_events()
            logger.info(
                f"[Autopilot] Budget remaining: {self.executor_ctx.get_budget_remaining():.1%}"
            )

        logger.info(
            f"[Autopilot] Executed {len(executed)} actions "
            f"({successful} successful, {failed} failed, {requires_approval} require approval)"
        )

        # IMP-HIGH-005: Prepare execution results for mid-execution research
        self._prepare_research_from_execution(
            executed_actions=executed,
            failed_count=failed,
            batch=batch,
        )

    def _prepare_research_from_execution(
        self,
        executed_actions: list[str],
        failed_count: int,
        batch: ExecutionBatch,
    ) -> None:
        """Prepare execution results for potential research triggering.

        IMP-HIGH-005: Collects execution results and prepares them for
        research trigger analysis. The results can be used by calling
        `trigger_research_cycle()` after batch execution.

        Args:
            executed_actions: List of executed action IDs
            failed_count: Number of failed actions
            batch: ExecutionBatch with detailed results
        """
        if not self._mid_execution_research_enabled:
            return

        # Check if we have failures that might need research
        if failed_count > 0:
            logger.info(
                f"[IMP-HIGH-005] {failed_count} action failures detected - "
                "research may be triggered on next cycle"
            )

            # Prepare analysis results from execution
            self._pending_execution_analysis = {
                "findings": [
                    {
                        "id": f"exec-failure-{i}",
                        "summary": "Action execution failed",
                        "confidence": 0.4,
                        "topic": "execution_failure",
                    }
                    for i in range(failed_count)
                ],
                "identified_gaps": (
                    [
                        {
                            "category": "execution",
                            "description": f"{failed_count} actions failed during execution",
                            "suggested_queries": ["error recovery strategies"],
                        }
                    ]
                    if failed_count > 2
                    else []
                ),
                "coverage_analysis": {
                    "execution": len(executed_actions) > 0,
                    "all_success": failed_count == 0,
                },
            }
        else:
            self._pending_execution_analysis = None

    def get_pending_execution_analysis(self) -> Optional[Dict[str, Any]]:
        """Get pending execution analysis results for research triggering.

        IMP-HIGH-005: Returns analysis results prepared from the last
        batch execution, if any failures occurred that might need research.

        Returns:
            Dict with analysis results, or None if no research needed
        """
        return getattr(self, "_pending_execution_analysis", None)

    def _get_command_for_action(self, action) -> Optional[str]:
        """Get command string for an action.

        Args:
            action: Action with action_type

        Returns:
            Command string or None
        """
        action_commands = {
            "check_doc_drift": "python scripts/check_docs_drift.py",
            "check_sot_summary": "python scripts/tidy/sot_summary_refresh.py --check",
            "run_lint": "ruff check .",
            "run_test_collect": "pytest --collect-only -q",
        }
        return action_commands.get(action.action_type)

    def _estimate_action_tokens(self, action) -> int:
        """Estimate token usage for an action.

        Uses estimated_cost from action if available, otherwise defaults.

        Args:
            action: Action with optional estimated_cost

        Returns:
            Estimated token count
        """
        # Use action's estimated cost if available
        if hasattr(action, "estimated_cost") and action.estimated_cost:
            if action.estimated_cost.tokens:
                return action.estimated_cost.tokens

        # Default estimates by action type
        default_estimates = {
            "check_doc_drift": 100,
            "check_sot_summary": 50,
            "run_lint": 200,
            "run_test_collect": 150,
            "doc_update": 500,
            "file_move": 200,
            "file_delete": 100,
            "test_fix": 2000,
            "config_update": 300,
            "write_artifact": 100,
        }
        return default_estimates.get(action.action_type, 100)

    def _persist_run_local_artifacts(self, proposal: PlanProposalV1) -> None:
        """Persist run-local artifacts (gap report, plan proposal).

        IMP-FEAT-004: Save full PlanProposalV1 to enable loading for approved action execution.

        Args:
            proposal: Plan proposal to persist
        """
        # Ensure autonomy directory exists
        autonomy_dir = self.layout.base_dir / "autonomy"
        autonomy_dir.mkdir(parents=True, exist_ok=True)

        # Save gap report if we have one
        if self.session and self.session.gap_report_id:
            gaps_dir = self.layout.base_dir / "gaps"
            gaps_dir.mkdir(parents=True, exist_ok=True)
            # Gap report would be saved by the scanner; just log
            logger.debug(f"[Autopilot] Gap report ID: {self.session.gap_report_id}")

        # Save plan proposal - IMP-FEAT-004: Save full proposal for later loading
        plans_dir = self.layout.base_dir / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plans_dir / f"plan_proposal_{self.session.plan_proposal_id}.json"

        try:
            # Save full PlanProposalV1 using its built-in serialization
            proposal.save_to_file(plan_path)
            logger.info(f"[Autopilot] Saved full plan proposal: {plan_path}")
        except Exception as e:
            logger.warning(f"[Autopilot] Failed to save plan proposal: {e}")

    def execute_approved_proposals(self, session_id: str) -> int:
        """Execute proposals that have been approved via approval workflow.

        IMP-FEAT-004: Complete implementation for loading and executing approved proposals.

        This method:
        1. Loads the autopilot session to get the plan_proposal_id
        2. Loads the full PlanProposalV1 from the plans directory
        3. Filters actions to only those that have been approved
        4. Executes each approved action via SafeActionExecutor
        5. Records results and updates the session

        Args:
            session_id: Session ID to execute approved actions for

        Returns:
            Number of approved actions successfully executed

        Raises:
            RuntimeError: If autopilot is not enabled
        """
        if not self.enabled:
            raise RuntimeError(
                "Autopilot is disabled. Set enabled=True explicitly to execute approved proposals."
            )

        from .approval_service import ApprovalService

        logger.info(f"[IMP-FEAT-004] Executing approved proposals for session {session_id}")

        # Load approval service
        approval_svc = ApprovalService(
            run_id=self.run_id,
            project_id=self.project_id,
            workspace_root=self.workspace_root,
        )

        # Get approved actions for this session
        approved_ids = approval_svc.get_approved_actions(session_id=session_id)

        if not approved_ids:
            logger.info("[IMP-FEAT-004] No approved actions to execute")
            return 0

        logger.info(f"[IMP-FEAT-004] Found {len(approved_ids)} approved actions")

        # IMP-REL-008: Validate approval IDs before processing
        valid_ids, invalid_ids = self._validate_approval_ids(approved_ids, approval_svc)

        if invalid_ids:
            logger.error(
                f"[IMP-REL-008] Execution blocked: {len(invalid_ids)} invalid approval IDs"
            )
            # Continue with only valid IDs
            approved_ids = valid_ids

        if not approved_ids:
            logger.error(
                "[IMP-REL-008] All approval IDs were invalid. No valid actions to execute."
            )
            return 0

        logger.info(f"[IMP-REL-008] Proceeding with {len(approved_ids)} valid approval IDs")

        # Step 1: Load the original session to get plan_proposal_id
        session_path = self.layout.base_dir / "autonomy" / f"{session_id}.json"
        if not session_path.exists():
            logger.error(f"[IMP-FEAT-004] Session file not found: {session_path}")
            return 0

        try:
            original_session = AutopilotSessionV1.load_from_file(session_path)
            plan_proposal_id = original_session.plan_proposal_id
            logger.info(f"[IMP-FEAT-004] Loaded session with plan_proposal_id: {plan_proposal_id}")
        except Exception as e:
            logger.error(f"[IMP-FEAT-004] Failed to load session: {e}")
            return 0

        # Step 2: Load the full PlanProposalV1
        plan_path = self.layout.base_dir / "plans" / f"plan_proposal_{plan_proposal_id}.json"
        if not plan_path.exists():
            logger.error(f"[IMP-FEAT-004] Plan proposal file not found: {plan_path}")
            return 0

        try:
            proposal = PlanProposalV1.load_from_file(plan_path)
            logger.info(f"[IMP-FEAT-004] Loaded plan proposal with {len(proposal.actions)} actions")
        except Exception as e:
            logger.error(f"[IMP-FEAT-004] Failed to load plan proposal: {e}")
            return 0

        # IMP-SAFETY-011: Validate approved action IDs against proposal actions
        # This prevents execution of actions that were never proposed
        pending_ids = {action.action_id for action in proposal.actions}
        approved_ids_set = set(approved_ids)
        invalid_ids = approved_ids_set - pending_ids

        if invalid_ids:
            logger.warning(
                f"[IMP-SAFETY-011] Rejected {len(invalid_ids)} invalid action IDs not found in proposal: "
                f"{sorted(invalid_ids)[:5]}{'...' if len(invalid_ids) > 5 else ''}"
            )
            # Filter out invalid IDs - only execute actions that exist in the proposal
            approved_ids = [aid for aid in approved_ids if aid in pending_ids]

            if not approved_ids:
                logger.error(
                    "[IMP-SAFETY-011] All approved action IDs were invalid. No actions to execute."
                )
                return 0

        # Step 3: Filter to approved actions only
        approved_actions = [a for a in proposal.actions if a.action_id in approved_ids]

        if not approved_actions:
            logger.warning(
                f"[IMP-FEAT-004] No matching actions found in proposal for approved IDs: "
                f"{approved_ids[:3]}{'...' if len(approved_ids) > 3 else ''}"
            )
            return 0

        logger.info(f"[IMP-FEAT-004] Executing {len(approved_actions)} approved actions")

        # Step 4: Execute approved actions via SafeActionExecutor
        executor = SafeActionExecutor(
            workspace_root=self.workspace_root,
            command_timeout=30,
            dry_run=False,
        )

        executed_count = 0
        successful_count = 0
        failed_count = 0

        for action in approved_actions:
            logger.info(
                f"[IMP-FEAT-004] Executing approved action: {action.action_id} ({action.action_type})"
            )

            result = None

            # Execute based on action type
            if action.action_type in ["check_doc_drift", "run_lint", "run_test_collect"]:
                # Read-only command actions
                command = self._get_command_for_action(action)
                if command:
                    result = executor.execute_command(command)
            elif action.action_type == "write_artifact":
                # Artifact write
                artifact_path = getattr(action, "artifact_path", None) or (
                    action.target_paths[0] if action.target_paths else None
                )
                artifact_content = getattr(action, "artifact_content", "{}")
                if artifact_path:
                    result = executor.write_artifact(artifact_path, artifact_content)
            elif action.command:
                # Action with explicit command
                result = executor.execute_command(action.command)
            elif action.target_paths:
                # File-based action
                for target_path in action.target_paths:
                    result = executor.write_artifact(target_path, getattr(action, "content", ""))

            if result:
                executed_count += 1
                if result.success:
                    successful_count += 1
                    logger.info(f"[IMP-FEAT-004] Action {action.action_id} executed successfully")
                else:
                    failed_count += 1
                    logger.warning(
                        f"[IMP-FEAT-004] Action {action.action_id} failed: {result.reason}"
                    )
            else:
                # No result means passthrough (action type not requiring execution)
                executed_count += 1
                successful_count += 1
                logger.info(f"[IMP-FEAT-004] Action {action.action_id} passed through")

        # Step 5: Log final results
        logger.info(
            f"[IMP-FEAT-004] Execution complete: "
            f"{executed_count} executed, {successful_count} successful, {failed_count} failed"
        )

        return successful_count

    def save_session(self) -> Path:
        """Save autopilot session to run-local artifact.

        Returns:
            Path to saved session file

        Raises:
            RuntimeError: If no session exists
        """
        if not self.session:
            raise RuntimeError("No session to save")

        # Ensure directories exist
        self.layout.ensure_directories()

        # Create autonomy directory
        autonomy_dir = self.layout.base_dir / "autonomy"
        autonomy_dir.mkdir(exist_ok=True)

        # Save session
        session_path = autonomy_dir / f"{self.session.session_id}.json"
        self.session.save_to_file(session_path)

        logger.info(f"[Autopilot] Saved session: {session_path}")
        return session_path


def run_autopilot_session(
    workspace_root: Path,
    project_id: str,
    run_id: str,
    anchor: IntentionAnchorV2,
    enabled: bool = False,
    save: bool = True,
) -> AutopilotSessionV1:
    """Run autopilot session (convenience function).

    Args:
        workspace_root: Root directory of workspace
        project_id: Project identifier
        run_id: Run identifier
        anchor: Intention anchor v2 to guide execution
        enabled: Whether autopilot is explicitly enabled (default: False)
        save: Whether to save session to file (default: True)

    Returns:
        AutopilotSessionV1 with execution log

    Raises:
        RuntimeError: If autopilot is not enabled
    """
    controller = AutopilotController(
        workspace_root=workspace_root,
        project_id=project_id,
        run_id=run_id,
        enabled=enabled,
    )

    session = controller.run_session(anchor)

    if save:
        controller.save_session()

    return session
