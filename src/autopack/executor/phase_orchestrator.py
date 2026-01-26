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

from autopack.config import settings
from autopack.autonomous.budgeting import (
    is_phase_budget_exceeded,
    get_phase_budget_remaining_pct,
)
from autopack.time_watchdog import TimeWatchdog

logger = logging.getLogger(__name__)


def create_default_time_watchdog() -> TimeWatchdog:
    """IMP-SAFETY-004: Factory function to create TimeWatchdog with config defaults.

    This function ensures that TimeWatchdog is always instantiated with proper
    configuration values. It MUST be used when creating ExecutionContext to
    guarantee phase timeout enforcement.

    Returns:
        TimeWatchdog configured with:
        - Run timeout from settings.run_max_duration_minutes
        - Phase timeout from settings.phase_timeout_minutes

    Example:
        context = ExecutionContext(
            phase=phase_spec,
            time_watchdog=create_default_time_watchdog(),
            ...
        )
    """
    return TimeWatchdog(
        max_run_wall_clock_sec=settings.run_max_duration_minutes * 60,
        max_phase_wall_clock_sec=settings.phase_timeout_minutes * 60,
    )


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
    # IMP-SAFETY-004: time_watchdog is mandatory for phase timeout enforcement
    # Phases can run indefinitely if no watchdog is provided, burning entire run budget.
    # Use create_default_time_watchdog() factory to create with config defaults.
    time_watchdog: Any  # Required: TimeWatchdog instance for phase timeout
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
    memory_context: Optional[str] = None  # IMP-ARCH-002: Memory context for builder injection


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
    - IMP-TEL-004: Real-time anomaly detection and alert routing
    """

    def __init__(
        self,
        max_retry_attempts: int = 5,
        anomaly_detector: Optional[Any] = None,
        alert_router: Optional[Any] = None,
    ):
        """Initialize the PhaseOrchestrator.

        Args:
            max_retry_attempts: Maximum number of retry attempts per phase.
            anomaly_detector: Optional TelemetryAnomalyDetector for real-time anomaly detection.
                             If provided, phase outcomes are analyzed for token spikes,
                             duration anomalies, and failure rate threshold breaches.
            alert_router: Optional AlertRouter for routing detected anomaly alerts.
                         If provided, alerts are routed to appropriate handlers
                         (logging, auto-healing, persistence).
        """
        self.max_retry_attempts = max_retry_attempts
        # IMP-TEL-004: Anomaly detection and alert routing
        self.anomaly_detector = anomaly_detector
        self.alert_router = alert_router

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

        # IMP-COST-002: Check phase-level budget before execution
        phase_budget_result = self._check_phase_budget(context)
        if phase_budget_result:
            return phase_budget_result

        # IMP-STUCK-001: Check phase wall-clock timeout before execution
        phase_timeout_result = self._check_phase_timeout(context)
        if phase_timeout_result:
            return phase_timeout_result

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
        IMP-STUCK-001: Start phase timeout tracking.
        """
        phase_id = context.phase.get("phase_id")

        # IMP-SAFETY-004: Start tracking phase wall-clock time (time_watchdog is mandatory)
        context.time_watchdog.track_phase_start(phase_id)
        timeout_min = settings.phase_timeout_minutes
        logger.debug(
            f"[IMP-SAFETY-004] Phase {phase_id}: timeout tracking started ({timeout_min} min limit)"
        )

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

        IMP-COORD-001: After scope generation, invalidates cached context to ensure
        Builder and Auditor receive fresh context based on the new scope.
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

                    # IMP-COORD-001: Invalidate cached context after scope change
                    self._invalidate_phase_context_cache(context)

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

    def _invalidate_phase_context_cache(self, context: ExecutionContext) -> None:
        """IMP-COORD-001: Mark phase context for cache invalidation after scope changes.

        When a phase's scope is generated or modified, cached file context from a previous
        scope becomes stale. This method marks the phase so that the executor will clear
        cached context before the next Builder/Auditor invocation.

        This addresses ~30% false Auditor rejections caused by stale context mismatches
        where Auditor sees old scope files while Builder worked with new scope files.

        Args:
            context: Execution context with phase information
        """
        phase_id = context.phase.get("phase_id")

        # IMP-COORD-001: Mark phase metadata to signal cache invalidation needed
        # The autonomous_executor will check this flag before loading context and
        # clear _last_file_context and LRU caches in builder_orchestrator
        context.phase["_require_context_refresh"] = True
        context.phase["_context_refresh_reason"] = "scope_changed"

        logger.info(
            f"[IMP-COORD-001] Marked phase '{phase_id}' for context refresh after scope change"
        )

    def _check_phase_budget(self, context: ExecutionContext) -> Optional[ExecutionResult]:
        """IMP-COST-002: Check phase-level token budget before execution.

        Returns ExecutionResult if budget exceeded, None if budget OK to proceed.
        """
        phase_id = context.phase.get("phase_id")
        phase_type = context.phase.get("category") or "implementation"

        # Get phase-specific token cap based on phase type
        phase_token_cap = settings.get_phase_token_cap(phase_type)

        # Get phase's current token usage (would need to be tracked per-phase)
        # For now, use a placeholder - in production this would query LlmUsageEvent
        phase_tokens_used = context.phase.get("_tokens_used", 0)

        # Check if phase budget exceeded
        if is_phase_budget_exceeded(phase_tokens_used, phase_token_cap):
            budget_pct = get_phase_budget_remaining_pct(phase_tokens_used, phase_token_cap) * 100
            error_msg = (
                f"Phase {phase_id} exceeded token budget: "
                f"{phase_tokens_used}/{phase_token_cap} tokens ({100 - budget_pct:.1f}% used). "
                f"Phase type: {phase_type}. "
                f"Consider: 1) Reduce phase scope, 2) Switch to smaller model, "
                f"3) Request escalation approval to increase phase budget."
            )
            logger.error(f"[PHASE_BUDGET_EXCEEDED] {error_msg}")

            if context.mark_phase_failed_in_db:
                context.mark_phase_failed_in_db(phase_id, "PHASE_TOKEN_BUDGET_EXCEEDED")

            return ExecutionResult(
                success=False,
                status="PHASE_TOKEN_BUDGET_EXCEEDED",
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

        # Log phase budget status
        budget_remaining = phase_token_cap - phase_tokens_used
        budget_pct = get_phase_budget_remaining_pct(phase_tokens_used, phase_token_cap) * 100
        logger.info(
            f"Phase {phase_id}: {budget_remaining} tokens remaining "
            f"({budget_pct:.1f}% of {phase_token_cap} cap, type={phase_type})"
        )

        return None  # Budget OK, proceed with execution

    def _check_phase_timeout(self, context: ExecutionContext) -> Optional[ExecutionResult]:
        """IMP-SAFETY-004: Check if phase has exceeded wall-clock timeout.

        Returns ExecutionResult if timeout exceeded, None if time OK to proceed.
        Logs soft warning at 50% threshold without failing.

        Note: time_watchdog is mandatory per IMP-SAFETY-004 - phases cannot run
        indefinitely. The watchdog must be provided when creating ExecutionContext.
        """
        phase_id = context.phase.get("phase_id")
        timeout_sec = settings.phase_timeout_minutes * 60

        exceeded, elapsed, soft_warning = context.time_watchdog.check_phase_timeout(
            phase_id, timeout_sec
        )

        if exceeded:
            # Hard timeout - fail phase
            elapsed_str = context.time_watchdog.format_elapsed(elapsed)
            timeout_min = settings.phase_timeout_minutes
            error_msg = (
                f"Phase {phase_id} exceeded wall-clock timeout: {elapsed_str} > {timeout_min} min. "
                f"This indicates a runaway phase burning run budget. "
                f"Consider: 1) Reduce phase scope/complexity, 2) Check for infinite loops, "
                f"3) Request timeout extension if legitimately needed."
            )
            logger.error(f"[PHASE_TIMEOUT_EXCEEDED] {error_msg}")

            if context.mark_phase_failed_in_db:
                context.mark_phase_failed_in_db(phase_id, "PHASE_WALL_CLOCK_TIMEOUT")

            # Record telemetry for timeout
            self._record_phase_outcome(
                phase_id=phase_id,
                run_id=context.run_id,
                outcome="FAILED",
                stop_reason="phase_wall_clock_timeout",
                rationale=f"Exceeded {timeout_min}min timeout after {elapsed_str}",
                tokens_used=getattr(context, "phase_tokens_used", None),
                duration_seconds=elapsed,
                model_used=getattr(context, "model_used", None),
                phase_type=context.phase.get("category"),
            )

            return ExecutionResult(
                success=False,
                status="PHASE_WALL_CLOCK_TIMEOUT",
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

        if soft_warning:
            # Soft warning at 50% - log but continue
            elapsed_str = context.time_watchdog.format_elapsed(elapsed)
            remaining_sec = context.time_watchdog.get_phase_remaining_sec(phase_id, timeout_sec)
            remaining_str = context.time_watchdog.format_elapsed(remaining_sec)
            timeout_min = settings.phase_timeout_minutes
            logger.warning(
                f"[PHASE_TIMEOUT_WARNING] Phase {phase_id} has used {elapsed_str} "
                f"(50% of {timeout_min} min timeout). Remaining: {remaining_str}. "
                f"Consider wrapping up to avoid hard timeout."
            )

        return None  # Time OK, proceed with execution

    def _create_exhausted_result(self, context: ExecutionContext) -> ExecutionResult:
        """Create result when max attempts are exhausted."""
        phase_id = context.phase.get("phase_id")
        logger.warning(
            f"[{phase_id}] Phase has already exhausted all attempts "
            f"({context.attempt_index}/{self.max_retry_attempts}). Marking as FAILED."
        )

        if context.mark_phase_failed_in_db:
            context.mark_phase_failed_in_db(phase_id, "MAX_ATTEMPTS_EXHAUSTED")

        # ROAD-A: Record phase outcome for telemetry analysis
        self._record_phase_outcome(
            phase_id=phase_id,
            run_id=context.run_id,
            outcome="FAILED",
            stop_reason="max_attempts_exhausted",
            tokens_used=getattr(context, "phase_tokens_used", None),
            duration_seconds=getattr(context, "phase_duration_seconds", None),
            model_used=getattr(context, "model_used", None),
            phase_type=context.phase.get("category"),
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
            memory_context=context.memory_context,  # IMP-ARCH-002: Memory context injection
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

        # ROAD-A: Record phase outcome for telemetry analysis
        self._record_phase_outcome(
            phase_id=phase_id,
            run_id=context.run_id,
            outcome="SUCCESS",
            stop_reason="completed",
            tokens_used=getattr(context, "phase_tokens_used", None),
            duration_seconds=getattr(context, "phase_duration_seconds", None),
            model_used=getattr(context, "model_used", None),
            phase_type=context.phase.get("category"),
        )

        logger.info(
            f"[{phase_id}] Phase completed successfully on attempt {context.attempt_index + 1}"
        )

        # IMP-SAFETY-004: Clear phase timer for completed phase (time_watchdog is mandatory)
        context.time_watchdog.clear_phase_timer(phase_id)

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
            # IMP-DOCTOR-002: Record Doctor outcome (initial invocation)
            doctor_integration.record_doctor_outcome(
                run_id=context.run_id,
                phase_id=phase_id,
                error_category=failure_outcome,
                builder_attempts=context.attempt_index + 1,
                doctor_response=doctor_response,
                recommendation_followed=True,  # Will update if action not taken
                phase_succeeded=None,  # Not known yet
                attempts_after_doctor=None,
                final_outcome=None,
                doctor_tokens_used=None,  # Could extract from llm_service if available
                model_used=None,  # Could extract from llm_service if available
            )

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

    def _record_phase_outcome(
        self,
        phase_id: str,
        run_id: str,
        outcome: str,
        stop_reason: str = None,
        rationale: str = None,
        tokens_used: int = None,
        duration_seconds: float = None,
        model_used: str = None,
        phase_type: str = None,
    ):
        """Record phase outcome with stop reason and metrics for downstream analysis (ROAD-A).

        Enables:
        - ROAD-B: Automated telemetry analysis
        - ROAD-G: Real-time anomaly detection
        - ROAD-L: Telemetry-driven model optimization
        - IMP-TEL-004: Route anomaly alerts from phase execution
        """
        if os.getenv("TELEMETRY_DB_ENABLED", "false").lower() != "true":
            return

        try:
            from autopack.models import PhaseOutcomeEvent
            from autopack.database import SessionLocal

            db = SessionLocal()
            try:
                event = PhaseOutcomeEvent(
                    run_id=run_id,
                    phase_id=phase_id,
                    phase_type=phase_type,
                    phase_outcome=outcome,
                    stop_reason=stop_reason,
                    stuck_decision_rationale=rationale,
                    tokens_used=tokens_used,
                    duration_seconds=duration_seconds,
                    model_used=model_used,
                )
                db.add(event)
                db.commit()
                logger.debug(f"[ROAD-A] Recorded phase outcome: {phase_id} -> {outcome}")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to record ROAD-A phase outcome: {e}")

        # IMP-TEL-004: Real-time anomaly detection and alert routing
        # After recording phase outcome, check for anomalies and route alerts
        self._detect_and_route_anomalies(
            phase_id=phase_id,
            run_id=run_id,
            phase_type=phase_type,
            outcome=outcome,
            tokens_used=tokens_used,
            duration_seconds=duration_seconds,
        )

    def _detect_and_route_anomalies(
        self,
        phase_id: str,
        run_id: str,
        phase_type: str,
        outcome: str,
        tokens_used: int = None,
        duration_seconds: float = None,
    ) -> None:
        """IMP-TEL-004: Detect anomalies in phase metrics and route alerts.

        Called after each phase outcome is recorded to enable real-time anomaly detection.
        Anomalies are detected based on:
        - Token usage spikes (>2x rolling baseline)
        - Duration anomalies (>p95 threshold)
        - Failure rate threshold breaches

        Args:
            phase_id: The phase identifier
            run_id: The run identifier
            phase_type: Phase category for baseline grouping
            outcome: Phase outcome (SUCCESS/FAILED)
            tokens_used: Tokens consumed during phase execution
            duration_seconds: Phase execution duration
        """
        if not self.anomaly_detector:
            return

        # Skip if we don't have the required metrics
        if tokens_used is None or duration_seconds is None:
            logger.debug(
                f"[IMP-TEL-004] Skipping anomaly detection for {phase_id}: "
                f"missing metrics (tokens={tokens_used}, duration={duration_seconds})"
            )
            return

        try:
            # Record phase outcome and check for anomalies
            alerts = self.anomaly_detector.record_phase_outcome(
                phase_id=phase_id,
                phase_type=phase_type or "unknown",
                success=(outcome == "SUCCESS"),
                tokens_used=tokens_used,
                duration_seconds=duration_seconds,
            )

            if alerts:
                logger.info(
                    f"[IMP-TEL-004] Phase {phase_id}: {len(alerts)} anomaly alert(s) detected"
                )

                # Route each alert through the alert router
                if self.alert_router:
                    for alert in alerts:
                        # Inject run_id into alert for persistence context
                        self.alert_router.route_alert(alert, run_id=run_id)
                else:
                    # Fallback logging if no router configured
                    for alert in alerts:
                        logger.warning(
                            f"[IMP-TEL-004] Unrouted alert: {alert.severity.value} - "
                            f"{alert.metric}: {alert.current_value} (threshold: {alert.threshold})"
                        )

        except Exception as e:
            # Don't let anomaly detection failures break phase execution
            logger.warning(f"[IMP-TEL-004] Anomaly detection failed for {phase_id}: {e}")

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


# =========================================================================
# IMP-LOOP-004: Generated Task Execution Handler
# =========================================================================


class GeneratedTaskHandler:
    """Handler for executing generated improvement tasks (IMP-LOOP-004).

    This class provides the execution logic for tasks generated by the ROAD-C
    AutonomousTaskGenerator. It closes the autonomous improvement loop by:

    1. Converting GeneratedTask metadata into executable phase specifications
    2. Executing the task using the standard Builder/Auditor pipeline
    3. Updating task status (completed/failed) based on execution outcome
    4. Recording telemetry for self-improvement feedback

    The handler is invoked via the "generated-task-execution" phase type
    registered in SPECIAL_PHASE_METHODS.
    """

    def __init__(self, executor: Any):
        """Initialize the handler with an executor reference.

        Args:
            executor: AutonomousExecutor instance for phase execution
        """
        self.executor = executor
        self.logger = logging.getLogger(__name__)

    def execute_generated_task_batched(
        self,
        phase: Dict,
        **kwargs,
    ) -> Tuple[bool, str]:
        """Execute a generated improvement task as a phase (IMP-LOOP-004).

        This method:
        1. Extracts task metadata from the phase spec
        2. Converts the task into an executable phase specification
        3. Delegates execution to the standard phase pipeline
        4. Updates task status based on execution result

        Args:
            phase: Phase spec dict containing _generated_task metadata
            **kwargs: Additional execution parameters (memory_context, etc.)

        Returns:
            Tuple of (success: bool, status: str)
        """
        task_metadata = phase.get("_generated_task", {})
        task_id = task_metadata.get("task_id", "unknown")

        self.logger.info(
            f"[IMP-LOOP-004] Executing generated task {task_id}: {task_metadata.get('title', 'Unknown')}"
        )

        # Build an executable phase spec from the task metadata
        executable_phase = self._build_executable_phase(phase, task_metadata)

        try:
            # Execute the phase using the standard pipeline
            # Delegate to the normal builder/auditor flow
            success, status = self._execute_task_phase(executable_phase, **kwargs)

            # Update task status in database
            self._update_task_status(task_id, success, status)

            # Record telemetry
            self._record_task_execution_telemetry(
                task_id=task_id,
                task_metadata=task_metadata,
                success=success,
                status=status,
            )

            if success:
                self.logger.info(f"[IMP-LOOP-004] Generated task {task_id} completed successfully")
            else:
                self.logger.warning(
                    f"[IMP-LOOP-004] Generated task {task_id} failed with status: {status}"
                )

            return success, status

        except Exception as e:
            self.logger.error(f"[IMP-LOOP-004] Generated task {task_id} raised exception: {e}")
            self._update_task_status(
                task_id, success=False, status=f"EXCEPTION: {type(e).__name__}"
            )
            return False, f"EXCEPTION: {type(e).__name__}"

    def _build_executable_phase(self, phase: Dict, task_metadata: Dict) -> Dict:
        """Build an executable phase specification from task metadata.

        Converts the GeneratedTask metadata into a standard phase spec that
        can be executed by the Builder/Auditor pipeline.

        Args:
            phase: Original phase spec with _generated_task metadata
            task_metadata: Extracted task metadata dict

        Returns:
            Modified phase spec ready for execution
        """
        # Create a copy to avoid mutating the original
        executable_phase = dict(phase)

        # Set standard phase fields from task metadata
        executable_phase["description"] = (
            f"## Auto-Generated Improvement Task\n\n"
            f"**Task ID:** {task_metadata.get('task_id', 'unknown')}\n"
            f"**Priority:** {task_metadata.get('priority', 'medium')}\n"
            f"**Estimated Effort:** {task_metadata.get('estimated_effort', 'M')}\n\n"
            f"### Problem\n{task_metadata.get('description', 'No description provided')}\n\n"
            f"### Suggested Files\n"
            f"{chr(10).join('- ' + f for f in task_metadata.get('suggested_files', []))}\n\n"
            f"### Source Insights\n"
            f"{chr(10).join('- ' + s for s in task_metadata.get('source_insights', []))}\n"
        )

        # Ensure scope includes suggested files
        scope = executable_phase.get("scope", {})
        suggested_files = task_metadata.get("suggested_files", [])
        if suggested_files:
            existing_paths = scope.get("paths", [])
            # Merge suggested files with existing scope
            scope["paths"] = list(set(existing_paths + suggested_files))
            executable_phase["scope"] = scope

        # Set category for token budget allocation
        executable_phase["category"] = "improvement"

        # Set complexity based on estimated effort
        effort_to_complexity = {
            "S": "simple",
            "M": "moderate",
            "L": "complex",
            "XL": "very_complex",
        }
        effort = task_metadata.get("estimated_effort", "M")
        executable_phase["complexity"] = effort_to_complexity.get(effort, "moderate")

        return executable_phase

    def _execute_task_phase(self, phase: Dict, **kwargs) -> Tuple[bool, str]:
        """Execute the task phase using the standard pipeline.

        Delegates to the executor's normal phase execution logic, which
        includes Builder invocation, Auditor review, and CI validation.

        Args:
            phase: Executable phase specification
            **kwargs: Additional execution parameters

        Returns:
            Tuple of (success: bool, status: str)
        """
        # Use the executor's standard phase execution
        # This may need to be adapted based on actual executor API
        if hasattr(self.executor, "_execute_standard_phase"):
            return self.executor._execute_standard_phase(phase, **kwargs)
        elif hasattr(self.executor, "execute_phase"):
            return self.executor.execute_phase(phase, **kwargs)
        else:
            # Fallback: try to use builder orchestration directly
            try:
                from autopack.executor.attempt_runner import run_single_attempt_with_recovery

                # Create a minimal executor context
                class MinimalExecutor:
                    def __init__(self, executor):
                        self.run_id = executor.run_id
                        self.llm_service = getattr(executor, "llm_service", None)

                minimal_executor = MinimalExecutor(self.executor)
                result = run_single_attempt_with_recovery(
                    executor=minimal_executor,
                    phase=phase,
                    attempt_index=0,
                    allowed_paths=phase.get("scope", {}).get("paths", []),
                    memory_context=kwargs.get("memory_context"),
                )
                return result.success, result.status
            except Exception as e:
                self.logger.error(f"[IMP-LOOP-004] Task phase execution failed: {e}")
                return False, f"EXECUTION_ERROR: {e}"

    def _update_task_status(self, task_id: str, success: bool, status: str) -> None:
        """Update the task status in the database.

        Marks the task as "completed" on success or "failed" on failure,
        closing the task lifecycle in the self-improvement loop.

        Args:
            task_id: ID of the task to update
            success: Whether execution succeeded
            status: Final execution status string
        """
        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(db_session=db_session)

            new_status = "completed" if success else "failed"
            run_id = getattr(self.executor, "run_id", None)

            updated = generator.mark_task_status(
                task_id=task_id,
                status=new_status,
                executed_in_run_id=run_id,
            )

            if updated:
                self.logger.info(f"[IMP-LOOP-004] Task {task_id} status updated to {new_status}")
            else:
                self.logger.warning(
                    f"[IMP-LOOP-004] Failed to update task {task_id} status (task not found)"
                )

        except Exception as e:
            self.logger.warning(f"[IMP-LOOP-004] Failed to update task status: {e}")

    def _record_task_execution_telemetry(
        self,
        task_id: str,
        task_metadata: Dict,
        success: bool,
        status: str,
    ) -> None:
        """Record telemetry for task execution (IMP-LOOP-004).

        Captures execution metrics for monitoring and analysis of the
        self-improvement loop effectiveness.

        Args:
            task_id: Task identifier
            task_metadata: Task metadata dict
            success: Execution success flag
            status: Final status string
        """
        if os.getenv("TELEMETRY_DB_ENABLED", "false").lower() != "true":
            return

        try:
            from autopack.models import GeneratedTaskExecutionEvent
            from autopack.database import SessionLocal
            from datetime import datetime, timezone

            db = SessionLocal()
            try:
                event = GeneratedTaskExecutionEvent(
                    task_id=task_id,
                    run_id=getattr(self.executor, "run_id", None),
                    task_title=task_metadata.get("title"),
                    task_priority=task_metadata.get("priority"),
                    estimated_effort=task_metadata.get("estimated_effort"),
                    execution_success=success,
                    execution_status=status,
                    timestamp=datetime.now(timezone.utc),
                )
                db.add(event)
                db.commit()
                self.logger.debug(f"[IMP-LOOP-004] Recorded task execution telemetry for {task_id}")
            finally:
                db.close()
        except ImportError:
            # Model not available - skip telemetry
            self.logger.debug("[IMP-LOOP-004] GeneratedTaskExecutionEvent model not available")
        except Exception as e:
            self.logger.warning(f"[IMP-LOOP-004] Failed to record task telemetry: {e}")


def execute_generated_task_batched(
    executor: Any,
    phase: Dict,
    **kwargs,
) -> Tuple[bool, str]:
    """Execute a generated improvement task (IMP-LOOP-004).

    This is the entry point function called by the executor when a
    "generated-task-execution" phase type is encountered.

    Args:
        executor: AutonomousExecutor instance
        phase: Phase spec dict containing _generated_task metadata
        **kwargs: Additional execution parameters

    Returns:
        Tuple of (success: bool, status: str)
    """
    handler = GeneratedTaskHandler(executor)
    return handler.execute_generated_task_batched(phase, **kwargs)


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
