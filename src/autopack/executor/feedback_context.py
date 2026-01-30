"""Feedback context retrieval for autonomous execution loop.

Extracted from autonomous_loop.py as part of IMP-MAINT-002.
Handles retrieval and processing of feedback pipeline context for phases.
"""

import logging
import time
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor
    from autopack.feedback_pipeline import FeedbackPipeline

from autopack.feedback_pipeline import PhaseOutcome

logger = logging.getLogger(__name__)


class FeedbackContextRetriever:
    """Handles feedback context retrieval for phase execution.

    IMP-MAINT-002: Extracted from AutonomousLoop to improve maintainability.
    Encapsulates logic for retrieving relevant feedback pipeline context
    and processing phase outcomes through the feedback pipeline.

    Responsibilities:
    1. Retrieve context for upcoming phase execution
    2. Process phase outcomes through the feedback pipeline
    3. Extract relevant insights, errors, and success patterns
    """

    def __init__(
        self,
        feedback_pipeline: Optional["FeedbackPipeline"],
        feedback_pipeline_enabled: bool = True,
    ):
        """Initialize the FeedbackContextRetriever.

        Args:
            feedback_pipeline: FeedbackPipeline instance for context retrieval
            feedback_pipeline_enabled: Whether feedback pipeline is enabled
        """
        self._feedback_pipeline = feedback_pipeline
        self._feedback_pipeline_enabled = feedback_pipeline_enabled

    @property
    def feedback_pipeline(self) -> Optional["FeedbackPipeline"]:
        """Get the feedback pipeline instance."""
        return self._feedback_pipeline

    @feedback_pipeline.setter
    def feedback_pipeline(self, value: Optional["FeedbackPipeline"]) -> None:
        """Set the feedback pipeline instance."""
        self._feedback_pipeline = value

    def get_context_for_phase(
        self,
        phase_type: Optional[str],
        phase_goal: Optional[str],
    ) -> str:
        """Get relevant feedback pipeline context for the current phase.

        IMP-LOOP-001: Uses the unified FeedbackPipeline to retrieve relevant
        context (insights, errors, patterns) for the current phase type and goal.

        Args:
            phase_type: Type of the phase being executed
            phase_goal: Goal/description of the phase

        Returns:
            Formatted context string for prompt injection
        """
        if not self._feedback_pipeline_enabled or self._feedback_pipeline is None:
            return ""

        try:
            context = self._feedback_pipeline.get_context_for_phase(
                phase_type=phase_type,
                phase_goal=phase_goal,
                max_insights=5,
                max_age_hours=72.0,
                include_errors=True,
                include_success_patterns=True,
            )

            if context.formatted_context:
                logger.info(
                    f"[IMP-LOOP-001] Retrieved feedback pipeline context "
                    f"(insights={len(context.relevant_insights)}, "
                    f"errors={len(context.similar_errors)}, "
                    f"patterns={len(context.success_patterns)})"
                )

            return context.formatted_context

        except Exception as e:
            logger.warning(f"[IMP-LOOP-001] Failed to get feedback pipeline context: {e}")
            return ""

    def process_phase_outcome(
        self,
        phase: Dict,
        success: bool,
        status: str,
        execution_start_time: float,
        executor: "AutonomousExecutor",
    ) -> None:
        """Process phase outcome through the feedback pipeline.

        IMP-LOOP-001: Uses the unified FeedbackPipeline to capture and persist
        phase execution feedback for the self-improvement loop.

        Args:
            phase: Phase dictionary with execution details
            success: Whether the phase executed successfully
            status: Final status string from execution
            execution_start_time: Unix timestamp when execution started
            executor: AutonomousExecutor instance for context extraction
        """
        if not self._feedback_pipeline_enabled or self._feedback_pipeline is None:
            return

        try:
            phase_id = phase.get("phase_id", "unknown")
            phase_type = phase.get("phase_type")
            run_id = getattr(executor, "run_id", "unknown")
            project_id = getattr(executor, "_get_project_slug", lambda: "default")()

            # Calculate execution time
            execution_time = time.time() - execution_start_time

            # Get tokens used (approximate)
            tokens_used = getattr(executor, "_run_tokens_used", 0)

            # Build error message for failures
            error_message = None
            if not success:
                error_message = f"Phase failed with status: {status}"
                phase_result = getattr(executor, "_last_phase_result", None)
                if phase_result and isinstance(phase_result, dict):
                    error_detail = phase_result.get("error") or phase_result.get("message")
                    if error_detail:
                        error_message = f"{error_message}. Detail: {error_detail}"

            # Create PhaseOutcome
            outcome = PhaseOutcome(
                phase_id=phase_id,
                phase_type=phase_type,
                success=success,
                status=status,
                execution_time_seconds=execution_time,
                tokens_used=tokens_used,
                error_message=error_message,
                run_id=run_id,
                project_id=project_id,
            )

            # Process through feedback pipeline
            result = self._feedback_pipeline.process_phase_outcome(outcome)

            if result.get("success"):
                logger.debug(
                    f"[IMP-LOOP-001] Processed phase {phase_id} through feedback pipeline "
                    f"(insights={result.get('insights_created', 0)})"
                )

        except Exception as e:
            logger.warning(f"[IMP-LOOP-001] Failed to process phase through feedback pipeline: {e}")
