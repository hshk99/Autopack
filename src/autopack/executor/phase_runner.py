"""
Phase Runner Module

Extracted from autonomous_executor.py to manage phase execution orchestration.
This module addresses complexity by separating phase execution flow into
testable, modular components.

Key responsibilities:
- Phase initialization and setup
- Attempt execution coordination
- Success/failure routing
- Recovery strategy selection
- State updates and telemetry
- Validator gate wiring (IMP-RES-005: Wire validators as pipeline gates)

Related modules:
- doctor_integration.py: Doctor invocation and budget tracking
- replan_trigger.py: Approach flaw detection and replanning
- intention_stuck_handler.py: Intention-first stuck handling (BUILD-161)
- validator_gate.py: Validator gate infrastructure and pipeline
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from autopack.executor.validator_gate import ValidatorGatePipeline, create_default_validator_gate_pipeline

logger = logging.getLogger(__name__)


class PhaseResult(Enum):
    """Outcome of phase execution"""

    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    REPLAN_REQUESTED = "REPLAN_REQUESTED"
    BLOCKED = "BLOCKED"


@dataclass
class ExecutionResult:
    """Result of phase execution attempt"""

    success: bool
    phase_result: str
    error_message: Optional[str] = None
    builder_result: Optional[Any] = None
    auditor_result: Optional[Any] = None
    ci_result: Optional[Dict] = None


class PhaseRunner:
    """
    Manages phase execution with error recovery and retry logic.

    Coordinates the execution of individual phases including:
    - Builder invocation
    - Auditor review
    - CI checks
    - Quality gate validation
    """

    def __init__(
        self,
        llm_service: Any,
        builder_orchestrator: Any,
        auditor_orchestrator: Any,
        quality_gate: Any,
        patch_flow: Any,
        ci_flow: Any,
        phase_state_mgr: Any,
        manifest_generator: Optional[Any] = None,
        time_watchdog: Any = None,  # IMP-SAFETY-004: Required but typed as Any for flexibility
        validator_gate_pipeline: Optional[ValidatorGatePipeline] = None,  # IMP-RES-005: Validator gates
    ):
        """Initialize PhaseRunner with dependencies.

        Args:
            llm_service: LLM service for model routing
            builder_orchestrator: Builder orchestration module
            auditor_orchestrator: Auditor orchestration module
            quality_gate: Quality gate for risk assessment
            patch_flow: Patch application flow
            ci_flow: CI execution flow
            phase_state_mgr: Phase state manager for DB updates
            manifest_generator: Optional manifest generator
            time_watchdog: TimeWatchdog instance for timeout enforcement (IMP-SAFETY-004: mandatory)
            validator_gate_pipeline: Optional validator gate pipeline (IMP-RES-005: wired validators)
        """
        # IMP-SAFETY-004: Validate time_watchdog is provided
        if time_watchdog is None:
            raise ValueError(
                "time_watchdog is required per IMP-SAFETY-004. "
                "Phases cannot run indefinitely. Use create_default_time_watchdog() "
                "from autopack.executor.phase_orchestrator to create with config defaults."
            )
        self.llm_service = llm_service
        self.builder_orchestrator = builder_orchestrator
        self.auditor_orchestrator = auditor_orchestrator
        self.quality_gate = quality_gate
        self.patch_flow = patch_flow
        self.ci_flow = ci_flow
        self.phase_state_mgr = phase_state_mgr
        self.manifest_generator = manifest_generator
        self.time_watchdog = time_watchdog
        # IMP-RES-005: Wire validator gate pipeline
        self.validator_gate_pipeline = validator_gate_pipeline or create_default_validator_gate_pipeline()

    def execute_phase(
        self,
        phase: Dict,
        attempt_index: int,
        max_attempts: int,
        escalation_level: int,
        allowed_paths: List[str],
        run_id: str,
        project_rules: List,
        run_hints: List,
        db: Any,
        get_phase_from_db: Callable,
        update_phase_status: Callable,
        record_phase_attempt: Callable,
        root: Path,
    ) -> ExecutionResult:
        """Execute a single phase with full validation pipeline.

        Args:
            phase: Phase specification dict
            attempt_index: Current attempt number
            max_attempts: Maximum retry attempts
            escalation_level: Current model escalation level
            allowed_paths: Governance allowed paths
            run_id: Run identifier
            project_rules: Learning context project rules
            run_hints: Learning context run hints
            db: Database session
            get_phase_from_db: Callable to get phase from DB
            update_phase_status: Callable to update phase status in DB
            record_phase_attempt: Callable to record phase attempt
            root: Repository root path

        Returns:
            ExecutionResult with outcome and details
        """
        phase_id = phase.get("phase_id", "unknown")

        logger.info(
            f"[{phase_id}] Starting phase execution (attempt {attempt_index}/{max_attempts})"
        )

        # IMP-RES-005: Phase 0 - Execute validator gates
        # Validate phase context before proceeding to builder
        validator_context = {
            "phase": phase,
            "phase_id": phase_id,
            "attempt_index": attempt_index,
            "escalation_level": escalation_level,
            "allowed_paths": allowed_paths,
        }
        gate_result = self.validator_gate_pipeline.execute(validator_context)

        if not gate_result.can_proceed:
            logger.error(
                f"[{phase_id}] Validator gates blocked execution: {gate_result.get_summary()}"
            )
            for error_msg in gate_result.get_blocking_failure_messages():
                logger.error(f"[{phase_id}] {error_msg}")
            return ExecutionResult(
                success=False,
                phase_result="BLOCKED",
                error_message=f"Validator gates blocked execution: {gate_result.get_summary()}",
            )

        logger.info(f"[{phase_id}] {gate_result.get_summary()}")

        # Phase 1: Execute Builder
        builder_result, build_error = self._execute_builder(
            phase, attempt_index, escalation_level, allowed_paths
        )

        if not builder_result:
            return ExecutionResult(
                success=False,
                phase_result="FAILED",
                error_message=build_error,
            )

        # Phase 2: Apply Patch
        patch_success, patch_error, apply_stats = self._apply_patch(
            phase, builder_result, allowed_paths
        )

        if not patch_success:
            return ExecutionResult(
                success=False,
                phase_result="PATCH_FAILED",
                error_message=patch_error,
                builder_result=builder_result,
            )

        # Phase 3: Execute CI
        ci_result = self._execute_ci(phase)

        # Phase 4: Execute Auditor
        auditor_result = self._execute_auditor(
            phase,
            builder_result,
            ci_result,
            project_rules,
            run_hints,
            attempt_index,
        )

        # Phase 5: Quality Gate
        quality_report = self._assess_quality(
            phase,
            auditor_result,
            ci_result,
            builder_result,
        )

        # Determine final outcome
        phase_result = self._determine_outcome(auditor_result, ci_result, quality_report, phase_id)

        logger.info(f"[{phase_id}] Phase execution completed with result: {phase_result}")

        return ExecutionResult(
            success=phase_result == PhaseResult.COMPLETE.value,
            phase_result=phase_result,
            builder_result=builder_result,
            auditor_result=auditor_result,
            ci_result=ci_result,
        )

    def _execute_builder(
        self,
        phase: Dict,
        attempt_index: int,
        escalation_level: int,
        allowed_paths: List[str],
    ) -> Tuple[Optional[Any], Optional[str]]:
        """Execute builder with orchestration.

        Delegates to builder_orchestrator.
        """
        phase_id = phase.get("phase_id", "unknown")
        return self.builder_orchestrator.execute_builder_with_validation(
            phase_id=phase_id,
            phase=phase,
            attempt_index=attempt_index,
            escalation_level=escalation_level,
            allowed_paths=allowed_paths,
        )

    def _apply_patch(
        self,
        phase: Dict,
        builder_result: Any,
        allowed_paths: List[str],
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Apply patch with validation.

        Delegates to patch_flow.
        """
        phase_id = phase.get("phase_id", "unknown")
        return self.patch_flow.apply_patch_with_validation(
            phase_id=phase_id,
            phase=phase,
            builder_result=builder_result,
            file_context={},  # Would need proper context from caller
            allowed_paths=allowed_paths,
        )

    def _execute_ci(self, phase: Dict) -> Optional[Dict]:
        """Execute CI checks.

        Delegates to ci_flow.
        """
        phase_id = phase.get("phase_id", "unknown")
        return self.ci_flow.execute_ci_checks(phase_id, phase)

    def _execute_auditor(
        self,
        phase: Dict,
        builder_result: Any,
        ci_result: Optional[Dict],
        project_rules: List,
        run_hints: List,
        attempt_index: int,
    ) -> Any:
        """Execute auditor review.

        Delegates to auditor_orchestrator.
        """
        phase_id = phase.get("phase_id", "unknown")
        return self.auditor_orchestrator.execute_auditor_review(
            phase_id=phase_id,
            phase=phase,
            builder_result=builder_result,
            ci_result=ci_result,
            project_rules=project_rules,
            run_hints=run_hints,
            attempt_index=attempt_index,
        )

    def _assess_quality(
        self,
        phase: Dict,
        auditor_result: Any,
        ci_result: Optional[Dict],
        builder_result: Any,
    ) -> Any:
        """Assess phase quality with quality gate.

        Delegates to quality_gate.
        """
        phase_id = phase.get("phase_id", "unknown")
        return self.quality_gate.assess_phase(
            phase_id=phase_id,
            phase_spec=phase,
            auditor_result={
                "approved": auditor_result.approved if auditor_result else False,
                "issues_found": auditor_result.issues_found if auditor_result else 0,
            },
            ci_result=ci_result,
            coverage_delta=self._compute_coverage_delta(ci_result),
            patch_content=builder_result.patch_content if builder_result else "",
            files_changed=builder_result.files_changed if builder_result else [],
        )

    def _compute_coverage_delta(self, ci_result: Optional[Dict]) -> float:
        """Compute coverage delta from CI result.

        Args:
            ci_result: CI execution result dict

        Returns:
            Coverage delta as float
        """
        if not ci_result:
            return 0.0

        coverage_before = ci_result.get("coverage_before", 0.0)
        coverage_after = ci_result.get("coverage_after", 0.0)
        return coverage_after - coverage_before

    def _determine_outcome(
        self,
        auditor_result: Any,
        ci_result: Optional[Dict],
        quality_report: Any,
        phase_id: str,
    ) -> str:
        """Determine final phase outcome based on all checks.

        Args:
            auditor_result: Auditor review result
            ci_result: CI execution result
            quality_report: Quality gate report
            phase_id: Phase identifier

        Returns:
            Phase outcome as string
        """
        # Check if any component failed
        if ci_result and not ci_result.get("success", True):
            return "CI_FAILED"

        if auditor_result and not auditor_result.approved:
            return "BLOCKED"

        if quality_report and quality_report.quality_level == "BLOCK":
            return "BLOCKED"

        # All checks passed
        return PhaseResult.COMPLETE.value
