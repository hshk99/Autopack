"""Injects memory context into builder prompts.

Retrieves historical context (past errors, strategies, hints, insights) from
vector memory and formats them for injection into builder prompts, enabling
the builder to learn from past experience.

IMP-MEM-002: Includes cross-phase conflict detection for hints to prevent
contradictory lessons from being active simultaneously.
"""

import logging
import re
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .memory_service import ContextMetadata, MemoryService

logger = logging.getLogger(__name__)


@dataclass
class ContextInjectionMetadata:
    """Metadata about context injection for impact measurement (IMP-LOOP-021).

    Tracks whether context was injected and how many items were provided,
    enabling A/B comparison of phase success rates with/without context.
    """

    context_injected: bool  # True if any context items were injected
    context_item_count: int  # Total number of context items injected
    errors_count: int  # Number of past errors injected
    strategies_count: int  # Number of successful strategies injected
    hints_count: int  # Number of doctor hints injected
    insights_count: int  # Number of relevant insights injected
    discovery_count: int  # Number of discovery insights injected


@dataclass
class InjectionTrackingRecord:
    """Record of a context injection for effectiveness measurement (IMP-LOOP-029).

    Tracks an individual context injection event along with its outcome,
    enabling correlation between context injection and phase success rates.

    Attributes:
        injection_id: Unique identifier for this injection event
        phase_id: The phase this injection was for
        timestamp: When the injection occurred
        memory_count: Number of memory items injected
        had_context: Whether any context was actually injected
        outcome: Phase outcome (success/failure) after correlation
        metrics: Additional metrics from phase execution
    """

    injection_id: str
    phase_id: str
    timestamp: str
    memory_count: int
    had_context: bool
    outcome: Optional[Dict[str, Any]] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "injection_id": self.injection_id,
            "phase_id": self.phase_id,
            "timestamp": self.timestamp,
            "memory_count": self.memory_count,
            "had_context": self.had_context,
            "outcome": self.outcome,
            "metrics": self.metrics,
        }


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
    """Retrieves and formats memory context for injection into builder prompts.

    IMP-LOOP-029: Includes injection tracking for effectiveness measurement,
    enabling correlation between context injection and phase outcomes.
    """

    def __init__(self, memory_service: Optional[MemoryService] = None):
        """Initialize with optional memory service instance.

        Args:
            memory_service: MemoryService instance (creates default if None)
        """
        self._memory = memory_service or MemoryService()
        # IMP-LOOP-029: Track injections for effectiveness measurement
        self._injections: Dict[str, InjectionTrackingRecord] = {}

    def get_context_for_phase(
        self,
        phase_type: str,
        current_goal: str,
        project_id: str,
        max_tokens: int = 500,
    ) -> ContextInjection:
        """Retrieve relevant context for a phase.

        .. deprecated::
            Use :meth:`get_context_for_phase_with_metadata` instead for enriched
            context with source, timestamp, and freshness metadata (IMP-LOOP-024).

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
        # IMP-LOOP-024: Deprecation warning - prefer EnrichedContextInjection
        warnings.warn(
            "get_context_for_phase() is deprecated, use get_context_for_phase_with_metadata() "
            "for enriched context with source, timestamp, and freshness metadata (IMP-LOOP-024)",
            DeprecationWarning,
            stacklevel=2,
        )
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
            # IMP-MEM-010: Apply freshness threshold to prevent stale context injection
            error_query = f"{phase_type} error failure issue"
            errors_result = self._memory.search_errors(
                query=error_query,
                project_id=project_id,
                limit=3,
                max_age_hours=168,  # 7 days freshness threshold
            )
            past_errors = [
                e.get("payload", {}).get("error_snippet", e.get("content", ""))
                for e in errors_result
            ]

            # Query for successful strategies
            # IMP-MEM-010: Apply freshness threshold to prevent stale context injection
            success_query = f"{phase_type} success strategy approach solution"
            summaries_result = self._memory.search_summaries(
                query=success_query,
                project_id=project_id,
                limit=3,
                max_age_hours=168,  # 7 days freshness threshold
            )
            successful_strategies = [
                s.get("payload", {}).get("summary", s.get("content", ""))[
                    :200
                ]  # Truncate to 200 chars
                for s in summaries_result
            ]

            # Query for doctor hints
            # IMP-MEM-010: Apply freshness threshold to prevent stale context injection
            hints_query = f"doctor recommendation hint {current_goal}"
            hints_result = self._memory.search_doctor_hints(
                query=hints_query,
                project_id=project_id,
                limit=5,  # Get more for conflict resolution
                max_age_hours=168,  # 7 days freshness threshold
            )
            raw_doctor_hints = [
                h.get("payload", {}).get("hint", h.get("content", "")) for h in hints_result
            ]

            # IMP-MEM-002: Apply conflict resolution to hints
            doctor_hints, conflicts_resolved = self._resolve_conflicts_plain(raw_doctor_hints)
            doctor_hints = doctor_hints[:2]  # Limit to 2 after conflict resolution

            if conflicts_resolved > 0:
                logger.info(
                    f"[IMP-MEM-002] Resolved {conflicts_resolved} conflicting plain hints "
                    f"for phase={phase_type}"
                )

            # Query for relevant insights to current goal
            # IMP-MEM-010: Apply freshness threshold to prevent stale context injection
            insights_query = current_goal
            code_result = self._memory.search_code(
                query=insights_query,
                project_id=project_id,
                limit=3,
                max_age_hours=168,  # 7 days freshness threshold
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

        .. deprecated::
            Use :meth:`format_enriched_for_prompt` instead for enriched context
            formatting with confidence warnings (IMP-LOOP-024).

        Creates a structured markdown section with historical context that can
        be injected into the builder prompt.

        Args:
            injection: ContextInjection with retrieved items

        Returns:
            Formatted string suitable for prompt injection, or empty string if no context
        """
        # IMP-LOOP-024: Deprecation warning - prefer format_enriched_for_prompt
        warnings.warn(
            "format_for_prompt() is deprecated, use format_enriched_for_prompt() "
            "for enriched context formatting with confidence warnings (IMP-LOOP-024)",
            DeprecationWarning,
            stacklevel=2,
        )
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
            raw_hints = hints_metadata.get("hints", [])[:5]  # Get more for conflict resolution
            insights = insights_metadata.get("code", [])[:3]

            # IMP-MEM-002: Apply conflict resolution to hints before using them
            hints, conflicts_resolved = self._resolve_conflicts(raw_hints)
            hints = hints[:2]  # Limit to 2 after conflict resolution

            if conflicts_resolved > 0:
                logger.info(
                    f"[IMP-MEM-002] Resolved {conflicts_resolved} conflicting hints "
                    f"for phase={phase_type}, goal='{current_goal[:50]}...'"
                )

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

            # IMP-MEM-002: Add conflict resolution info to quality summary
            quality_summary["conflicts_resolved"] = conflicts_resolved

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

    # -------------------------------------------------------------------------
    # IMP-MEM-002: Cross-Phase Conflict Detection for Hints
    # -------------------------------------------------------------------------

    # Patterns that indicate contradictory advice
    _CONTRADICTION_PATTERNS: List[Tuple[str, str]] = [
        (r"\buse\b", r"\bavoid\b"),
        (r"\balways\b", r"\bnever\b"),
        (r"\benable\b", r"\bdisable\b"),
        (r"\bprefer\b", r"\bavoid\b"),
        (r"\bdo\b", r"\bdon'?t\b"),
        (r"\bshould\b", r"\bshould\s*n'?t\b"),
        (r"\bsync\b", r"\basync\b"),
        (r"\binclude\b", r"\bexclude\b"),
        (r"\badd\b", r"\bremove\b"),
        (r"\bincrease\b", r"\bdecrease\b"),
    ]

    def _extract_topic(self, content: str) -> str:
        """Extract the main topic/keyword from hint content.

        IMP-MEM-002: Extracts a normalized topic key for grouping hints.
        Uses the first significant noun phrase or key technical term.

        Args:
            content: Hint content string

        Returns:
            Normalized topic string for grouping
        """
        if not content:
            return ""

        # Normalize content
        content_lower = content.lower().strip()

        # Remove common prefixes that don't contribute to topic
        prefixes_to_remove = [
            r"^(always|never|do|don't|should|shouldn't|try to|avoid|prefer|use)\s+",
            r"^(when|if|before|after|during)\s+\w+\s*,?\s*",
        ]
        for pattern in prefixes_to_remove:
            content_lower = re.sub(pattern, "", content_lower, flags=re.IGNORECASE)

        # Extract key technical terms (typically nouns and compound terms)
        # Look for common programming/technical patterns
        tech_patterns = [
            r"\b(async|sync|await|promise|callback)\b",
            r"\b(cache|caching|memory|storage)\b",
            r"\b(retry|timeout|backoff|rate.?limit)\b",
            r"\b(test|testing|mock|stub)\b",
            r"\b(error|exception|handling|logging)\b",
            r"\b(database|db|query|sql|orm)\b",
            r"\b(api|endpoint|route|request|response)\b",
            r"\b(import|export|module|package)\b",
            r"\b(config|configuration|setting|option)\b",
            r"\b(type|typing|annotation|hint)\b",
        ]

        for pattern in tech_patterns:
            match = re.search(pattern, content_lower)
            if match:
                return match.group(1).replace("-", "").replace("_", "")

        # Fallback: extract first significant word (>3 chars, not common words)
        common_words = {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "have",
            "been",
            "will",
            "your",
            "code",
            "when",
            "make",
            "sure",
        }
        words = re.findall(r"\b[a-z][a-z_-]{2,}\b", content_lower)
        for word in words:
            if word not in common_words:
                return word

        # Last resort: use hash of content
        return f"topic_{hash(content_lower) % 10000}"

    def _are_conflicting(self, content1: str, content2: str) -> bool:
        """Detect if two hints contradict each other.

        IMP-MEM-002: Checks if two hints give contradictory advice by looking
        for opposing action patterns applied to similar topics.

        Args:
            content1: First hint content
            content2: Second hint content

        Returns:
            True if hints appear to contradict each other
        """
        if not content1 or not content2:
            return False

        c1_lower = content1.lower()
        c2_lower = content2.lower()

        # Check for contradiction patterns
        for positive_pattern, negative_pattern in self._CONTRADICTION_PATTERNS:
            # Check if one hint has positive pattern and other has negative
            c1_has_positive = bool(re.search(positive_pattern, c1_lower, re.IGNORECASE))
            c1_has_negative = bool(re.search(negative_pattern, c1_lower, re.IGNORECASE))
            c2_has_positive = bool(re.search(positive_pattern, c2_lower, re.IGNORECASE))
            c2_has_negative = bool(re.search(negative_pattern, c2_lower, re.IGNORECASE))

            # Contradiction: one says "use X" and other says "avoid X"
            if (c1_has_positive and c2_has_negative) or (c1_has_negative and c2_has_positive):
                # Verify they're talking about similar topic
                topic1 = self._extract_topic(content1)
                topic2 = self._extract_topic(content2)
                if topic1 and topic2 and topic1 == topic2:
                    return True

        return False

    def _resolve_conflicts(self, hints: List[ContextMetadata]) -> Tuple[List[ContextMetadata], int]:
        """Remove conflicting hints, keeping highest confidence.

        IMP-MEM-002: Groups hints by topic and resolves contradictions by
        keeping the hint with the highest confidence score.

        Args:
            hints: List of ContextMetadata hint objects

        Returns:
            Tuple of (filtered hints list, number of conflicts resolved)
        """
        if not hints:
            return [], 0

        # Sort by confidence descending so we process high-confidence first
        sorted_hints = sorted(hints, key=lambda h: h.confidence, reverse=True)

        seen_topics: Dict[str, ContextMetadata] = {}
        conflicts_resolved = 0

        for hint in sorted_hints:
            topic = self._extract_topic(hint.content)

            if topic not in seen_topics:
                # First hint for this topic - check for conflicts with existing topics
                has_conflict = False
                for existing_topic, existing_hint in seen_topics.items():
                    if self._are_conflicting(hint.content, existing_hint.content):
                        # Conflict detected - skip this hint (existing has higher confidence)
                        has_conflict = True
                        conflicts_resolved += 1
                        logger.debug(
                            f"[IMP-MEM-002] Conflict detected: '{hint.content[:50]}...' "
                            f"conflicts with '{existing_hint.content[:50]}...'. "
                            f"Keeping higher confidence hint ({existing_hint.confidence:.2f} > {hint.confidence:.2f})"
                        )
                        break

                if not has_conflict:
                    seen_topics[topic] = hint
            else:
                # Same topic - check if contradictory
                existing_hint = seen_topics[topic]
                if self._are_conflicting(hint.content, existing_hint.content):
                    # Already have higher confidence hint for this topic
                    conflicts_resolved += 1
                    logger.debug(
                        f"[IMP-MEM-002] Duplicate topic conflict: '{hint.content[:50]}...' "
                        f"Keeping existing hint with confidence {existing_hint.confidence:.2f}"
                    )

        if conflicts_resolved > 0:
            logger.info(
                f"[IMP-MEM-002] Resolved {conflicts_resolved} conflicting hints, "
                f"kept {len(seen_topics)} hints"
            )

        return list(seen_topics.values()), conflicts_resolved

    def _resolve_conflicts_plain(self, hints: List[str]) -> Tuple[List[str], int]:
        """Remove conflicting hints from plain string list.

        IMP-MEM-002: Simpler conflict resolution for plain string hints.
        Groups by topic and keeps first occurrence (assumed higher relevance).

        Args:
            hints: List of hint content strings

        Returns:
            Tuple of (filtered hints list, number of conflicts resolved)
        """
        if not hints:
            return [], 0

        seen_topics: Dict[str, str] = {}
        conflicts_resolved = 0

        for hint in hints:
            topic = self._extract_topic(hint)

            if topic not in seen_topics:
                # Check for conflicts with existing hints
                has_conflict = False
                for existing_topic, existing_hint in seen_topics.items():
                    if self._are_conflicting(hint, existing_hint):
                        has_conflict = True
                        conflicts_resolved += 1
                        logger.debug(
                            f"[IMP-MEM-002] Plain hint conflict: '{hint[:50]}...' "
                            f"conflicts with existing hint"
                        )
                        break

                if not has_conflict:
                    seen_topics[topic] = hint
            else:
                existing_hint = seen_topics[topic]
                if self._are_conflicting(hint, existing_hint):
                    conflicts_resolved += 1

        if conflicts_resolved > 0:
            logger.info(f"[IMP-MEM-002] Resolved {conflicts_resolved} conflicting plain hints")

        return list(seen_topics.values()), conflicts_resolved

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

    # -------------------------------------------------------------------------
    # IMP-LOOP-021: Context Injection Impact Measurement
    # -------------------------------------------------------------------------

    def get_injection_metadata(self, injection: ContextInjection) -> ContextInjectionMetadata:
        """Extract injection metadata for impact measurement (IMP-LOOP-021).

        Creates metadata tracking whether context was injected and counts
        by category. This enables A/B comparison of phase success rates
        between phases with and without context injection.

        Args:
            injection: ContextInjection with retrieved context items

        Returns:
            ContextInjectionMetadata with injection statistics
        """
        errors_count = len(injection.past_errors)
        strategies_count = len(injection.successful_strategies)
        hints_count = len(injection.doctor_hints)
        insights_count = len(injection.relevant_insights)
        discovery_count = len(injection.discovery_insights)

        total_count = (
            errors_count + strategies_count + hints_count + insights_count + discovery_count
        )

        metadata = ContextInjectionMetadata(
            context_injected=total_count > 0,
            context_item_count=total_count,
            errors_count=errors_count,
            strategies_count=strategies_count,
            hints_count=hints_count,
            insights_count=insights_count,
            discovery_count=discovery_count,
        )

        logger.debug(
            f"[IMP-LOOP-021] Context injection metadata: injected={metadata.context_injected}, "
            f"count={metadata.context_item_count}"
        )

        return metadata

    def get_enriched_injection_metadata(
        self, injection: EnrichedContextInjection
    ) -> ContextInjectionMetadata:
        """Extract injection metadata from enriched context (IMP-LOOP-021).

        Creates metadata tracking from EnrichedContextInjection objects
        that include confidence and quality information.

        Args:
            injection: EnrichedContextInjection with metadata

        Returns:
            ContextInjectionMetadata with injection statistics
        """
        errors_count = len(injection.past_errors)
        strategies_count = len(injection.successful_strategies)
        hints_count = len(injection.doctor_hints)
        insights_count = len(injection.relevant_insights)
        discovery_count = len(injection.discovery_insights)

        total_count = (
            errors_count + strategies_count + hints_count + insights_count + discovery_count
        )

        metadata = ContextInjectionMetadata(
            context_injected=total_count > 0,
            context_item_count=total_count,
            errors_count=errors_count,
            strategies_count=strategies_count,
            hints_count=hints_count,
            insights_count=insights_count,
            discovery_count=discovery_count,
        )

        logger.debug(
            f"[IMP-LOOP-021] Enriched context injection metadata: "
            f"injected={metadata.context_injected}, count={metadata.context_item_count}, "
            f"avg_confidence={injection.avg_confidence:.2f}"
        )

        return metadata

    # -------------------------------------------------------------------------
    # IMP-LOOP-029: Context Injection Effectiveness Measurement
    # -------------------------------------------------------------------------

    def _generate_injection_id(self, phase_id: str) -> str:
        """Generate a unique injection ID for tracking.

        IMP-LOOP-029: Creates a unique identifier combining phase_id with a
        UUID suffix for tracking injection events.

        Args:
            phase_id: The phase this injection is for

        Returns:
            Unique injection ID string
        """
        return f"{phase_id}_{uuid.uuid4().hex[:8]}"

    def track_injection(
        self,
        phase_id: str,
        memory_count: int,
        had_context: bool,
    ) -> str:
        """Track a context injection for effectiveness measurement.

        IMP-LOOP-029: Records an injection event for later correlation with
        phase outcomes. Returns an injection_id that should be passed to
        correlate_outcome() after phase execution completes.

        Args:
            phase_id: The phase this injection is for
            memory_count: Number of memory items injected
            had_context: Whether any context was actually injected

        Returns:
            injection_id for later outcome correlation
        """
        injection_id = self._generate_injection_id(phase_id)

        record = InjectionTrackingRecord(
            injection_id=injection_id,
            phase_id=phase_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            memory_count=memory_count,
            had_context=had_context,
        )

        self._injections[injection_id] = record

        logger.debug(
            f"[IMP-LOOP-029] Tracked injection: id={injection_id}, "
            f"phase={phase_id}, memory_count={memory_count}, had_context={had_context}"
        )

        return injection_id

    def correlate_outcome(
        self,
        injection_id: str,
        success: bool,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Correlate an injection with its phase outcome for effectiveness analysis.

        IMP-LOOP-029: Records the outcome of a phase that had context injected,
        enabling comparison of success rates with/without context injection.

        Args:
            injection_id: The injection_id returned from track_injection()
            success: Whether the phase succeeded
            metrics: Optional additional metrics from phase execution

        Returns:
            True if correlation was recorded, False if injection_id not found
        """
        if injection_id not in self._injections:
            logger.warning(
                f"[IMP-LOOP-029] Cannot correlate outcome: injection_id={injection_id} not found"
            )
            return False

        record = self._injections[injection_id]
        record.outcome = {
            "success": success,
            "correlated_at": datetime.now(timezone.utc).isoformat(),
        }
        record.metrics = metrics or {}

        logger.debug(
            f"[IMP-LOOP-029] Correlated outcome: id={injection_id}, "
            f"success={success}, had_context={record.had_context}"
        )

        return True

    def get_injection_record(self, injection_id: str) -> Optional[InjectionTrackingRecord]:
        """Get the tracking record for an injection.

        Args:
            injection_id: The injection ID to look up

        Returns:
            InjectionTrackingRecord if found, None otherwise
        """
        return self._injections.get(injection_id)

    def get_all_injection_records(self) -> List[InjectionTrackingRecord]:
        """Get all tracked injection records.

        Returns:
            List of all InjectionTrackingRecord objects
        """
        return list(self._injections.values())

    def get_correlated_records(self) -> List[InjectionTrackingRecord]:
        """Get all injection records that have been correlated with outcomes.

        Returns:
            List of InjectionTrackingRecord objects with outcomes
        """
        return [r for r in self._injections.values() if r.outcome is not None]

    def calculate_effectiveness_summary(self) -> Dict[str, Any]:
        """Calculate summary statistics for context injection effectiveness.

        IMP-LOOP-029: Computes success rates for phases with and without
        context injection, enabling A/B comparison.

        Returns:
            Dict with effectiveness metrics:
            - with_context_success_rate: Success rate when context was injected
            - without_context_success_rate: Success rate when no context
            - delta: Difference (with - without)
            - with_context_count: Number of phases with context
            - without_context_count: Number of phases without context
            - improvement_percent: Percentage improvement from context
        """
        correlated = self.get_correlated_records()

        with_context = [r for r in correlated if r.had_context]
        without_context = [r for r in correlated if not r.had_context]

        with_success = sum(1 for r in with_context if r.outcome and r.outcome.get("success"))
        without_success = sum(1 for r in without_context if r.outcome and r.outcome.get("success"))

        with_rate = with_success / len(with_context) if with_context else 0.0
        without_rate = without_success / len(without_context) if without_context else 0.0

        delta = with_rate - without_rate
        improvement_percent = (delta / without_rate * 100) if without_rate > 0 else 0.0

        summary = {
            "with_context_success_rate": round(with_rate, 4),
            "without_context_success_rate": round(without_rate, 4),
            "delta": round(delta, 4),
            "with_context_count": len(with_context),
            "without_context_count": len(without_context),
            "improvement_percent": round(improvement_percent, 2),
            "total_correlated": len(correlated),
            "is_significant": len(correlated) >= 10 and abs(delta) >= 0.05,
        }

        logger.info(
            f"[IMP-LOOP-029] Effectiveness summary: "
            f"with_context={with_rate:.2%} ({len(with_context)}), "
            f"without_context={without_rate:.2%} ({len(without_context)}), "
            f"delta={delta:+.2%}"
        )

        return summary

    def clear_injection_records(self) -> int:
        """Clear all tracked injection records.

        Returns:
            Number of records cleared
        """
        count = len(self._injections)
        self._injections.clear()
        logger.debug(f"[IMP-LOOP-029] Cleared {count} injection records")
        return count
