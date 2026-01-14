"""
Phase Execution Orchestrator

Extracted from autonomous_executor.py to manage phase execution flow with error recovery.
This module addresses the core complexity issue by separating the 800-line execute_phase()
method into modular, testable components.

Key responsibilities:
- Phase initialization and setup
- Attempt execution coordination
- Success/failure routing
- Recovery strategy selection
- State updates and telemetry
- Parallel execution of independent operations (IMP-P06)

Related modules:
- doctor_integration.py: Doctor invocation and budget tracking
- replan_trigger.py: Approach flaw detection and replanning
- intention_stuck_handler.py: Intention-first stuck handling (BUILD-161)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Any, List, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class PhaseResult(Enum):
    """Outcome of phase execution"""

    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    REPLAN_REQUESTED = "REPLAN_REQUESTED"
    BLOCKED = "BLOCKED"


@dataclass
class ExecutionContext:
    """All context needed for phase execution"""

    # Core phase data
    phase: Dict
    attempt_index: int
    max_attempts: int
    escalation_level: int
    allowed_paths: List[str]
    run_id: str

    # Dependencies passed by executor
    llm_service: Any
    diagnostics_agent: Optional[Any] = None
    iterative_investigator: Optional[Any] = None
    intention_wiring: Optional[Any] = None
    intention_anchor: Optional[Any] = None
    manifest_generator: Optional[Any] = None

    # State counters
    run_total_failures: int = 0
    run_http_500_count: int = 0
    run_patch_failure_count: int = 0
    run_doctor_calls: int = 0
    run_replan_count: int = 0
    run_tokens_used: int = 0
    run_context_chars_used: int = 0
    run_sot_chars_used: int = 0

    # Executor methods (passed as callables)
    get_phase_from_db: Optional[Any] = None
    mark_phase_complete_in_db: Optional[Any] = None
    mark_phase_failed_in_db: Optional[Any] = None
    update_phase_attempts_in_db: Optional[Any] = None
    record_learning_hint: Optional[Any] = None
    record_phase_error: Optional[Any] = None
    run_diagnostics_for_failure: Optional[Any] = None
    record_token_efficiency_telemetry: Optional[Any] = None
    status_to_outcome: Optional[Any] = None
    refresh_project_rules_if_updated: Optional[Any] = None

    # Additional state
    phase_error_history: Dict[str, List[Dict]] = field(default_factory=dict)
    last_builder_result: Optional[Any] = None
    workspace_root: Optional[str] = None
    run_budget_tokens: int = 0


@dataclass
class ExecutionResult:
    """Result of phase execution attempt"""

    success: bool
    status: str
    phase_result: PhaseResult
    updated_counters: Dict[str, int]  # Updated state counters
    should_continue: bool = True


class PhaseOrchestrator:
    """
    Orchestrates phase execution flow with error recovery.

    This class replaces the 800-line execute_phase() method by separating concerns:
    - Initialization and setup
    - Attempt execution
    - Success/failure routing
    - Recovery strategy selection
    - State updates
    """

    def __init__(self, max_retry_attempts: int = 5):
        self.max_retry_attempts = max_retry_attempts

    def execute_phase_attempt(self, context: ExecutionContext) -> ExecutionResult:
        """
        Execute a single phase attempt with full error recovery.

        This is the main entry point that replaces the 800-line execute_phase() method.

        Args:
            context: Complete execution context with dependencies

        Returns:
            ExecutionResult with status and updated counters
        """
        context.phase.get("phase_id")

        # Initialize goal anchoring and tracking
        self._initialize_phase(context)

        # Setup scope manifest if missing (BUILD-123v2)
        self._setup_phase_scope(context)

        # Check if already exhausted attempts
        if context.attempt_index >= self.max_retry_attempts:
            return self._create_exhausted_result(context)

        # Refresh project rules mid-run if needed
        if context.refresh_project_rules_if_updated:
            context.refresh_project_rules_if_updated()

        # Execute single attempt
        try:
            result = self._execute_single_attempt(context)

            if result.success:
                return self._handle_success(context, result)
            else:
                return self._handle_failure(context, result)

        except Exception as e:
            return self._handle_exception(context, e)

    def _initialize_phase(self, context: ExecutionContext):
        """
        Initialize goal anchoring and tracking for the phase.

        Tracks phase state for intention-first loop (BUILD-161 Phase A).
        """
        phase_id = context.phase.get("phase_id")

        # INSERTION POINT 2: Track phase state for intention-first loop (BUILD-161 Phase A)
        if context.intention_wiring is not None:
            from autopack.autonomous.executor_wiring import get_or_create_phase_state

            phase_state = get_or_create_phase_state(context.intention_wiring, phase_id)
            # Increment iterations_used at phase start
            phase_state.iterations_used += 1
            logger.debug(
                f"[IntentionFirst] Phase {phase_id}: iteration {phase_state.iterations_used}"
            )

    def _setup_phase_scope(self, context: ExecutionContext):
        """
        Set up scope manifest if missing or incomplete (BUILD-123v2).

        Generates scope manifest for phases that don't have explicit scope paths.
        """
        phase_id = context.phase.get("phase_id")
        scope_config = context.phase.get("scope") or {}

        if not scope_config.get("paths") and context.manifest_generator:
            logger.info(f"[BUILD-123v2] Phase '{phase_id}' has no scope - generating manifest...")
            try:
                # Create minimal plan for this phase
                minimal_plan = {"run_id": context.run_id, "phases": [context.phase]}

                # Generate manifest
                result = context.manifest_generator.generate_manifest(
                    plan_data=minimal_plan,
                    skip_validation=False,  # Run preflight validation
                )

                if result.success and result.enhanced_plan["phases"]:
                    enhanced_phase = result.enhanced_plan["phases"][0]
                    scope_config = enhanced_phase.get("scope", {})

                    # Update phase with generated scope
                    context.phase["scope"] = scope_config

                    # Log confidence
                    confidence = result.confidence_scores.get(phase_id, 0.0)
                    category = enhanced_phase.get("metadata", {}).get("category", "unknown")
                    logger.info(
                        f"[BUILD-123v2] Generated scope for '{phase_id}': "
                        f"category={category}, confidence={confidence:.1%}, "
                        f"files={len(scope_config.get('paths', []))}"
                    )

                    # Warn if low confidence
                    if confidence < 0.30:
                        logger.warning(
                            f"[BUILD-123v2] Low confidence ({confidence:.1%}) for phase '{phase_id}' - "
                            f"scope may be incomplete. Builder may need to request expansion."
                        )
                else:
                    logger.warning(
                        f"[BUILD-123v2] Manifest generation failed for '{phase_id}': {result.error}"
                    )
                    # Continue with empty scope - Builder will handle
            except Exception as e:
                logger.error(f"[BUILD-123v2] Failed to generate manifest for '{phase_id}': {e}")
                import traceback

                traceback.print_exc()
                # Continue with empty scope

    def _create_exhausted_result(self, context: ExecutionContext) -> ExecutionResult:
        """Create result when max attempts are exhausted."""
        phase_id = context.phase.get("phase_id")
        logger.warning(
            f"[{phase_id}] Phase has already exhausted all attempts "
            f"({context.attempt_index}/{self.max_retry_attempts}). Marking as FAILED."
        )

        if context.mark_phase_failed_in_db:
            context.mark_phase_failed_in_db(phase_id, "MAX_ATTEMPTS_EXHAUSTED")

        return ExecutionResult(
            success=False,
            status="FAILED",
            phase_result=PhaseResult.FAILED,
            updated_counters={
                "total_failures": context.run_total_failures,
                "http_500_count": context.run_http_500_count,
                "patch_failure_count": context.run_patch_failure_count,
                "doctor_calls": context.run_doctor_calls,
                "replan_count": context.run_replan_count,
            },
            should_continue=False,
        )

    def _execute_single_attempt(self, context: ExecutionContext):
        """
        Execute single attempt with recovery.

        Delegates to attempt_runner module for the execution wrapper.
        """
        from autopack.executor.attempt_runner import run_single_attempt_with_recovery
        from autopack.executor.db_events import maybe_apply_retry_max_tokens_from_db
        from autopack.executor.retry_policy import AttemptContext

        # PR-B: Build attempt context for retry policy decisions
        AttemptContext(
            attempt_index=context.attempt_index,
            max_attempts=context.max_attempts,
            escalation_level=context.escalation_level,
        )

        # BUILD-129 Phase 3 P10: Apply persisted escalate-once budget on the *next* attempt.
        maybe_apply_retry_max_tokens_from_db(
            run_id=context.run_id,
            phase=context.phase,
            attempt_index=context.attempt_index,
        )

        # Execute the attempt (this is a mock executor - would need real one)
        class MockExecutor:
            """Mock executor to pass to attempt_runner."""

            def __init__(self, context):
                self.context = context
                self.run_id = context.run_id
                self.llm_service = context.llm_service

        mock_executor = MockExecutor(context)

        result = run_single_attempt_with_recovery(
            executor=mock_executor,
            phase=context.phase,
            attempt_index=context.attempt_index,
            allowed_paths=context.allowed_paths,
        )

        return result

    def _handle_success(self, context: ExecutionContext, result) -> ExecutionResult:
        """
        Handle successful phase completion.

        Records telemetry and learning hints.
        """
        phase_id = context.phase.get("phase_id")

        # [BUILD-041] Mark phase COMPLETE in database
        if context.mark_phase_complete_in_db:
            context.mark_phase_complete_in_db(phase_id)

        # Learning Pipeline: Record hint if succeeded after retries
        if context.attempt_index > 0 and context.record_learning_hint:
            context.record_learning_hint(
                phase=context.phase,
                hint_type="success_after_retry",
                details=f"Succeeded on attempt {context.attempt_index + 1} after {context.attempt_index} failed attempts",
            )

        # BUILD-145 P1.1: Record token efficiency telemetry
        if context.record_token_efficiency_telemetry:
            context.record_token_efficiency_telemetry(phase_id, "COMPLETE")

        logger.info(
            f"[{phase_id}] Phase completed successfully on attempt {context.attempt_index + 1}"
        )

        return ExecutionResult(
            success=True,
            status="COMPLETE",
            phase_result=PhaseResult.COMPLETE,
            updated_counters={
                "total_failures": context.run_total_failures,
                "http_500_count": context.run_http_500_count,
                "patch_failure_count": context.run_patch_failure_count,
                "doctor_calls": context.run_doctor_calls,
                "replan_count": context.run_replan_count,
            },
            should_continue=True,
        )

    def _handle_failure(self, context: ExecutionContext, result) -> ExecutionResult:
        """
        Handle phase failure with recovery strategy.

        This is the big one - coordinates:
        - Diagnostics
        - Doctor invocation
        - Failure hardening
        - Intention-first stuck handling
        - Replan triggers
        - Attempt increment and retry
        """
        from autopack.executor.retry_policy import next_attempt_state, AttemptContext

        phase_id = context.phase.get("phase_id")
        status = result.status

        # [BUILD-041] Attempt failed - update database and check if exhausted
        if context.status_to_outcome:
            failure_outcome = context.status_to_outcome(status)
        else:
            failure_outcome = "auditor_reject"

        # PR-B: Use retry_policy to compute next state decision
        attempt_ctx = AttemptContext(
            attempt_index=context.attempt_index,
            max_attempts=context.max_attempts,
            escalation_level=context.escalation_level,
        )
        decision = next_attempt_state(attempt_ctx, status)

        # BUILD-129/P10 convergence: TOKEN_ESCALATION is not a diagnosable "approach flaw".
        if not decision.should_run_diagnostics and decision.next_retry_attempt is not None:
            # TOKEN_ESCALATION or similar: advance retry_attempt without diagnostics
            if context.update_phase_attempts_in_db:
                context.update_phase_attempts_in_db(
                    phase_id,
                    retry_attempt=decision.next_retry_attempt,
                    last_failure_reason=status,
                )
            logger.info(
                f"[{phase_id}] {status} recorded; advancing retry_attempt to {decision.next_retry_attempt} "
                f"and deferring diagnosis so the next attempt can use the escalated max_tokens."
            )
            return ExecutionResult(
                success=False,
                status=status,
                phase_result=PhaseResult.FAILED,
                updated_counters={
                    "total_failures": context.run_total_failures,
                    "http_500_count": context.run_http_500_count,
                    "patch_failure_count": context.run_patch_failure_count,
                    "doctor_calls": context.run_doctor_calls,
                    "replan_count": context.run_replan_count,
                },
                should_continue=True,
            )

        # Update health budget tracking
        context.run_total_failures += 1
        if status == "PATCH_FAILED":
            context.run_patch_failure_count += 1

        # Learning Pipeline: Record hint about what went wrong
        if context.record_learning_hint:
            context.record_learning_hint(
                phase=context.phase,
                hint_type=failure_outcome,
                details=f"Failed with {status} on attempt {context.attempt_index + 1}",
            )

        # Mid-Run Re-Planning: Record error for approach flaw detection
        if context.record_phase_error:
            context.record_phase_error(
                phase=context.phase,
                error_type=failure_outcome,
                error_details=f"Status: {status}",
                attempt_index=context.attempt_index,
            )

        # [BUILD-146 P6.3] Deterministic Failure Hardening (before expensive diagnostics/Doctor)
        hardening_result = self._try_failure_hardening(context, status, phase_id)
        if hardening_result:
            return hardening_result

        # Run governed diagnostics to gather evidence before mutations
        if context.run_diagnostics_for_failure:
            context.run_diagnostics_for_failure(
                failure_class=failure_outcome,
                phase=context.phase,
                context={
                    "status": status,
                    "attempt_index": context.attempt_index,
                    "logs_excerpt": f"Status: {status}, Attempt: {context.attempt_index + 1}",
                },
            )

        # [Doctor Integration] Invoke Doctor for diagnosis after sufficient failures
        from autopack.executor.doctor_integration import DoctorIntegration

        doctor_integration = DoctorIntegration()

        # Extract patch and error info from last builder result
        last_patch = None
        patch_errors = []
        if context.last_builder_result:
            last_patch = context.last_builder_result.patch_content
            if context.last_builder_result.error:
                patch_errors = [{"error": context.last_builder_result.error}]
            if context.last_builder_result.builder_messages:
                for msg in context.last_builder_result.builder_messages:
                    if msg and ("error" in msg.lower() or "failed" in msg.lower()):
                        patch_errors.append({"message": msg})

        doctor_response = doctor_integration.invoke_doctor(
            phase=context.phase,
            error_category=failure_outcome,
            builder_attempts=context.attempt_index + 1,
            last_patch=last_patch,
            patch_errors=patch_errors,
            logs_excerpt=f"Status: {status}, Attempt: {context.attempt_index + 1}",
            llm_service=context.llm_service,
            run_id=context.run_id,
            # These would need to be passed or retrieved
            doctor_calls_by_phase={},
            run_doctor_calls=context.run_doctor_calls,
            intention_injector=getattr(context, "_intention_injector", None),
        )

        if doctor_response:
            # Handle Doctor's recommended action
            action_taken, should_continue = doctor_integration.handle_doctor_action(
                phase=context.phase,
                response=doctor_response,
                attempt_index=context.attempt_index,
                llm_service=context.llm_service,
            )

            if not should_continue:
                # [BUILD-041] Doctor recommended skipping - mark phase FAILED
                if context.mark_phase_failed_in_db:
                    context.mark_phase_failed_in_db(phase_id, f"DOCTOR_SKIP: {status}")
                logger.warning(f"[{phase_id}] Doctor recommended skipping, marking FAILED")
                return ExecutionResult(
                    success=False,
                    status=status,
                    phase_result=PhaseResult.FAILED,
                    updated_counters={
                        "total_failures": context.run_total_failures,
                        "http_500_count": context.run_http_500_count,
                        "patch_failure_count": context.run_patch_failure_count,
                        "doctor_calls": context.run_doctor_calls + 1,
                        "replan_count": context.run_replan_count,
                    },
                    should_continue=False,
                )

            if action_taken == "replan":
                # BUILD-050 Phase 2: Non-destructive replanning
                return self._handle_doctor_replan(context, phase_id)

        # INSERTION POINT 3: Intention-first stuck handling dispatch (BUILD-161 Phase A)
        intention_result = self._check_intention_stuck_handling(context, status)
        if intention_result:
            return intention_result

        # Check if we should trigger re-planning before next retry
        replan_result = self._check_replan_trigger(context)
        if replan_result:
            return replan_result

        # [BUILD-041] Increment attempts_used in database
        new_attempts = context.attempt_index + 1
        if context.update_phase_attempts_in_db:
            context.update_phase_attempts_in_db(
                phase_id, retry_attempt=new_attempts, last_failure_reason=status
            )

        # Token-efficiency guard: CI collection/import errors are deterministic
        status_lower = (status or "").lower()
        if (
            "ci collection/import error" in status_lower
            or "collection errors detected" in status_lower
        ):
            logger.error(
                f"[{phase_id}] Deterministic CI collection/import failure. "
                f"Skipping escalation/retry to avoid token waste."
            )
            return ExecutionResult(
                success=False,
                status=status,
                phase_result=PhaseResult.FAILED,
                updated_counters={
                    "total_failures": context.run_total_failures,
                    "http_500_count": context.run_http_500_count,
                    "patch_failure_count": context.run_patch_failure_count,
                    "doctor_calls": context.run_doctor_calls,
                    "replan_count": context.run_replan_count,
                },
                should_continue=False,
            )

        # Check if attempts exhausted
        if new_attempts >= context.max_attempts:
            return self._handle_max_attempts_exhausted(context, phase_id, new_attempts)

        logger.warning(
            f"[{phase_id}] Attempt {new_attempts}/{context.max_attempts} failed, will escalate model for next retry"
        )
        return ExecutionResult(
            success=False,
            status=status,
            phase_result=PhaseResult.FAILED,
            updated_counters={
                "total_failures": context.run_total_failures,
                "http_500_count": context.run_http_500_count,
                "patch_failure_count": context.run_patch_failure_count,
                "doctor_calls": context.run_doctor_calls,
                "replan_count": context.run_replan_count,
            },
            should_continue=True,
        )

    def _try_failure_hardening(
        self, context: ExecutionContext, status: str, phase_id: str
    ) -> Optional[ExecutionResult]:
        """
        Try deterministic failure hardening before expensive diagnostics/Doctor.

        Returns ExecutionResult if hardening was applied and claims fix, None otherwise.
        """
        if os.getenv("AUTOPACK_ENABLE_FAILURE_HARDENING", "false").lower() != "true":
            return None

        from autopack.failure_hardening import detect_and_mitigate_failure

        error_text = f"Status: {status}, Attempt: {context.attempt_index + 1}"
        hardening_context = {
            "workspace": (Path(context.workspace_root) if context.workspace_root else Path.cwd()),
            "phase_id": phase_id,
            "status": status,
            "scope_paths": context.phase.get("scope", {}).get("paths", []),
        }

        mitigation_result = detect_and_mitigate_failure(error_text, hardening_context)

        if not mitigation_result:
            return None

        logger.info(
            f"[{phase_id}] Failure hardening detected pattern: {mitigation_result.pattern_id} "
            f"(success={mitigation_result.success}, fixed={mitigation_result.fixed})"
        )
        logger.info(f"[{phase_id}] Actions taken: {mitigation_result.actions_taken}")
        logger.info(f"[{phase_id}] Suggestions: {mitigation_result.suggestions}")

        # Record mitigation in learning hints
        if context.record_learning_hint:
            context.record_learning_hint(
                phase=context.phase,
                hint_type="failure_hardening_applied",
                details=f"Pattern: {mitigation_result.pattern_id}, Fixed: {mitigation_result.fixed}",
            )

        # If mitigation claims it's fixed, skip diagnostics/Doctor and retry immediately
        if mitigation_result.fixed:
            logger.info(
                f"[{phase_id}] Failure hardening claims fix applied, skipping diagnostics/Doctor"
            )

            # [BUILD-146 P2] Record Phase 6 telemetry for failure hardening
            self._record_failure_hardening_telemetry(
                context, phase_id, mitigation_result, avoided_doctor=True
            )

            # Increment attempts and return for immediate retry
            new_attempts = context.attempt_index + 1
            if context.update_phase_attempts_in_db:
                context.update_phase_attempts_in_db(
                    phase_id,
                    retry_attempt=new_attempts,
                    last_failure_reason=f"HARDENING_MITIGATED: {mitigation_result.pattern_id}",
                )

            # Return FAILED status so caller can retry immediately with mitigation applied
            return ExecutionResult(
                success=False,
                status="FAILED",
                phase_result=PhaseResult.FAILED,
                updated_counters={
                    "total_failures": context.run_total_failures,
                    "http_500_count": context.run_http_500_count,
                    "patch_failure_count": context.run_patch_failure_count,
                    "doctor_calls": context.run_doctor_calls,
                    "replan_count": context.run_replan_count,
                },
                should_continue=True,
            )

        return None

    def _record_failure_hardening_telemetry(
        self, context: ExecutionContext, phase_id: str, mitigation_result, avoided_doctor: bool
    ):
        """Record Phase 6 telemetry for failure hardening (BUILD-146 P2)."""
        if os.getenv("TELEMETRY_DB_ENABLED", "false").lower() != "true":
            return

        try:
            from autopack.usage_recorder import (
                record_phase6_metrics,
                estimate_doctor_tokens_avoided,
            )
            from autopack.database import SessionLocal

            db = SessionLocal()
            try:
                # BUILD-146 P3: Use median-based estimation with coverage tracking
                estimate, coverage_n, source = estimate_doctor_tokens_avoided(
                    db=db,
                    run_id=context.run_id,
                    doctor_model=None,  # Could enhance to track expected model
                )

                record_phase6_metrics(
                    db=db,
                    run_id=context.run_id,
                    phase_id=phase_id,
                    failure_hardening_triggered=True,
                    failure_pattern_detected=mitigation_result.pattern_id,
                    failure_hardening_mitigated=True,
                    doctor_call_skipped=avoided_doctor,
                    doctor_tokens_avoided_estimate=estimate,
                    estimate_coverage_n=coverage_n,
                    estimate_source=source,
                )
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to record Phase 6 telemetry: {e}")

    def _check_intention_stuck_handling(
        self, context: ExecutionContext, status: str
    ) -> Optional[ExecutionResult]:
        """
        Check and handle intention-first stuck scenarios (BUILD-161).

        Returns ExecutionResult if stuck handling was triggered, None otherwise.
        """
        if not (context.intention_wiring is not None and context.intention_anchor is not None):
            return None

        from autopack.executor.intention_stuck_handler import IntentionStuckHandler

        phase_id = context.phase.get("phase_id")

        # Map failure status to stuck reason
        if "BUDGET" in status.upper():
            pass
        elif "TRUNCAT" in status.upper():
            pass

        # BUILD-190: Use run-level accumulated token usage for budget decisions
        tokens_used = context.run_tokens_used
        context_chars_used = context.run_context_chars_used
        sot_chars_used = context.run_sot_chars_used

        stuck_handler = IntentionStuckHandler()

        try:
            decision, decision_msg = stuck_handler.handle_stuck_scenario(
                wiring=context.intention_wiring,
                phase_id=phase_id,
                phase_spec=context.phase,
                anchor=context.intention_anchor,
                status=status,
                tokens_used=tokens_used,
                context_chars_used=context_chars_used,
                sot_chars_used=sot_chars_used,
                run_budget_tokens=context.run_budget_tokens,
                llm_service=context.llm_service,
            )

            logger.info(f"[IntentionFirst] {decision_msg}")

            # Return result based on decision
            if decision == "REPLAN":
                return ExecutionResult(
                    success=False,
                    status="REPLAN_REQUESTED",
                    phase_result=PhaseResult.REPLAN_REQUESTED,
                    updated_counters={
                        "total_failures": context.run_total_failures,
                        "http_500_count": context.run_http_500_count,
                        "patch_failure_count": context.run_patch_failure_count,
                        "doctor_calls": context.run_doctor_calls,
                        "replan_count": context.run_replan_count,
                    },
                    should_continue=False,
                )
            elif decision == "BLOCKED_NEEDS_HUMAN":
                return ExecutionResult(
                    success=False,
                    status="BLOCKED_NEEDS_HUMAN",
                    phase_result=PhaseResult.BLOCKED,
                    updated_counters={
                        "total_failures": context.run_total_failures,
                        "http_500_count": context.run_http_500_count,
                        "patch_failure_count": context.run_patch_failure_count,
                        "doctor_calls": context.run_doctor_calls,
                        "replan_count": context.run_replan_count,
                    },
                    should_continue=False,
                )
            elif decision == "STOP":
                return ExecutionResult(
                    success=False,
                    status="FAILED",
                    phase_result=PhaseResult.FAILED,
                    updated_counters={
                        "total_failures": context.run_total_failures,
                        "http_500_count": context.run_http_500_count,
                        "patch_failure_count": context.run_patch_failure_count,
                        "doctor_calls": context.run_doctor_calls,
                        "replan_count": context.run_replan_count,
                    },
                    should_continue=False,
                )

            # ESCALATE_MODEL or REDUCE_SCOPE - phase was modified, continue with retry
            return None

        except Exception as e:
            logger.warning(
                f"[IntentionFirst] Stuck decision failed: {e}, falling back to existing logic"
            )
            return None

    def _check_replan_trigger(self, context: ExecutionContext) -> Optional[ExecutionResult]:
        """
        Check if we should trigger re-planning before next retry.

        Returns ExecutionResult if replan was triggered, None otherwise.
        """
        from autopack.executor.replan_trigger import ReplanTrigger

        phase_id = context.phase.get("phase_id")
        replan_trigger = ReplanTrigger()

        # Get error history for this phase
        error_history = context.phase_error_history.get(phase_id, [])

        should_replan, flaw_type = replan_trigger.should_trigger_replan(
            phase=context.phase,
            error_history=error_history,
            replan_count=0,  # Would need to track this
            run_replan_count=context.run_replan_count,
        )

        if not should_replan:
            return None

        logger.info(f"[{phase_id}] Triggering mid-run re-planning due to {flaw_type}")

        # Invoke re-planner
        revised_phase = replan_trigger.revise_phase_approach(
            phase=context.phase,
            flaw_type=flaw_type,
            error_history=error_history,
            original_intent="",  # Would need to retrieve this
            llm_service=context.llm_service,
        )

        if revised_phase:
            # BUILD-050 Phase 2: Non-destructive replanning
            context.run_replan_count += 1

            if context.get_phase_from_db and context.update_phase_attempts_in_db:
                phase_db = context.get_phase_from_db(phase_id)
                if phase_db:
                    new_epoch = phase_db.revision_epoch + 1
                    logger.info(
                        f"[{phase_id}] Re-planning successful (run total: {context.run_replan_count}), "
                        f"epoch {phase_db.revision_epoch} → {new_epoch}, preserving retry progress"
                    )
                    context.update_phase_attempts_in_db(
                        phase_id, revision_epoch=new_epoch, last_failure_reason="REPLANNED"
                    )

            return ExecutionResult(
                success=False,
                status="REPLAN_REQUESTED",
                phase_result=PhaseResult.REPLAN_REQUESTED,
                updated_counters={
                    "total_failures": context.run_total_failures,
                    "http_500_count": context.run_http_500_count,
                    "patch_failure_count": context.run_patch_failure_count,
                    "doctor_calls": context.run_doctor_calls,
                    "replan_count": context.run_replan_count,
                },
                should_continue=False,
            )
        else:
            logger.warning(f"[{phase_id}] Re-planning failed, continuing with original approach")
            return None

    def _handle_doctor_replan(self, context: ExecutionContext, phase_id: str) -> ExecutionResult:
        """Handle Doctor-triggered replanning (BUILD-050 Phase 2)."""
        if context.get_phase_from_db and context.update_phase_attempts_in_db:
            phase_db = context.get_phase_from_db(phase_id)
            if phase_db:
                new_epoch = phase_db.revision_epoch + 1
                logger.info(
                    f"[{phase_id}] Doctor triggered re-planning (epoch {phase_db.revision_epoch} → {new_epoch}), "
                    f"preserving retry progress (retry_attempt={phase_db.retry_attempt}, escalation={phase_db.escalation_level})"
                )
                context.update_phase_attempts_in_db(
                    phase_id, revision_epoch=new_epoch, last_failure_reason="DOCTOR_REPLAN"
                )

        return ExecutionResult(
            success=False,
            status="REPLAN_REQUESTED",
            phase_result=PhaseResult.REPLAN_REQUESTED,
            updated_counters={
                "total_failures": context.run_total_failures,
                "http_500_count": context.run_http_500_count,
                "patch_failure_count": context.run_patch_failure_count,
                "doctor_calls": context.run_doctor_calls + 1,
                "replan_count": context.run_replan_count,
            },
            should_continue=False,
        )

    def _handle_max_attempts_exhausted(
        self, context: ExecutionContext, phase_id: str, new_attempts: int
    ) -> ExecutionResult:
        """Handle when max attempts are exhausted."""
        logger.error(
            f"[{phase_id}] All {context.max_attempts} attempts exhausted. Marking phase as FAILED."
        )

        # Log to debug journal for persistent tracking
        from autopack.debug_journal import log_error

        log_error(
            error_signature=f"Phase {phase_id} max attempts exhausted",
            symptom=f"Phase failed after {context.max_attempts} attempts with model escalation",
            run_id=context.run_id,
            phase_id=phase_id,
            suspected_cause="Task complexity exceeds model capabilities or task is impossible",
            priority="HIGH",
        )

        if context.mark_phase_failed_in_db:
            context.mark_phase_failed_in_db(phase_id, "MAX_ATTEMPTS_EXHAUSTED")

        return ExecutionResult(
            success=False,
            status="FAILED",
            phase_result=PhaseResult.FAILED,
            updated_counters={
                "total_failures": context.run_total_failures,
                "http_500_count": context.run_http_500_count,
                "patch_failure_count": context.run_patch_failure_count,
                "doctor_calls": context.run_doctor_calls,
                "replan_count": context.run_replan_count,
            },
            should_continue=False,
        )

    def _handle_exception(self, context: ExecutionContext, exc: Exception) -> ExecutionResult:
        """
        Handle exception during execution.

        Includes diagnostics, Doctor invocation, and replan checks.
        """
        from autopack.error_reporter import report_error
        from autopack.debug_journal import log_error

        phase_id = context.phase.get("phase_id")
        logger.error(f"[{phase_id}] Attempt {context.attempt_index + 1} raised exception: {exc}")

        # Report detailed error context for debugging
        report_error(
            error=exc,
            run_id=context.run_id,
            phase_id=phase_id,
            component="executor",
            operation="execute_phase",
            context_data={
                "attempt_index": context.attempt_index,
                "max_retry_attempts": self.max_retry_attempts,
                "phase_description": context.phase.get("description", "")[:200],
                "phase_complexity": context.phase.get("complexity"),
                "phase_task_category": context.phase.get("task_category"),
            },
        )

        # Update health budget tracking
        context.run_total_failures += 1
        error_str = str(exc).lower()
        if "500" in error_str or "internal server error" in error_str:
            context.run_http_500_count += 1

        # Mid-Run Re-Planning: Record error for approach flaw detection
        if context.record_phase_error:
            context.record_phase_error(
                phase=context.phase,
                error_type="infra_error",
                error_details=str(exc),
                attempt_index=context.attempt_index,
            )

        # Diagnostics: gather evidence for infra errors before any mutations
        if context.run_diagnostics_for_failure:
            context.run_diagnostics_for_failure(
                failure_class="infra_error",
                phase=context.phase,
                context={
                    "exception": str(exc)[:300],
                    "attempt_index": context.attempt_index,
                },
            )

        # [Doctor Integration] Invoke Doctor for diagnosis on exceptions
        from autopack.executor.doctor_integration import DoctorIntegration

        doctor_integration = DoctorIntegration()

        doctor_response = doctor_integration.invoke_doctor(
            phase=context.phase,
            error_category="infra_error",
            builder_attempts=context.attempt_index + 1,
            last_patch=None,
            patch_errors=[],
            logs_excerpt=f"Exception: {type(exc).__name__}: {str(exc)[:500]}",
            llm_service=context.llm_service,
            run_id=context.run_id,
            doctor_calls_by_phase={},
            run_doctor_calls=context.run_doctor_calls,
            intention_injector=None,
        )

        if doctor_response:
            action_taken, should_continue = doctor_integration.handle_doctor_action(
                phase=context.phase,
                response=doctor_response,
                attempt_index=context.attempt_index,
                llm_service=context.llm_service,
            )

            if not should_continue:
                # [BUILD-041] Doctor recommended skipping - mark phase FAILED
                if context.mark_phase_failed_in_db:
                    context.mark_phase_failed_in_db(phase_id, f"DOCTOR_SKIP: {type(exc).__name__}")
                return ExecutionResult(
                    success=False,
                    status="FAILED",
                    phase_result=PhaseResult.FAILED,
                    updated_counters={
                        "total_failures": context.run_total_failures,
                        "http_500_count": context.run_http_500_count,
                        "patch_failure_count": context.run_patch_failure_count,
                        "doctor_calls": context.run_doctor_calls + 1,
                        "replan_count": context.run_replan_count,
                    },
                    should_continue=False,
                )

            if action_taken == "replan":
                # BUILD-050 Phase 2: Non-destructive replanning after exception
                return self._handle_doctor_replan_exception(context, phase_id)

        # Check if we should trigger re-planning before next retry
        replan_result = self._check_replan_trigger_exception(context)
        if replan_result:
            return replan_result

        # [BUILD-041] Increment attempts_used in database after exception
        new_attempts = context.attempt_index + 1
        if context.update_phase_attempts_in_db:
            context.update_phase_attempts_in_db(
                phase_id,
                retry_attempt=new_attempts,
                last_failure_reason=f"EXCEPTION: {type(exc).__name__}",
            )

        # Check if attempts exhausted
        if new_attempts >= context.max_attempts:
            logger.error(
                f"[{phase_id}] All {context.max_attempts} attempts exhausted after exception. Marking phase as FAILED."
            )

            # Log to debug journal for persistent tracking
            log_error(
                error_signature=f"Phase {phase_id} max attempts exhausted (exception)",
                symptom=f"Phase failed after {context.max_attempts} attempts with final exception: {type(exc).__name__}",
                run_id=context.run_id,
                phase_id=phase_id,
                suspected_cause=str(exc)[:200],
                priority="HIGH",
            )

            if context.mark_phase_failed_in_db:
                context.mark_phase_failed_in_db(
                    phase_id, f"MAX_ATTEMPTS_EXHAUSTED: {type(exc).__name__}"
                )

            return ExecutionResult(
                success=False,
                status="FAILED",
                phase_result=PhaseResult.FAILED,
                updated_counters={
                    "total_failures": context.run_total_failures,
                    "http_500_count": context.run_http_500_count,
                    "patch_failure_count": context.run_patch_failure_count,
                    "doctor_calls": context.run_doctor_calls,
                    "replan_count": context.run_replan_count,
                },
                should_continue=False,
            )

        logger.warning(
            f"[{phase_id}] Attempt {new_attempts}/{context.max_attempts} raised exception, will retry"
        )
        return ExecutionResult(
            success=False,
            status="EXCEPTION_OCCURRED",
            phase_result=PhaseResult.FAILED,
            updated_counters={
                "total_failures": context.run_total_failures,
                "http_500_count": context.run_http_500_count,
                "patch_failure_count": context.run_patch_failure_count,
                "doctor_calls": context.run_doctor_calls,
                "replan_count": context.run_replan_count,
            },
            should_continue=True,
        )

    def _handle_doctor_replan_exception(
        self, context: ExecutionContext, phase_id: str
    ) -> ExecutionResult:
        """Handle Doctor-triggered replanning after exception."""
        if context.get_phase_from_db and context.update_phase_attempts_in_db:
            phase_db = context.get_phase_from_db(phase_id)
            if phase_db:
                new_epoch = phase_db.revision_epoch + 1
                logger.info(
                    f"[{phase_id}] Doctor triggered re-planning after exception (epoch {phase_db.revision_epoch} → {new_epoch}), "
                    f"preserving retry progress"
                )
                context.update_phase_attempts_in_db(
                    phase_id,
                    revision_epoch=new_epoch,
                    last_failure_reason="DOCTOR_REPLAN_AFTER_EXCEPTION",
                )

        return ExecutionResult(
            success=False,
            status="REPLAN_REQUESTED",
            phase_result=PhaseResult.REPLAN_REQUESTED,
            updated_counters={
                "total_failures": context.run_total_failures,
                "http_500_count": context.run_http_500_count,
                "patch_failure_count": context.run_patch_failure_count,
                "doctor_calls": context.run_doctor_calls + 1,
                "replan_count": context.run_replan_count,
            },
            should_continue=False,
        )

    def _check_replan_trigger_exception(
        self, context: ExecutionContext
    ) -> Optional[ExecutionResult]:
        """Check if we should trigger re-planning after exception."""
        from autopack.executor.replan_trigger import ReplanTrigger

        phase_id = context.phase.get("phase_id")
        replan_trigger = ReplanTrigger()

        error_history = context.phase_error_history.get(phase_id, [])

        should_replan, flaw_type = replan_trigger.should_trigger_replan(
            phase=context.phase,
            error_history=error_history,
            replan_count=0,
            run_replan_count=context.run_replan_count,
        )

        if not should_replan:
            return None

        logger.info(f"[{phase_id}] Triggering mid-run re-planning due to {flaw_type}")

        revised_phase = replan_trigger.revise_phase_approach(
            phase=context.phase,
            flaw_type=flaw_type,
            error_history=error_history,
            original_intent="",
            llm_service=context.llm_service,
        )

        if revised_phase:
            # BUILD-050 Phase 2: Non-destructive replanning after exception
            context.run_replan_count += 1

            if context.get_phase_from_db and context.update_phase_attempts_in_db:
                phase_db = context.get_phase_from_db(phase_id)
                if phase_db:
                    new_epoch = phase_db.revision_epoch + 1
                    logger.info(
                        f"[{phase_id}] Re-planning successful (run total: {context.run_replan_count}), "
                        f"epoch {phase_db.revision_epoch} → {new_epoch}, preserving retry progress"
                    )
                    context.update_phase_attempts_in_db(
                        phase_id,
                        revision_epoch=new_epoch,
                        last_failure_reason="REPLANNED_AFTER_EXCEPTION",
                    )

            return ExecutionResult(
                success=False,
                status="REPLAN_REQUESTED",
                phase_result=PhaseResult.REPLAN_REQUESTED,
                updated_counters={
                    "total_failures": context.run_total_failures,
                    "http_500_count": context.run_http_500_count,
                    "patch_failure_count": context.run_patch_failure_count,
                    "doctor_calls": context.run_doctor_calls,
                    "replan_count": context.run_replan_count,
                },
                should_continue=False,
            )

        return None


# IMP-P06: Parallel execution utilities for independent operations
def execute_parallel(
    operations: List[Tuple[str, Callable[[], Any]]], max_workers: int = 2
) -> Dict[str, Any]:
    """
    Execute multiple independent operations in parallel using a thread pool.

    This utility enables parallel execution of CI checks, Auditor reviews, and other
    independent validation steps to reduce total phase execution time.

    IMP-P06: Saves 5-15s per phase by running Auditor review concurrently with CI execution.

    Args:
        operations: List of (operation_name, callable) tuples where each callable
                   performs an independent operation and returns a result.
        max_workers: Maximum number of parallel workers (default: 2 for CI + Auditor)

    Returns:
        Dict mapping operation names to their results. If an operation raises an
        exception, the result will be the exception object.

    Example:
        results = execute_parallel([
            ("ci_check", lambda: run_ci_tests()),
            ("auditor_review", lambda: run_auditor_review()),
        ])
        ci_passed = results["ci_check"]
        audit_passed = results["auditor_review"]
    """
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all operations
        future_to_name = {
            executor.submit(op_callable): op_name for op_name, op_callable in operations
        }

        # Collect results as they complete
        for future in as_completed(future_to_name):
            op_name = future_to_name[future]
            try:
                result = future.result()
                results[op_name] = result
                logger.debug(f"[ParallelExecution] {op_name} completed successfully")
            except Exception as exc:
                logger.warning(f"[ParallelExecution] {op_name} raised exception: {exc}")
                results[op_name] = exc

    return results
