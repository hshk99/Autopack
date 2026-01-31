"""Doctor Integration Facade for AutonomousExecutor.

Extracted from autonomous_executor.py as part of IMP-MAINT-001.
Provides a clean interface for Doctor (LLM-based diagnostic agent) invocation
with budget tracking and state management.

Per GPT_RESPONSE8: Doctor is invoked after minimum Builder attempts with
guardrails on per-phase and run-level call limits.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import (TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set,
                    Tuple)

from autopack.debug_journal import log_error
from autopack.error_recovery import (DOCTOR_HEALTH_BUDGET_NEAR_LIMIT_RATIO,
                                     DOCTOR_MIN_BUILDER_ATTEMPTS,
                                     DoctorContextSummary, DoctorRequest,
                                     DoctorResponse)

if TYPE_CHECKING:
    from autopack.llm_service import LlmService

logger = logging.getLogger(__name__)


@dataclass
class DoctorState:
    """Tracks Doctor invocation state across a run.

    Encapsulates all Doctor-related counters and tracking dictionaries.
    """

    # Per-(run, phase) tracking (keyed by f"{run_id}:{phase_id}")
    doctor_calls_by_phase: Dict[str, int] = field(default_factory=dict)
    last_doctor_response_by_phase: Dict[str, DoctorResponse] = field(default_factory=dict)
    doctor_context_by_phase: Dict[str, DoctorContextSummary] = field(default_factory=dict)
    distinct_error_cats_by_phase: Dict[str, Set[str]] = field(default_factory=dict)

    # Run-level counters
    run_doctor_calls: int = 0
    run_doctor_strong_calls: int = 0
    run_doctor_infra_calls: int = 0

    # Builder hints from Doctor
    builder_hint_by_phase: Dict[str, str] = field(default_factory=dict)

    # Skipped phases (from Doctor skip_phase action)
    skipped_phases: Set[str] = field(default_factory=set)


@dataclass
class HealthBudget:
    """Current health budget state for Doctor decisions."""

    http_500: int
    patch_failures: int
    total_failures: int
    total_cap: int


class DoctorFacade:
    """Facade for Doctor invocation with budget tracking.

    Centralizes all Doctor-related operations with proper state management
    and budget guardrails. The Doctor is an LLM-based diagnostic agent that
    analyzes phase failures and recommends recovery actions.

    This facade:
    - Determines when to invoke Doctor based on failure patterns
    - Tracks per-phase and run-level Doctor call budgets
    - Invokes Doctor with appropriate context via LlmService
    - Handles Doctor's recommended actions
    - Records telemetry and decision metadata
    """

    # Default budget limits
    DEFAULT_MAX_DOCTOR_CALLS_PER_PHASE = 2
    DEFAULT_MAX_DOCTOR_CALLS_PER_RUN = 10
    DEFAULT_MAX_DOCTOR_STRONG_CALLS_PER_RUN = 5
    DEFAULT_MAX_DOCTOR_INFRA_CALLS_PER_RUN = 5

    def __init__(
        self,
        run_id: str,
        llm_service: Optional["LlmService"],
        get_health_budget_fn: Callable[[], HealthBudget],
        get_phase_from_db_fn: Callable[[str], Optional[Any]],
        update_phase_status_fn: Callable[[str, str], None],
        record_decision_fn: Callable[..., None],
        revise_phase_approach_fn: Callable[..., Optional[Dict]],
        rollback_to_checkpoint_fn: Callable[[str], Tuple[bool, Optional[str]]],
        execute_fix_handler: Any,
        intention_injector: Optional[Any] = None,
        max_calls_per_phase: int = DEFAULT_MAX_DOCTOR_CALLS_PER_PHASE,
        max_calls_per_run: int = DEFAULT_MAX_DOCTOR_CALLS_PER_RUN,
        max_strong_calls_per_run: int = DEFAULT_MAX_DOCTOR_STRONG_CALLS_PER_RUN,
        max_infra_calls_per_run: int = DEFAULT_MAX_DOCTOR_INFRA_CALLS_PER_RUN,
    ):
        """Initialize Doctor facade.

        Args:
            run_id: Unique run identifier
            llm_service: LLM service for Doctor invocation
            get_health_budget_fn: Callback to get current health budget
            get_phase_from_db_fn: Callback to fetch phase from database
            update_phase_status_fn: Callback to update phase status
            record_decision_fn: Callback to record decision entries
            revise_phase_approach_fn: Callback to revise phase approach
            rollback_to_checkpoint_fn: Callback for run rollback
            execute_fix_handler: Handler for execute_fix actions
            intention_injector: Optional intention context injector
            max_calls_per_phase: Max Doctor calls per phase
            max_calls_per_run: Max total Doctor calls per run
            max_strong_calls_per_run: Max strong-model Doctor calls
            max_infra_calls_per_run: Max infra-related Doctor calls
        """
        self.run_id = run_id
        self.llm_service = llm_service
        self._get_health_budget = get_health_budget_fn
        self._get_phase_from_db = get_phase_from_db_fn
        self._update_phase_status = update_phase_status_fn
        self._record_decision_entry = record_decision_fn
        self._revise_phase_approach = revise_phase_approach_fn
        self._rollback_to_run_checkpoint = rollback_to_checkpoint_fn
        self.execute_fix_handler = execute_fix_handler
        self._intention_injector = intention_injector

        # Budget limits
        self.max_calls_per_phase = max_calls_per_phase
        self.max_calls_per_run = max_calls_per_run
        self.max_strong_calls_per_run = max_strong_calls_per_run
        self.max_infra_calls_per_run = max_infra_calls_per_run

        # State tracking
        self.state = DoctorState()

    def get_health_budget_dict(self) -> Dict[str, int]:
        """Get current health budget as dictionary.

        Returns:
            Health budget with http_500, patch_failures, total_failures, total_cap
        """
        budget = self._get_health_budget()
        return {
            "http_500": budget.http_500,
            "patch_failures": budget.patch_failures,
            "total_failures": budget.total_failures,
            "total_cap": budget.total_cap,
        }

    def should_invoke_doctor(
        self, phase_id: str, builder_attempts: int, error_category: str
    ) -> bool:
        """Determine if Doctor should be invoked for this failure.

        Per GPT_RESPONSE8 Section 4 (Guardrails):
        - Only invoke after DOCTOR_MIN_BUILDER_ATTEMPTS failures
        - Respect per-phase and run-level Doctor call limits
        - Invoke when health budget is near limit

        Args:
            phase_id: Phase identifier
            builder_attempts: Number of builder attempts so far
            error_category: Category of the current error

        Returns:
            True if Doctor should be invoked
        """
        # DBG-014 / BUILD-049: Defer Doctor for deliverables validation failures
        if error_category == "deliverables_validation_failed":
            try:
                phase_db = self._get_phase_from_db(phase_id)
                max_attempts = getattr(phase_db, "max_builder_attempts", None) if phase_db else None
                if (
                    isinstance(max_attempts, int)
                    and max_attempts > 0
                    and builder_attempts < max_attempts
                ):
                    logger.info(
                        f"[Doctor] Deferring for deliverables validation failure "
                        f"(attempt {builder_attempts}/{max_attempts})"
                    )
                    return False
            except Exception as e:
                logger.warning(f"[Doctor] Failed to read phase max attempts: {e}")
                return False

        is_infra = error_category == "infra_error"

        # Check minimum builder attempts (only for non-infra failures)
        if not is_infra and builder_attempts < DOCTOR_MIN_BUILDER_ATTEMPTS:
            logger.debug(
                f"[Doctor] Not invoking: builder_attempts={builder_attempts} "
                f"< {DOCTOR_MIN_BUILDER_ATTEMPTS}"
            )
            return False

        # Check per-(run, phase) Doctor call limit
        phase_key = f"{self.run_id}:{phase_id}"
        phase_doctor_calls = self.state.doctor_calls_by_phase.get(phase_key, 0)
        if phase_doctor_calls >= self.max_calls_per_phase:
            logger.info(
                f"[Doctor] Not invoking: per-phase limit reached "
                f"({phase_doctor_calls}/{self.max_calls_per_phase})"
            )
            return False

        # Check run-level Doctor call limit
        if self.state.run_doctor_calls >= self.max_calls_per_run:
            logger.info(
                f"[Doctor] Not invoking: run-level limit reached "
                f"({self.state.run_doctor_calls}/{self.max_calls_per_run})"
            )
            return False

        # Additional cap for infra-related diagnostics
        if is_infra and self.state.run_doctor_infra_calls >= self.max_infra_calls_per_run:
            logger.info(
                f"[Doctor] Not invoking: run-level infra limit reached "
                f"({self.state.run_doctor_infra_calls}/{self.max_infra_calls_per_run})"
            )
            return False

        # Check health budget - invoke Doctor if near limit
        budget = self._get_health_budget()
        health_ratio = budget.total_failures / max(budget.total_cap, 1)
        if health_ratio >= DOCTOR_HEALTH_BUDGET_NEAR_LIMIT_RATIO:
            logger.info(f"[Doctor] Health budget near limit ({health_ratio:.2f}), invoking Doctor")
            return True

        # Default: invoke Doctor for diagnosis
        return True

    def build_doctor_context(self, phase_id: str, error_category: str) -> DoctorContextSummary:
        """Build Doctor context summary for model routing decisions.

        Per GPT_RESPONSE8 Section 2.1: Per-phase Doctor context tracking.

        Args:
            phase_id: Phase identifier
            error_category: Current error category

        Returns:
            DoctorContextSummary for model selection
        """
        # Track distinct error categories for this (run, phase)
        phase_key = f"{self.run_id}:{phase_id}"
        if phase_key not in self.state.distinct_error_cats_by_phase:
            self.state.distinct_error_cats_by_phase[phase_key] = set()
        self.state.distinct_error_cats_by_phase[phase_key].add(error_category)

        # Get prior Doctor response if any
        prior_response = self.state.last_doctor_response_by_phase.get(phase_key)
        prior_action = prior_response.action if prior_response else None
        prior_confidence = prior_response.confidence if prior_response else None

        return DoctorContextSummary(
            distinct_error_categories_for_phase=len(
                self.state.distinct_error_cats_by_phase[phase_key]
            ),
            prior_doctor_action=prior_action,
            prior_doctor_confidence=prior_confidence,
        )

    def invoke_doctor(
        self,
        phase: Dict[str, Any],
        error_category: str,
        builder_attempts: int,
        last_patch: Optional[str] = None,
        patch_errors: Optional[List[Dict]] = None,
        logs_excerpt: str = "",
    ) -> Optional[DoctorResponse]:
        """Invoke the Doctor to diagnose a phase failure.

        Per GPT_RESPONSE8 Section 3: Doctor invocation flow.

        Args:
            phase: Phase specification
            error_category: Category of the current error
            builder_attempts: Number of builder attempts so far
            last_patch: Last patch content (if any)
            patch_errors: Patch validation errors (if any)
            logs_excerpt: Relevant log excerpt

        Returns:
            DoctorResponse if Doctor was invoked, None otherwise
        """
        phase_id = phase.get("phase_id")
        phase_key = f"{self.run_id}:{phase_id}"

        # Check if we should invoke Doctor
        if not self.should_invoke_doctor(phase_id, builder_attempts, error_category):
            return None

        # Check LlmService availability
        if not self.llm_service:
            logger.warning("[Doctor] LlmService not available, skipping invocation")
            return None

        # Add intention context if enabled
        doctor_logs_excerpt = logs_excerpt
        if os.getenv("AUTOPACK_ENABLE_INTENTION_CONTEXT", "false").lower() == "true":
            try:
                if self._intention_injector:
                    intention_reminder = self._intention_injector.get_intention_context(
                        max_chars=512
                    )
                    if intention_reminder:
                        doctor_logs_excerpt = (
                            f"[Project Intention]\n{intention_reminder}\n\n"
                            f"[Error Context]\n{logs_excerpt}"
                        )
                        logger.debug(f"[{phase_id}] Added intention to Doctor context")
            except Exception as e:
                logger.warning(f"[{phase_id}] Failed to add intention: {e}")

        # Build request
        request = DoctorRequest(
            phase_id=phase_id,
            error_category=error_category,
            builder_attempts=builder_attempts,
            health_budget=self.get_health_budget_dict(),
            last_patch=last_patch,
            patch_errors=patch_errors or [],
            logs_excerpt=doctor_logs_excerpt,
            run_id=self.run_id,
        )

        # Build context summary
        ctx_summary = self.build_doctor_context(phase_id, error_category)

        try:
            # Invoke Doctor via LlmService
            response = self.llm_service.execute_doctor(
                request=request,
                ctx_summary=ctx_summary,
                run_id=self.run_id,
                phase_id=phase_id,
                allow_escalation=True,
            )

            # Update tracking
            self.state.doctor_calls_by_phase[phase_key] = (
                self.state.doctor_calls_by_phase.get(phase_key, 0) + 1
            )
            self.state.run_doctor_calls += 1
            if error_category == "infra_error":
                self.state.run_doctor_infra_calls += 1
            self.state.last_doctor_response_by_phase[phase_key] = response
            self.state.doctor_context_by_phase[phase_key] = ctx_summary

            # Store builder hint if provided
            if response.builder_hint:
                self.state.builder_hint_by_phase[phase_id] = response.builder_hint

            logger.info(
                f"[Doctor] Diagnosis complete: action={response.action}, "
                f"confidence={response.confidence:.2f}, "
                f"phase_calls={self.state.doctor_calls_by_phase[phase_key]}, "
                f"run_calls={self.state.run_doctor_calls}"
            )

            return response

        except Exception as e:
            logger.error(f"[Doctor] Invocation failed: {e}")
            return None

    def handle_doctor_action(
        self,
        phase: Dict[str, Any],
        response: DoctorResponse,
        attempt_index: int,
        phase_error_history: Dict[str, List[Dict]],
    ) -> Tuple[Optional[str], bool]:
        """Handle Doctor's recommended action.

        Per GPT_RESPONSE8 Section 3.3: Action handling in executor.

        Args:
            phase: Phase specification
            response: Doctor's response
            attempt_index: Current attempt index
            phase_error_history: Error history for replanning

        Returns:
            Tuple of (action_taken, should_continue_retry)
        """
        phase_id = phase.get("phase_id")
        action = response.action

        # Apply provider-level recommendations
        disable_providers = getattr(response, "disable_providers", None)
        if disable_providers and self.llm_service:
            for provider in disable_providers:
                try:
                    self.llm_service.model_router.disable_provider(
                        provider,
                        reason=f"Doctor recommendation for phase {phase_id}",
                    )
                except Exception as e:
                    logger.warning(f"[Doctor] Failed to disable provider {provider}: {e}")

        if action == "retry_with_fix":
            hint = response.builder_hint or "Review previous errors and try a different approach"
            self.state.builder_hint_by_phase[phase_id] = hint
            logger.info("[Doctor] Action: retry_with_fix - hint stored")
            self._record_decision_entry(
                trigger="doctor",
                choice="retry_with_fix",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback",
            )
            return "retry_with_hint", True

        elif action == "replan":
            logger.info("[Doctor] Action: replan - triggering approach revision")
            error_history = phase_error_history.get(phase_id, [])
            revised_phase = self._revise_phase_approach(
                phase, f"doctor_replan:{response.rationale[:50]}", error_history
            )
            if revised_phase:
                logger.info("[Doctor] Replan successful, phase revised")
                return "replan", True
            else:
                logger.warning("[Doctor] Replan failed, continuing with original")
                self._record_decision_entry(
                    trigger="doctor",
                    choice="replan_failed",
                    rationale=response.rationale,
                    phase_id=phase_id,
                    alternatives="retry_with_fix,replan,skip,rollback",
                )
                return "replan_failed", True

        elif action == "skip_phase":
            logger.info("[Doctor] Action: skip_phase - marking as FAILED")
            self.state.skipped_phases.add(phase_id)
            self._update_phase_status(phase_id, "FAILED")
            self._record_decision_entry(
                trigger="doctor",
                choice="skip_phase",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback",
            )
            return "skip", False

        elif action == "mark_fatal":
            logger.critical(
                f"[Doctor] Action: mark_fatal - phase {phase_id} requires intervention. "
                f"Rationale: {response.rationale}"
            )
            log_error(
                error_signature=f"Doctor FATAL: {phase_id}",
                symptom=response.rationale,
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="Doctor diagnosed unrecoverable failure",
                priority="CRITICAL",
            )
            self._update_phase_status(phase_id, "FAILED")
            self._record_decision_entry(
                trigger="doctor",
                choice="mark_fatal",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback",
            )
            return "fatal", False

        elif action == "rollback_run":
            logger.critical(
                f"[Doctor] Action: rollback_run - aborting run {self.run_id}. "
                f"Rationale: {response.rationale}"
            )
            log_error(
                error_signature=f"Doctor ROLLBACK: {self.run_id}",
                symptom=response.rationale,
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="Doctor recommended run rollback",
                priority="CRITICAL",
            )

            rollback_success, rollback_error = self._rollback_to_run_checkpoint(
                f"Doctor rollback_run: {response.rationale}"
            )

            if rollback_success:
                logger.info("[Doctor] Successfully rolled back run")
            else:
                logger.error(f"[Doctor] Failed to rollback: {rollback_error}")
                logger.error("[Doctor] Working tree may be inconsistent")

            self._update_phase_status(phase_id, "FAILED")
            self._record_decision_entry(
                trigger="doctor",
                choice="rollback_run",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback",
            )
            return "rollback", False

        elif action == "execute_fix":
            self._record_decision_entry(
                trigger="doctor",
                choice="execute_fix",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback,execute_fix",
            )
            result = self.execute_fix_handler.execute_fix(phase, response)
            return result.action_taken, result.should_continue_retry

        else:
            logger.warning(f"[Doctor] Unknown action: {action}, treating as retry")
            self._record_decision_entry(
                trigger="doctor",
                choice="unknown_action",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback",
            )
            return "unknown", True

    def get_builder_hint_for_phase(self, phase_id: str) -> Optional[str]:
        """Get any Doctor-provided hint for the next Builder attempt.

        Clears the hint after retrieval to avoid stale hints.

        Args:
            phase_id: Phase identifier

        Returns:
            Builder hint if available, None otherwise
        """
        hint = self.state.builder_hint_by_phase.get(phase_id)
        if hint:
            del self.state.builder_hint_by_phase[phase_id]
        return hint

    def get_run_stats(self) -> Dict[str, Any]:
        """Get Doctor invocation statistics for the run.

        Returns:
            Statistics including call counts and skipped phases
        """
        return {
            "run_doctor_calls": self.state.run_doctor_calls,
            "run_doctor_strong_calls": self.state.run_doctor_strong_calls,
            "run_doctor_infra_calls": self.state.run_doctor_infra_calls,
            "skipped_phases_count": len(self.state.skipped_phases),
            "skipped_phases": list(self.state.skipped_phases),
        }
