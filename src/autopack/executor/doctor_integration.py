"""
Doctor Integration Module

Extracted from autonomous_executor.py to manage Doctor invocation with budget tracking.
The Doctor is an LLM-based diagnostic agent that analyzes phase failures and recommends
recovery actions (retry with hint, replan, skip, etc.).

Key responsibilities:
- Determine when to invoke Doctor based on failure patterns
- Track per-phase and run-level Doctor call budgets
- Invoke Doctor with appropriate context
- Handle Doctor's recommended actions
- Record telemetry and decision metadata

Related modules:
- phase_orchestrator.py: Main execution orchestrator that uses Doctor
- replan_trigger.py: Handles replan actions recommended by Doctor
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List, Any, Set
import logging
import os

logger = logging.getLogger(__name__)

# Import Doctor types and constants
try:
    from autopack.doctor import (
        DoctorRequest,
        DoctorResponse,
        DoctorContextSummary,
        DOCTOR_MIN_BUILDER_ATTEMPTS,
        DOCTOR_HEALTH_BUDGET_NEAR_LIMIT_RATIO,
    )
except ImportError:
    # Fallback if doctor module doesn't exist yet
    logger.warning("Could not import doctor module, using fallback constants")
    DOCTOR_MIN_BUILDER_ATTEMPTS = 2
    DOCTOR_HEALTH_BUDGET_NEAR_LIMIT_RATIO = 0.7

    @dataclass
    class DoctorRequest:
        phase_id: str
        error_category: str
        builder_attempts: int
        health_budget: Dict[str, int]
        last_patch: Optional[str] = None
        patch_errors: Optional[List[Dict]] = None
        logs_excerpt: str = ""
        run_id: str = ""

    @dataclass
    class DoctorResponse:
        action: str
        rationale: str
        builder_hint: Optional[str] = None
        confidence: float = 0.0
        disable_providers: Optional[List[str]] = None

    @dataclass
    class DoctorContextSummary:
        distinct_error_categories_for_phase: int
        prior_doctor_action: Optional[str] = None
        prior_doctor_confidence: Optional[float] = None


class DoctorIntegration:
    """
    Manages Doctor invocation with budget tracking.

    Per GPT_RESPONSE8: Doctor is invoked after DOCTOR_MIN_BUILDER_ATTEMPTS failures
    with guardrails on per-phase and run-level call limits.
    """

    def __init__(
        self,
        max_doctor_calls_per_phase: int = 2,
        max_doctor_calls_per_run: int = 10,
        max_doctor_strong_calls_per_run: int = 5,
        max_doctor_infra_calls_per_run: int = 3,
    ):
        """
        Initialize Doctor integration.

        Args:
            max_doctor_calls_per_phase: Maximum Doctor calls per (run, phase) pair
            max_doctor_calls_per_run: Maximum total Doctor calls for the run
            max_doctor_strong_calls_per_run: Maximum strong-model Doctor calls
            max_doctor_infra_calls_per_run: Maximum infra-error Doctor calls
        """
        self.max_doctor_calls_per_phase = max_doctor_calls_per_phase
        self.max_doctor_calls_per_run = max_doctor_calls_per_run
        self.max_doctor_strong_calls_per_run = max_doctor_strong_calls_per_run
        self.max_doctor_infra_calls_per_run = max_doctor_infra_calls_per_run

    def should_invoke_doctor(
        self,
        phase_id: str,
        builder_attempts: int,
        error_category: str,
        health_budget: Dict[str, int],
        doctor_calls_by_phase: Dict[str, int],
        run_doctor_calls: int,
        run_doctor_infra_calls: int = 0,
        run_id: str = "",
        get_phase_from_db: Optional[Any] = None,
    ) -> bool:
        """
        Determine if Doctor should be invoked for this failure.

        Per GPT_RESPONSE8 Section 4 (Guardrails):
        - Only invoke after DOCTOR_MIN_BUILDER_ATTEMPTS failures
        - Respect per-phase and run-level Doctor call limits
        - Invoke when health budget is near limit

        Args:
            phase_id: Phase identifier
            builder_attempts: Number of builder attempts so far
            error_category: Category of the current error
            health_budget: Current health budget state
            doctor_calls_by_phase: Per-(run,phase) Doctor call count
            run_doctor_calls: Run-level total Doctor calls
            run_doctor_infra_calls: Run-level infra-error Doctor calls
            run_id: Run identifier for phase key
            get_phase_from_db: Optional callable to get phase DB state

        Returns:
            True if Doctor should be invoked
        """
        # DBG-014 / BUILD-049 coordination: deliverables validation failures are tactical
        # path-correction problems that should be handled by deliverables validator + learning hints.
        # Defer Doctor until we've exhausted the normal retry budget.
        if error_category == "deliverables_validation_failed" and get_phase_from_db:
            try:
                phase_db = get_phase_from_db(phase_id)
                max_attempts = getattr(phase_db, "max_builder_attempts", None) if phase_db else None
                if (
                    isinstance(max_attempts, int)
                    and max_attempts > 0
                    and builder_attempts < max_attempts
                ):
                    logger.info(
                        f"[Doctor] Deferring for deliverables validation failure "
                        f"(attempt {builder_attempts}/{max_attempts}) - allowing learning hints to converge"
                    )
                    return False
            except Exception as e:
                # Best-effort safety: if DB read fails, still avoid Doctor on deliverables failures.
                logger.warning(f"[Doctor] Failed to read phase max attempts for {phase_id}: {e}")
                return False

        is_infra = error_category == "infra_error"

        # Check minimum builder attempts (only for non-infra failures)
        if not is_infra and builder_attempts < DOCTOR_MIN_BUILDER_ATTEMPTS:
            logger.debug(
                f"[Doctor] Not invoking: builder_attempts={builder_attempts} < {DOCTOR_MIN_BUILDER_ATTEMPTS}"
            )
            return False

        # Check per-(run, phase) Doctor call limit
        phase_key = f"{run_id}:{phase_id}" if run_id else phase_id
        phase_doctor_calls = doctor_calls_by_phase.get(phase_key, 0)
        if phase_doctor_calls >= self.max_doctor_calls_per_phase:
            logger.info(
                f"[Doctor] Not invoking: per-phase limit reached "
                f"({phase_doctor_calls}/{self.max_doctor_calls_per_phase})"
            )
            return False

        # Check run-level Doctor call limit (overall)
        if run_doctor_calls >= self.max_doctor_calls_per_run:
            logger.info(
                f"[Doctor] Not invoking: run-level limit reached "
                f"({run_doctor_calls}/{self.max_doctor_calls_per_run})"
            )
            return False

        # Additional cap for infra-related diagnostics
        if is_infra and run_doctor_infra_calls >= self.max_doctor_infra_calls_per_run:
            logger.info(
                f"[Doctor] Not invoking: run-level infra limit reached "
                f"({run_doctor_infra_calls}/{self.max_doctor_infra_calls_per_run})"
            )
            return False

        # Check health budget - invoke Doctor if near limit
        total_failures = health_budget.get("total_failures", 0)
        max_total_failures = health_budget.get("max_total_failures", 1)
        health_ratio = total_failures / max(max_total_failures, 1)
        if health_ratio >= DOCTOR_HEALTH_BUDGET_NEAR_LIMIT_RATIO:
            logger.info(f"[Doctor] Health budget near limit ({health_ratio:.2f}), invoking Doctor")
            return True

        # Default: invoke Doctor for diagnosis
        return True

    def build_doctor_context(
        self,
        phase_id: str,
        error_category: str,
        run_id: str,
        distinct_error_cats_by_phase: Dict[str, Set[str]],
        last_doctor_response_by_phase: Dict[str, DoctorResponse],
    ) -> DoctorContextSummary:
        """
        Build Doctor context summary for model routing decisions.

        Per GPT_RESPONSE8 Section 2.1: Per-phase Doctor context tracking.

        Args:
            phase_id: Phase identifier
            error_category: Current error category
            run_id: Run identifier
            distinct_error_cats_by_phase: Distinct error categories seen per phase
            last_doctor_response_by_phase: Last Doctor response per phase

        Returns:
            DoctorContextSummary for model selection
        """
        # Track distinct error categories for this (run, phase)
        phase_key = f"{run_id}:{phase_id}"
        if phase_key not in distinct_error_cats_by_phase:
            distinct_error_cats_by_phase[phase_key] = set()
        distinct_error_cats_by_phase[phase_key].add(error_category)

        # Get prior Doctor response if any
        prior_response = last_doctor_response_by_phase.get(phase_key)
        prior_action = prior_response.action if prior_response else None
        prior_confidence = prior_response.confidence if prior_response else None

        return DoctorContextSummary(
            distinct_error_categories_for_phase=len(distinct_error_cats_by_phase[phase_key]),
            prior_doctor_action=prior_action,
            prior_doctor_confidence=prior_confidence,
        )

    def invoke_doctor(
        self,
        phase: Dict,
        error_category: str,
        builder_attempts: int,
        last_patch: Optional[str],
        patch_errors: List[Dict],
        logs_excerpt: str,
        llm_service: Any,
        run_id: str,
        doctor_calls_by_phase: Dict[str, int],
        run_doctor_calls: int,
        intention_injector: Optional[Any] = None,
        health_budget: Optional[Dict[str, int]] = None,
        distinct_error_cats_by_phase: Optional[Dict[str, Set[str]]] = None,
        last_doctor_response_by_phase: Optional[Dict[str, DoctorResponse]] = None,
        run_doctor_infra_calls: int = 0,
        get_phase_from_db: Optional[Any] = None,
    ) -> Optional[DoctorResponse]:
        """
        Invoke the Autopack Doctor to diagnose a phase failure.

        Per GPT_RESPONSE8 Section 3: Doctor invocation flow.

        Args:
            phase: Phase specification
            error_category: Category of the current error
            builder_attempts: Number of builder attempts so far
            last_patch: Last patch content (if any)
            patch_errors: Patch validation errors (if any)
            logs_excerpt: Relevant log excerpt
            llm_service: LLM service for Doctor invocation
            run_id: Run identifier
            doctor_calls_by_phase: Per-(run,phase) Doctor call tracking
            run_doctor_calls: Run-level Doctor call count
            intention_injector: Optional intention context injector (BUILD-146 P6.2)
            health_budget: Health budget state
            distinct_error_cats_by_phase: Error category tracking
            last_doctor_response_by_phase: Last Doctor response tracking
            run_doctor_infra_calls: Run-level infra-error Doctor calls
            get_phase_from_db: Optional callable to get phase DB state

        Returns:
            DoctorResponse if Doctor was invoked, None otherwise
        """
        phase_id = phase.get("phase_id")
        phase_key = f"{run_id}:{phase_id}"

        # Check if we should invoke Doctor
        if not self.should_invoke_doctor(
            phase_id=phase_id,
            builder_attempts=builder_attempts,
            error_category=error_category,
            health_budget=health_budget or {},
            doctor_calls_by_phase=doctor_calls_by_phase,
            run_doctor_calls=run_doctor_calls,
            run_doctor_infra_calls=run_doctor_infra_calls,
            run_id=run_id,
            get_phase_from_db=get_phase_from_db,
        ):
            return None

        # Check LlmService availability
        if not llm_service:
            logger.warning("[Doctor] LlmService not available, skipping Doctor invocation")
            return None

        # [BUILD-146 P6.2] Add intention context to Doctor logs_excerpt
        doctor_logs_excerpt = logs_excerpt
        if os.getenv("AUTOPACK_ENABLE_INTENTION_CONTEXT", "false").lower() == "true":
            try:
                if intention_injector:
                    intention_reminder = intention_injector.get_intention_context(max_chars=512)
                    if intention_reminder:
                        doctor_logs_excerpt = f"[Project Intention]\n{intention_reminder}\n\n[Error Context]\n{logs_excerpt}"
                        logger.debug(f"[{phase_id}] Added intention reminder to Doctor context")
            except Exception as e:
                logger.warning(f"[{phase_id}] Failed to add intention to Doctor logs: {e}")

        # Build request
        request = DoctorRequest(
            phase_id=phase_id,
            error_category=error_category,
            builder_attempts=builder_attempts,
            health_budget=health_budget or {},
            last_patch=last_patch,
            patch_errors=patch_errors or [],
            logs_excerpt=doctor_logs_excerpt,
            run_id=run_id,
        )

        # Build context summary
        ctx_summary = self.build_doctor_context(
            phase_id=phase_id,
            error_category=error_category,
            run_id=run_id,
            distinct_error_cats_by_phase=distinct_error_cats_by_phase or {},
            last_doctor_response_by_phase=last_doctor_response_by_phase or {},
        )

        try:
            # Invoke Doctor via LlmService
            response = llm_service.execute_doctor(
                request=request,
                ctx_summary=ctx_summary,
                run_id=run_id,
                phase_id=phase_id,
                allow_escalation=True,
            )

            # Update tracking (per run+phase key)
            doctor_calls_by_phase[phase_key] = doctor_calls_by_phase.get(phase_key, 0) + 1

            logger.info(
                f"[Doctor] Diagnosis complete: action={response.action}, "
                f"confidence={response.confidence:.2f}, phase_calls={doctor_calls_by_phase[phase_key]}, "
                f"run_calls={run_doctor_calls + 1}"
            )

            return response

        except Exception as e:
            logger.error(f"[Doctor] Invocation failed: {e}")
            return None

    def record_doctor_outcome(
        self,
        run_id: str,
        phase_id: str,
        error_category: str,
        builder_attempts: int,
        doctor_response: DoctorResponse,
        recommendation_followed: bool = True,
        phase_succeeded: Optional[bool] = None,
        attempts_after_doctor: Optional[int] = None,
        final_outcome: Optional[str] = None,
        doctor_tokens_used: Optional[int] = None,
        model_used: Optional[str] = None,
    ):
        """Record Doctor outcome telemetry (IMP-DOCTOR-002).

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            error_category: Error category that triggered Doctor
            builder_attempts: Builder attempts before Doctor was called
            doctor_response: Doctor's response
            recommendation_followed: Whether Doctor's recommendation was followed
            phase_succeeded: Whether phase succeeded after Doctor (None if still in progress)
            attempts_after_doctor: Additional attempts after Doctor
            final_outcome: Final phase outcome ("COMPLETE", "FAILED", etc.)
            doctor_tokens_used: Tokens used by Doctor call
            model_used: Model used for Doctor invocation
        """
        if os.getenv("TELEMETRY_DB_ENABLED", "false").lower() != "true":
            return

        try:
            from autopack.models import DoctorOutcomeEvent
            from autopack.database import SessionLocal

            db = SessionLocal()
            try:
                event = DoctorOutcomeEvent(
                    run_id=run_id,
                    phase_id=phase_id,
                    error_category=error_category,
                    builder_attempts=builder_attempts,
                    doctor_action=doctor_response.action,
                    doctor_rationale=doctor_response.rationale,
                    doctor_confidence=doctor_response.confidence,
                    builder_hint_provided=bool(doctor_response.builder_hint),
                    recommendation_followed=recommendation_followed,
                    phase_succeeded_after_doctor=phase_succeeded,
                    attempts_after_doctor=attempts_after_doctor,
                    final_phase_outcome=final_outcome,
                    doctor_tokens_used=doctor_tokens_used,
                    model_used=model_used,
                )
                db.add(event)
                db.commit()
                logger.debug(
                    f"[IMP-DOCTOR-002] Recorded Doctor outcome: {phase_id} -> {doctor_response.action}"
                )
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[IMP-DOCTOR-002] Failed to record Doctor outcome: {e}")

    def update_doctor_outcome(
        self,
        run_id: str,
        phase_id: str,
        phase_succeeded: bool,
        final_outcome: str,
        attempts_after_doctor: int,
    ):
        """Update Doctor outcome with final phase result (IMP-DOCTOR-002).

        Called after phase completes to record whether Doctor's intervention was successful.

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            phase_succeeded: Whether phase succeeded
            final_outcome: Final phase status ("COMPLETE", "FAILED", etc.)
            attempts_after_doctor: Number of attempts after Doctor intervention
        """
        if os.getenv("TELEMETRY_DB_ENABLED", "false").lower() != "true":
            return

        try:
            from autopack.models import DoctorOutcomeEvent
            from autopack.database import SessionLocal
            from sqlalchemy import desc

            db = SessionLocal()
            try:
                # Find most recent Doctor outcome for this phase
                event = (
                    db.query(DoctorOutcomeEvent)
                    .filter(
                        DoctorOutcomeEvent.run_id == run_id,
                        DoctorOutcomeEvent.phase_id == phase_id,
                    )
                    .order_by(desc(DoctorOutcomeEvent.timestamp))
                    .first()
                )

                if event and event.phase_succeeded_after_doctor is None:
                    # Update with final outcome
                    event.phase_succeeded_after_doctor = phase_succeeded
                    event.final_phase_outcome = final_outcome
                    event.attempts_after_doctor = attempts_after_doctor
                    db.commit()
                    logger.debug(
                        f"[IMP-DOCTOR-002] Updated Doctor outcome: {phase_id} -> success={phase_succeeded}"
                    )
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[IMP-DOCTOR-002] Failed to update Doctor outcome: {e}")

    def handle_doctor_action(
        self,
        phase: Dict,
        response: DoctorResponse,
        attempt_index: int,
        llm_service: Any,
        builder_hint_by_phase: Optional[Dict[str, str]] = None,
        skipped_phases: Optional[Set[str]] = None,
        record_decision_entry: Optional[Any] = None,
    ) -> Tuple[Optional[str], bool]:
        """
        Handle Doctor's recommended action.

        Per GPT_RESPONSE8 Section 3.3: Action handling in executor.

        Args:
            phase: Phase specification
            response: Doctor's response
            attempt_index: Current attempt index
            llm_service: LLM service for provider disabling
            builder_hint_by_phase: Optional builder hint storage
            skipped_phases: Optional skipped phases tracking
            record_decision_entry: Optional decision recording callable

        Returns:
            Tuple of (action_taken: str or None, should_continue_retry: bool)
            - action_taken: What was done ("retry_with_hint", "replan", "skip", "fatal", "rollback")
            - should_continue_retry: Whether to continue the retry loop
        """
        phase_id = phase.get("phase_id")
        action = response.action

        # Apply any provider-level recommendations from Doctor before
        # interpreting the high-level action.
        disable_providers = getattr(response, "disable_providers", None)
        if disable_providers and llm_service:
            for provider in disable_providers:
                try:
                    llm_service.model_router.disable_provider(
                        provider,
                        reason=f"Doctor recommendation for phase {phase_id}",
                    )
                except Exception as e:
                    logger.warning(f"[Doctor] Failed to disable provider {provider}: {e}")

        if action == "retry_with_fix":
            # Doctor has a hint for the next Builder attempt
            hint = response.builder_hint or "Review previous errors and try a different approach"
            if builder_hint_by_phase is not None:
                builder_hint_by_phase[phase_id] = hint

            logger.info("[Doctor] Action: retry_with_fix - hint stored for next attempt")

            if record_decision_entry:
                record_decision_entry(
                    trigger="doctor",
                    choice="retry_with_fix",
                    rationale=response.rationale,
                    phase_id=phase_id,
                    alternatives="retry_with_fix,replan,skip,rollback",
                )

            return "retry_with_hint", True  # Continue retry loop with hint

        elif action == "replan":
            # Trigger mid-run re-planning
            logger.info("[Doctor] Action: replan - triggering approach revision")
            # The orchestrator will handle the actual replan logic
            return "replan", True

        elif action == "skip_phase":
            # Skip this phase and continue to next
            logger.info("[Doctor] Action: skip_phase - marking phase as FAILED and continuing")

            if skipped_phases is not None:
                skipped_phases.add(phase_id)

            if record_decision_entry:
                record_decision_entry(
                    trigger="doctor",
                    choice="skip_phase",
                    rationale=response.rationale,
                    phase_id=phase_id,
                    alternatives="retry_with_fix,replan,skip,rollback",
                )

            return "skip", False  # Exit retry loop

        elif action == "mark_fatal":
            # Unrecoverable error - human intervention required
            logger.critical(
                f"[Doctor] Action: mark_fatal - phase {phase_id} requires human intervention. "
                f"Rationale: {response.rationale}"
            )

            # Log to debug journal
            try:
                from autopack.debug_journal import log_error

                log_error(
                    error_signature=f"Doctor FATAL: {phase_id}",
                    symptom=response.rationale,
                    run_id="",  # Would need run_id passed in
                    phase_id=phase_id,
                    suspected_cause="Doctor diagnosed unrecoverable failure",
                    priority="CRITICAL",
                )
            except Exception as e:
                logger.warning(f"[Doctor] Failed to log fatal error to debug journal: {e}")

            if record_decision_entry:
                record_decision_entry(
                    trigger="doctor",
                    choice="mark_fatal",
                    rationale=response.rationale,
                    phase_id=phase_id,
                    alternatives="retry_with_fix,replan,skip,rollback",
                )

            return "fatal", False  # Exit retry loop

        elif action == "rollback_run":
            # Rollback all changes and abort run
            logger.critical(
                f"[Doctor] Action: rollback_run - aborting run. Rationale: {response.rationale}"
            )

            # Log to debug journal
            try:
                from autopack.debug_journal import log_error

                log_error(
                    error_signature="Doctor ROLLBACK",
                    symptom=response.rationale,
                    run_id="",  # Would need run_id passed in
                    phase_id=phase_id,
                    suspected_cause="Doctor recommended run rollback due to accumulated failures",
                    priority="CRITICAL",
                )
            except Exception as e:
                logger.warning(f"[Doctor] Failed to log rollback to debug journal: {e}")

            if record_decision_entry:
                record_decision_entry(
                    trigger="doctor",
                    choice="rollback_run",
                    rationale=response.rationale,
                    phase_id=phase_id,
                    alternatives="retry_with_fix,replan,skip,rollback",
                )

            return "rollback", False  # Exit retry loop

        else:
            # Unknown action - log warning and continue
            logger.warning(f"[Doctor] Unknown action '{action}', continuing with retry")
            return None, True
