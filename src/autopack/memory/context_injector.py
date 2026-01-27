"""Injects memory context into builder prompts.

Retrieves historical context (past errors, strategies, hints, insights) from
vector memory and formats them for injection into builder prompts, enabling
the builder to learn from past experience.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .memory_service import ContextMetadata, MemoryService

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


@dataclass
class EnrichedContextInjection:
    """Context injection with relevance and confidence metadata.

    IMP-LOOP-019: Extends ContextInjection with quality signals so callers
    know how fresh and relevant the retrieved context is.

    Attributes:
        past_errors: List of ContextMetadata for past errors
        successful_strategies: List of ContextMetadata for strategies
        doctor_hints: List of ContextMetadata for hints
        relevant_insights: List of ContextMetadata for code insights
        discovery_insights: List of plain strings (discovery has no metadata)
        total_token_estimate: Estimated token count
        quality_summary: Aggregated quality metrics for the context
        has_low_confidence_warning: True if significant portion is low confidence
    """

    past_errors: List[ContextMetadata]
    successful_strategies: List[ContextMetadata]
    doctor_hints: List[ContextMetadata]
    relevant_insights: List[ContextMetadata]
    discovery_insights: List[str]
    total_token_estimate: int
    quality_summary: Dict[str, Any] = field(default_factory=dict)
    has_low_confidence_warning: bool = False

    def to_plain_injection(self) -> ContextInjection:
        """Convert to plain ContextInjection (for backward compatibility).

        Returns:
            ContextInjection with just the content strings
        """
        return ContextInjection(
            past_errors=[m.content for m in self.past_errors],
            successful_strategies=[m.content for m in self.successful_strategies],
            doctor_hints=[m.content for m in self.doctor_hints],
            relevant_insights=[m.content for m in self.relevant_insights],
            discovery_insights=self.discovery_insights,
            total_token_estimate=self.total_token_estimate,
        )

    @property
    def avg_confidence(self) -> float:
        """Average confidence across all context items."""
        all_items = (
            self.past_errors
            + self.successful_strategies
            + self.doctor_hints
            + self.relevant_insights
        )
        if not all_items:
            return 0.0
        return sum(item.confidence for item in all_items) / len(all_items)

    @property
    def low_confidence_count(self) -> int:
        """Count of items with low confidence."""
        all_items = (
            self.past_errors
            + self.successful_strategies
            + self.doctor_hints
            + self.relevant_insights
        )
        return sum(1 for item in all_items if item.is_low_confidence)


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
                "[ContextInjector] DiscoveryContextMerger not available, skipping discovery context"
            )
            return []
        except Exception as e:
            logger.warning(f"[ContextInjector] Failed to retrieve discovery context: {e}")
            return []

    # -------------------------------------------------------------------------
    # IMP-LOOP-019: Context with Relevance/Confidence Metadata
    # -------------------------------------------------------------------------

    def get_context_for_phase_with_metadata(
        self,
        phase_type: str,
        current_goal: str,
        project_id: str,
        max_tokens: int = 500,
    ) -> EnrichedContextInjection:
        """Retrieve context with relevance and confidence metadata.

        IMP-LOOP-019: Returns EnrichedContextInjection with ContextMetadata
        objects that include relevance_score, age_hours, and confidence.

        Args:
            phase_type: Type of phase (e.g., 'build', 'test', 'deploy')
            current_goal: The goal/description for this phase
            project_id: Project ID for scoping memory queries
            max_tokens: Maximum tokens to allocate for context (default 500)

        Returns:
            EnrichedContextInjection with metadata for each context item
        """
        empty_result = EnrichedContextInjection(
            past_errors=[],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=0,
            quality_summary={
                "total_items": 0,
                "low_confidence_count": 0,
                "avg_confidence": 0.0,
                "avg_age_hours": 0.0,
                "has_low_confidence_warning": False,
            },
            has_low_confidence_warning=False,
        )

        if not self._memory.enabled:
            logger.debug("[ContextInjector] Memory disabled, returning empty enriched context")
            return empty_result

        try:
            # Build query strings for each context type
            error_query = f"{phase_type} error failure issue"
            success_query = f"{phase_type} success strategy approach solution"
            hints_query = f"doctor recommendation hint {current_goal}"
            insights_query = current_goal

            # Retrieve context with metadata using the new method
            error_metadata = self._memory.retrieve_context_with_metadata(
                query=error_query,
                project_id=project_id,
                include_code=False,
                include_summaries=False,
                include_errors=True,
                include_hints=False,
            )

            strategy_metadata = self._memory.retrieve_context_with_metadata(
                query=success_query,
                project_id=project_id,
                include_code=False,
                include_summaries=True,
                include_errors=False,
                include_hints=False,
            )

            hints_metadata = self._memory.retrieve_context_with_metadata(
                query=hints_query,
                project_id=project_id,
                include_code=False,
                include_summaries=False,
                include_errors=False,
                include_hints=True,
            )

            insights_metadata = self._memory.retrieve_context_with_metadata(
                query=insights_query,
                project_id=project_id,
                include_code=True,
                include_summaries=False,
                include_errors=False,
                include_hints=False,
            )

            # Extract the relevant lists and limit to 3 items each
            past_errors = error_metadata.get("errors", [])[:3]
            strategies = strategy_metadata.get("summaries", [])[:3]
            hints = hints_metadata.get("hints", [])[:2]
            insights = insights_metadata.get("code", [])[:3]

            # Get discovery context (no metadata for external sources)
            discovery_insights = self.get_discovery_context(
                phase_type=phase_type,
                current_goal=current_goal,
                limit=3,
            )

            # Calculate token estimate
            all_content = (
                [m.content for m in past_errors]
                + [m.content for m in strategies]
                + [m.content for m in hints]
                + [m.content for m in insights]
                + discovery_insights
            )
            total_token_estimate = self._estimate_tokens(all_content)

            # Calculate quality summary
            all_metadata_items = past_errors + strategies + hints + insights
            quality_summary = self._calculate_quality_summary(all_metadata_items)

            # Determine if we should warn about low confidence
            has_warning = quality_summary.get("has_low_confidence_warning", False)

            if has_warning:
                logger.warning(
                    f"[ContextInjector] Low confidence context retrieved for {phase_type}: "
                    f"{quality_summary['low_confidence_count']}/{quality_summary['total_items']} "
                    f"items are low confidence (avg={quality_summary['avg_confidence']:.2f})"
                )

            logger.info(
                f"[ContextInjector] Retrieved enriched context for {phase_type}: "
                f"{len(past_errors)} errors, {len(strategies)} strategies, "
                f"{len(hints)} hints, {len(insights)} insights, "
                f"{len(discovery_insights)} discovery insights "
                f"(avg_confidence={quality_summary.get('avg_confidence', 0):.2f}, "
                f"{total_token_estimate} tokens)"
            )

            return EnrichedContextInjection(
                past_errors=past_errors,
                successful_strategies=strategies,
                doctor_hints=hints,
                relevant_insights=insights,
                discovery_insights=discovery_insights,
                total_token_estimate=total_token_estimate,
                quality_summary=quality_summary,
                has_low_confidence_warning=has_warning,
            )

        except Exception as e:
            logger.warning(f"[ContextInjector] Failed to retrieve enriched memory context: {e}")
            return empty_result

    def _calculate_quality_summary(self, items: List[ContextMetadata]) -> Dict[str, Any]:
        """Calculate aggregated quality metrics for context items.

        Args:
            items: List of ContextMetadata objects

        Returns:
            Dict with quality metrics
        """
        if not items:
            return {
                "total_items": 0,
                "low_confidence_count": 0,
                "avg_confidence": 0.0,
                "avg_age_hours": 0.0,
                "has_low_confidence_warning": False,
            }

        total = len(items)
        low_confidence = sum(1 for item in items if item.is_low_confidence)
        avg_confidence = sum(item.confidence for item in items) / total

        # Calculate average age, excluding unknown ages (-1)
        valid_ages = [item.age_hours for item in items if item.age_hours >= 0]
        avg_age = sum(valid_ages) / len(valid_ages) if valid_ages else -1.0

        # Warning if more than 50% of items are low confidence
        has_warning = (low_confidence / total) > 0.5 if total > 0 else False

        return {
            "total_items": total,
            "low_confidence_count": low_confidence,
            "avg_confidence": round(avg_confidence, 3),
            "avg_age_hours": round(avg_age, 1) if avg_age >= 0 else -1.0,
            "has_low_confidence_warning": has_warning,
        }

    def format_enriched_for_prompt(
        self,
        injection: EnrichedContextInjection,
        include_confidence_warnings: bool = True,
    ) -> str:
        """Format enriched context injection for builder prompt.

        IMP-LOOP-019: Formats context with optional confidence warnings
        so the builder knows when context may be unreliable.

        Args:
            injection: EnrichedContextInjection with metadata
            include_confidence_warnings: Whether to include low-confidence warnings

        Returns:
            Formatted string suitable for prompt injection
        """
        sections = []

        # Add confidence warning header if needed
        if include_confidence_warnings and injection.has_low_confidence_warning:
            warning = (
                "**⚠️ Context Quality Warning:**\n"
                f"Some retrieved context has low confidence "
                f"(avg={injection.quality_summary.get('avg_confidence', 0):.2f}). "
                "Consider verifying this information before relying on it."
            )
            sections.append(warning)

        # Format past errors with confidence indicators
        if injection.past_errors:
            error_items = []
            for m in injection.past_errors:
                content = m.content[:150] if m.content else ""
                if m.is_low_confidence and include_confidence_warnings:
                    error_items.append(f"- {content} _(low confidence)_")
                else:
                    error_items.append(f"- {content}")
            if error_items:
                sections.append("**Past Errors to Avoid:**\n" + "\n".join(error_items))

        # Format strategies
        if injection.successful_strategies:
            strategy_items = []
            for m in injection.successful_strategies:
                content = m.content[:150] if m.content else ""
                if m.is_low_confidence and include_confidence_warnings:
                    strategy_items.append(f"- {content} _(low confidence)_")
                else:
                    strategy_items.append(f"- {content}")
            if strategy_items:
                sections.append("**Successful Strategies:**\n" + "\n".join(strategy_items))

        # Format hints
        if injection.doctor_hints:
            hint_items = []
            for m in injection.doctor_hints:
                content = m.content[:150] if m.content else ""
                if m.is_low_confidence and include_confidence_warnings:
                    hint_items.append(f"- {content} _(low confidence)_")
                else:
                    hint_items.append(f"- {content}")
            if hint_items:
                sections.append("**Doctor Recommendations:**\n" + "\n".join(hint_items))

        # Format insights
        if injection.relevant_insights:
            insight_items = []
            for m in injection.relevant_insights:
                content = m.content[:150] if m.content else ""
                if m.is_low_confidence and include_confidence_warnings:
                    insight_items.append(f"- {content} _(low confidence)_")
                else:
                    insight_items.append(f"- {content}")
            if insight_items:
                sections.append("**Relevant Historical Insights:**\n" + "\n".join(insight_items))

        # Discovery insights (no metadata)
        if injection.discovery_insights:
            discovery_items = "\n".join(f"- {d[:150]}" for d in injection.discovery_insights if d)
            if discovery_items:
                sections.append(f"**Discovery Insights (External Sources):**\n{discovery_items}")

        return "\n\n".join(sections) if sections else ""
