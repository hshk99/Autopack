"""Context injection helpers for autonomous loop.

IMP-GOD-002: Extracted from autonomous_loop.py to reduce god file size.

Handles memory context retrieval, token estimation, and context ceiling enforcement.
"""

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from autopack.feedback_pipeline import FeedbackPipeline

logger = logging.getLogger(__name__)


class ContextInjectionHelper:
    """Manages context injection for the autonomous loop.

    Handles memory context retrieval, token estimation, and context ceiling
    enforcement to prevent unbounded context accumulation across phases.
    """

    def __init__(
        self,
        context_ceiling: int = 100000,
    ):
        """Initialize context injection helper.

        Args:
            context_ceiling: Maximum context tokens allowed across phases.
        """
        # IMP-PERF-002: Context ceiling tracking
        # Prevents unbounded context injection across phases
        self._total_context_tokens = 0
        self._context_ceiling = context_ceiling

    @property
    def total_context_tokens(self) -> int:
        """Get total context tokens used."""
        return self._total_context_tokens

    @property
    def context_ceiling(self) -> int:
        """Get the context ceiling limit."""
        return self._context_ceiling

    def reset_context_tracking(self) -> None:
        """Reset context token tracking (e.g., at start of new run)."""
        self._total_context_tokens = 0

    def get_memory_context(
        self,
        phase_type: str,
        goal: str,
        project_id: str,
        feedback_pipeline: Optional["FeedbackPipeline"] = None,
    ) -> str:
        """Retrieve memory context for builder injection.

        Queries vector memory for historical context (past errors, successful strategies,
        doctor hints) related to the phase and injects it into the builder prompt.

        Args:
            phase_type: Type of phase (e.g., 'build', 'test', 'deploy')
            goal: Phase goal/description
            project_id: Project identifier for memory queries
            feedback_pipeline: Optional feedback pipeline for promoted rules

        Returns:
            Formatted context string for prompt injection, or empty string if memory disabled
        """
        from autopack.memory.context_injector import ContextInjector

        try:
            injector = ContextInjector()
            # IMP-LOOP-024: Use EnrichedContextInjection for metadata (source, timestamp, freshness)
            injection = injector.get_context_for_phase_with_metadata(
                phase_type=phase_type,
                current_goal=goal,
                project_id=project_id,
                max_tokens=500,
            )

            if injection.total_token_estimate > 0:
                # IMP-LOOP-024: Log enriched context with quality signals
                quality_info = ""
                if injection.has_low_confidence_warning:
                    quality_info = f", LOW_CONFIDENCE avg={injection.avg_confidence:.2f}"
                else:
                    quality_info = f", confidence={injection.avg_confidence:.2f}"

                logger.info(
                    f"[IMP-LOOP-024] Injecting {injection.total_token_estimate} tokens of enriched memory context "
                    f"({len(injection.past_errors)} errors, "
                    f"{len(injection.successful_strategies)} strategies, "
                    f"{len(injection.doctor_hints)} hints, "
                    f"{len(injection.relevant_insights)} insights{quality_info})"
                )

            # IMP-LOOP-024: Use enriched formatting with confidence warnings
            memory_context = injector.format_enriched_for_prompt(injection)

            # IMP-LOOP-025: Retrieve and inject promoted rules into execution context
            # Promoted rules are high-priority patterns that have occurred 3+ times
            if feedback_pipeline is not None:
                try:
                    promoted_rules = feedback_pipeline.get_promoted_rules(
                        phase_type=phase_type, limit=5
                    )
                    if promoted_rules:
                        rules_lines = ["\n\n## Promoted Rules (High-Priority Patterns)"]
                        rules_lines.append(
                            "The following rules were derived from recurring issues:"
                        )
                        for rule in promoted_rules:
                            description = rule.get("description", "")[:200]
                            action = rule.get("suggested_action", "")[:150]
                            occurrences = rule.get("occurrences", 0)
                            rules_lines.append(f"- **Rule** (seen {occurrences}x): {description}")
                            if action:
                                rules_lines.append(f"  → Action: {action}")
                        rules_context = "\n".join(rules_lines)
                        memory_context += rules_context
                        logger.info(
                            f"[IMP-LOOP-025] Injected {len(promoted_rules)} promoted rules "
                            f"into execution context for phase_type={phase_type}"
                        )
                except Exception as rules_err:
                    logger.warning(
                        f"[IMP-LOOP-025] Failed to retrieve promoted rules (non-fatal): {rules_err}"
                    )

            return memory_context
        except Exception as e:
            logger.warning(f"[IMP-ARCH-002] Failed to retrieve memory context: {e}")
            return ""

    def get_improvement_task_context(self, improvement_tasks: List[Dict]) -> str:
        """Get improvement tasks as context for phase execution (IMP-ARCH-019).

        Formats loaded improvement tasks into a context string that guides
        the Builder to address self-improvement opportunities.

        Args:
            improvement_tasks: List of improvement task dictionaries

        Returns:
            Formatted context string, or empty string if no tasks
        """
        # Ensure it's a proper list (not a Mock or other non-list type)
        if not improvement_tasks or not isinstance(improvement_tasks, list):
            return ""

        # Format tasks for injection
        lines = ["## Self-Improvement Tasks (from previous runs)"]
        lines.append("The following improvement opportunities were identified from telemetry:")
        lines.append("")

        for i, task in enumerate(improvement_tasks[:5], 1):  # Limit to 5 tasks
            priority = task.get("priority", "medium")
            title = task.get("title", "Unknown task")
            description = task.get("description", "")[:200]  # Truncate long descriptions
            files = task.get("suggested_files", [])

            lines.append(f"### {i}. [{priority.upper()}] {title}")
            if description:
                lines.append(f"{description}")
            if files:
                lines.append(f"Suggested files: {', '.join(files[:3])}")
            lines.append("")

        lines.append("Consider addressing these issues if relevant to the current phase.")

        context = "\n".join(lines)
        logger.info(
            f"[IMP-ARCH-019] Injecting {len(improvement_tasks)} improvement tasks into phase context"
        )
        return context

    def estimate_tokens(self, context: str) -> int:
        """Estimate token count for a context string.

        Uses a rough heuristic of ~4 characters per token (common for English text).
        This is a fast approximation; actual token counts vary by model and content.

        Args:
            context: The context string to estimate tokens for.

        Returns:
            Estimated token count.
        """
        if not context:
            return 0
        # Rough estimate: ~4 characters per token (typical for English)
        return len(context) // 4

    def truncate_to_budget(self, context: str, token_budget: int) -> str:
        """Truncate context to fit within a token budget.

        Prioritizes keeping the most recent content (end of string).
        Truncates from the beginning to preserve recent context.

        Args:
            context: The context string to truncate.
            token_budget: Maximum tokens allowed.

        Returns:
            Truncated context string that fits within budget.
        """
        if token_budget <= 0:
            return ""

        current_tokens = self.estimate_tokens(context)
        if current_tokens <= token_budget:
            return context

        # Calculate approximate character limit (4 chars per token)
        char_budget = token_budget * 4

        # Truncate from beginning, keeping most recent content
        truncated = context[-char_budget:]

        # Try to find a clean break point (newline or space)
        clean_break = truncated.find("\n")
        if clean_break == -1:
            clean_break = truncated.find(" ")

        if clean_break > 0 and clean_break < len(truncated) // 2:
            truncated = truncated[clean_break + 1 :]

        return truncated

    def inject_context_with_ceiling(self, context: str) -> str:
        """Inject context while enforcing the total context ceiling.

        IMP-PERF-002: Prevents unbounded context accumulation across phases.
        Tracks total context tokens injected and truncates when ceiling is reached.

        Args:
            context: The context string to inject.

        Returns:
            The context string (potentially truncated to fit within ceiling).
        """
        if not context:
            return ""

        context_tokens = self.estimate_tokens(context)

        if self._total_context_tokens + context_tokens > self._context_ceiling:
            remaining_budget = self._context_ceiling - self._total_context_tokens

            if remaining_budget <= 0:
                logger.warning(
                    f"[IMP-PERF-002] Context ceiling reached ({self._context_ceiling} tokens). "
                    f"Skipping context injection entirely."
                )
                return ""

            logger.warning(
                f"[IMP-PERF-002] Context ceiling approaching ({self._total_context_tokens}/{self._context_ceiling} tokens). "
                f"Truncating injection from {context_tokens} to {remaining_budget} tokens."
            )
            # Prioritize most recent context
            context = self.truncate_to_budget(context, remaining_budget)
            context_tokens = self.estimate_tokens(context)

        self._total_context_tokens += context_tokens
        logger.debug(
            f"[IMP-PERF-002] Context injected: {context_tokens} tokens "
            f"(total: {self._total_context_tokens}/{self._context_ceiling})"
        )
        return context

    def combine_contexts(
        self,
        memory_context: str,
        feedback_context: str,
        improvement_context: str,
        phase_id: str,
    ) -> str:
        """Combine all context sources with logging.

        Args:
            memory_context: Context from memory service
            feedback_context: Context from feedback pipeline
            improvement_context: Context from improvement tasks
            phase_id: Phase ID for logging

        Returns:
            Combined context string
        """
        combined_context = ""
        if memory_context:
            combined_context = memory_context
        if feedback_context:
            combined_context = (
                combined_context + "\n\n" + feedback_context
                if combined_context
                else feedback_context
            )
        if improvement_context:
            combined_context = (
                combined_context + "\n\n" + improvement_context
                if combined_context
                else improvement_context
            )

        # IMP-LOOP-028: Warn when all context sources return empty
        if not combined_context.strip():
            logger.warning(
                "All context sources returned empty - phase executing without historical guidance",
                extra={
                    "phase": phase_id,
                    "memory_empty": not memory_context,
                    "feedback_empty": not feedback_context,
                    "improvement_empty": not improvement_context,
                },
            )

        return combined_context
