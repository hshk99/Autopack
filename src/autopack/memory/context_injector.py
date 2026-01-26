"""Injects memory context into builder prompts.

Retrieves historical context (past errors, strategies, hints, insights) from
vector memory and formats them for injection into builder prompts, enabling
the builder to learn from past experience.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from .memory_service import MemoryService

logger = logging.getLogger(__name__)


@dataclass
class ContextInjection:
    """Context to inject into builder prompt."""

    past_errors: List[str]
    successful_strategies: List[str]
    doctor_hints: List[str]
    relevant_insights: List[str]
    discovery_insights: List[str]  # IMP-DISC-001: Discovery context from research modules
    total_token_estimate: int


class ContextInjector:
    """Retrieves and formats memory context for injection into builder prompts."""

    def __init__(self, memory_service: Optional[MemoryService] = None):
        """Initialize with optional memory service instance.

        Args:
            memory_service: MemoryService instance (creates default if None)
        """
        self._memory = memory_service or MemoryService()

    def get_context_for_phase(
        self,
        phase_type: str,
        current_goal: str,
        project_id: str,
        max_tokens: int = 500,
    ) -> ContextInjection:
        """Retrieve relevant context for a phase.

        Queries memory for:
        - Past errors related to this phase type
        - Successful strategies used before
        - Doctor hints and recommendations
        - General insights related to the goal

        Args:
            phase_type: Type of phase (e.g., 'build', 'test', 'deploy')
            current_goal: The goal/description for this phase
            project_id: Project ID for scoping memory queries
            max_tokens: Maximum tokens to allocate for context (default 500)

        Returns:
            ContextInjection with retrieved context items
        """
        if not self._memory.enabled:
            logger.debug("[ContextInjector] Memory disabled, returning empty context")
            return ContextInjection(
                past_errors=[],
                successful_strategies=[],
                doctor_hints=[],
                relevant_insights=[],
                discovery_insights=[],
                total_token_estimate=0,
            )

        try:
            # Query for past errors related to this phase type
            error_query = f"{phase_type} error failure issue"
            errors_result = self._memory.search_errors(
                query=error_query,
                project_id=project_id,
                limit=3,
            )
            past_errors = [
                e.get("payload", {}).get("error_snippet", e.get("content", ""))
                for e in errors_result
            ]

            # Query for successful strategies
            success_query = f"{phase_type} success strategy approach solution"
            summaries_result = self._memory.search_summaries(
                query=success_query,
                project_id=project_id,
                limit=3,
            )
            successful_strategies = [
                s.get("payload", {}).get("summary", s.get("content", ""))[
                    :200
                ]  # Truncate to 200 chars
                for s in summaries_result
            ]

            # Query for doctor hints
            hints_query = f"doctor recommendation hint {current_goal}"
            hints_result = self._memory.search_doctor_hints(
                query=hints_query,
                project_id=project_id,
                limit=2,
            )
            doctor_hints = [
                h.get("payload", {}).get("hint", h.get("content", "")) for h in hints_result
            ]

            # Query for relevant insights to current goal
            insights_query = current_goal
            code_result = self._memory.search_code(
                query=insights_query,
                project_id=project_id,
                limit=3,
            )
            relevant_insights = [
                c.get("payload", {}).get("content", c.get("content", ""))[:200] for c in code_result
            ]

            # IMP-DISC-001: Retrieve discovery context from research modules
            discovery_insights = self.get_discovery_context(
                phase_type=phase_type,
                current_goal=current_goal,
                limit=3,
            )

            # Estimate total tokens
            all_content = (
                past_errors
                + successful_strategies
                + doctor_hints
                + relevant_insights
                + discovery_insights
            )
            total_token_estimate = self._estimate_tokens(all_content)

            logger.info(
                f"[ContextInjector] Retrieved context for {phase_type}: "
                f"{len(past_errors)} errors, {len(successful_strategies)} strategies, "
                f"{len(doctor_hints)} hints, {len(relevant_insights)} insights, "
                f"{len(discovery_insights)} discovery insights "
                f"({total_token_estimate} tokens estimated)"
            )

            return ContextInjection(
                past_errors=past_errors,
                successful_strategies=successful_strategies,
                doctor_hints=doctor_hints,
                relevant_insights=relevant_insights,
                discovery_insights=discovery_insights,
                total_token_estimate=total_token_estimate,
            )

        except Exception as e:
            logger.warning(f"[ContextInjector] Failed to retrieve memory context: {e}")
            return ContextInjection(
                past_errors=[],
                successful_strategies=[],
                doctor_hints=[],
                relevant_insights=[],
                discovery_insights=[],
                total_token_estimate=0,
            )

    def format_for_prompt(self, injection: ContextInjection) -> str:
        """Format context injection for builder prompt.

        Creates a structured markdown section with historical context that can
        be injected into the builder prompt.

        Args:
            injection: ContextInjection with retrieved items

        Returns:
            Formatted string suitable for prompt injection, or empty string if no context
        """
        sections = []

        if injection.past_errors:
            error_items = "\n".join(f"- {e[:150]}" for e in injection.past_errors if e)
            if error_items:
                sections.append(f"**Past Errors to Avoid:**\n{error_items}")

        if injection.successful_strategies:
            strategy_items = "\n".join(f"- {s[:150]}" for s in injection.successful_strategies if s)
            if strategy_items:
                sections.append(f"**Successful Strategies:**\n{strategy_items}")

        if injection.doctor_hints:
            hint_items = "\n".join(f"- {h[:150]}" for h in injection.doctor_hints if h)
            if hint_items:
                sections.append(f"**Doctor Recommendations:**\n{hint_items}")

        if injection.relevant_insights:
            insight_items = "\n".join(f"- {i[:150]}" for i in injection.relevant_insights if i)
            if insight_items:
                sections.append(f"**Relevant Historical Insights:**\n{insight_items}")

        # IMP-DISC-001: Include discovery insights from research modules
        if injection.discovery_insights:
            discovery_items = "\n".join(f"- {d[:150]}" for d in injection.discovery_insights if d)
            if discovery_items:
                sections.append(f"**Discovery Insights (External Sources):**\n{discovery_items}")

        return "\n\n".join(sections) if sections else ""

    def _estimate_tokens(self, content_list: List[str]) -> int:
        """Estimate token count for content.

        Uses rough approximation: ~4 characters per token.

        Args:
            content_list: List of content strings

        Returns:
            Estimated token count
        """
        total_chars = sum(len(str(item)) for item in content_list if item)
        return max(0, total_chars // 4)

    def get_discovery_context(
        self,
        phase_type: str,
        current_goal: str,
        limit: int = 3,
    ) -> List[str]:
        """Retrieve discovery context from research/discovery modules (IMP-DISC-001).

        Queries the discovery system (GitHub, Reddit, Web sources) for relevant
        solutions and insights that can inform the current phase execution.

        Args:
            phase_type: Type of phase (e.g., 'build', 'test', 'deploy')
            current_goal: The goal/description for this phase
            limit: Maximum number of discovery insights to return

        Returns:
            List of discovery insight strings
        """
        try:
            from ..roadc.discovery_context_merger import DiscoveryContextMerger

            merger = DiscoveryContextMerger()
            merged = merger.merge_sources(
                query=f"{phase_type} {current_goal}",
                limit=limit,
            )
            ranked = merger.rank_by_relevance(merged, current_goal)

            logger.debug(
                f"[ContextInjector] Retrieved {len(ranked)} discovery insights "
                f"for phase={phase_type}"
            )
            return ranked[:limit]

        except ImportError:
            logger.debug(
                "[ContextInjector] DiscoveryContextMerger not available, "
                "skipping discovery context"
            )
            return []
        except Exception as e:
            logger.warning(f"[ContextInjector] Failed to retrieve discovery context: {e}")
            return []
