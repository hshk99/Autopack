"""
Follow-up Research Trigger for automated gap-filling research.

Analyzes research findings to identify areas requiring deeper investigation
and triggers targeted follow-up research automatically.

IMP-HIGH-005: Implements callback execution mechanism for mid-execution
research triggering. Callbacks are invoked when triggers are detected,
enabling autonomous research loop closure.
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Types of follow-up research triggers."""

    UNCERTAINTY = "uncertainty"  # Low confidence or conflicting sources
    GAP = "gap"  # Missing information
    DEPTH = "depth"  # Needs deeper investigation
    VALIDATION = "validation"  # Claims need verification
    EMERGING = "emerging"  # New relevant topics discovered


class TriggerPriority(Enum):
    """Priority levels for triggers."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ResearchPlan:
    """Plan for follow-up research on a trigger."""

    queries: List[str]
    target_agent: str
    expected_outcome: str
    estimated_time_minutes: int = 5


@dataclass
class CallbackResult:
    """Result of a callback execution for a trigger.

    IMP-HIGH-005: Tracks the outcome of callback execution including
    any research results or errors.
    """

    trigger_id: str
    success: bool
    executed_at: datetime = field(default_factory=datetime.now)
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    execution_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "success": self.success,
            "executed_at": self.executed_at.isoformat(),
            "result_data": self.result_data,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class FollowupTrigger:
    """A trigger for follow-up research."""

    trigger_id: str
    trigger_type: TriggerType
    priority: TriggerPriority
    reason: str
    source_finding: str
    research_plan: ResearchPlan
    created_at: datetime = field(default_factory=datetime.now)
    addressed: bool = False
    addressed_at: Optional[datetime] = None
    # IMP-HIGH-005: Track callback execution results
    callback_results: List[CallbackResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "type": self.trigger_type.value,
            "priority": self.priority.value,
            "reason": self.reason,
            "source_finding": self.source_finding,
            "research_plan": {
                "queries": self.research_plan.queries,
                "target_agent": self.research_plan.target_agent,
                "expected_outcome": self.research_plan.expected_outcome,
            },
            "created_at": self.created_at.isoformat(),
            "addressed": self.addressed,
            "addressed_at": self.addressed_at.isoformat() if self.addressed_at else None,
            "callback_results": [r.to_dict() for r in self.callback_results],
        }

    def mark_executed(self, result: CallbackResult) -> None:
        """Mark this trigger as having had a callback executed.

        IMP-HIGH-005: Records callback result and updates addressed status.

        Args:
            result: The callback execution result
        """
        self.callback_results.append(result)
        if result.success:
            self.addressed = True
            self.addressed_at = datetime.now()


@dataclass
class TriggerExecutionResult:
    """Result of executing all callbacks for a set of triggers.

    IMP-HIGH-005: Aggregates results from callback execution across
    multiple triggers.
    """

    triggers_executed: int
    callbacks_invoked: int
    successful_executions: int
    failed_executions: int
    total_execution_time_ms: int
    callback_results: List[CallbackResult] = field(default_factory=list)
    integrated_findings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_execution_result": {
                "triggers_executed": self.triggers_executed,
                "callbacks_invoked": self.callbacks_invoked,
                "successful_executions": self.successful_executions,
                "failed_executions": self.failed_executions,
                "total_execution_time_ms": self.total_execution_time_ms,
                "callback_results": [r.to_dict() for r in self.callback_results],
                "integrated_findings_count": len(self.integrated_findings),
            }
        }


@dataclass
class TriggerAnalysisResult:
    """Result of trigger analysis."""

    triggers_detected: int
    triggers_selected: int
    trigger_summary: Dict[str, int]
    selected_triggers: List[FollowupTrigger]
    not_selected_triggers: List[Dict[str, Any]]
    should_research: bool
    execution_plan: Dict[str, Any]
    # IMP-HIGH-005: Track execution results when callbacks are run
    execution_result: Optional[TriggerExecutionResult] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "followup_trigger_analysis": {
                "analysis_timestamp": datetime.now().isoformat(),
                "triggers_detected": self.triggers_detected,
                "triggers_selected": self.triggers_selected,
                "trigger_summary": self.trigger_summary,
                "selected_triggers": [t.to_dict() for t in self.selected_triggers],
                "not_selected_triggers": self.not_selected_triggers,
                "should_research": self.should_research,
                "research_execution_plan": self.execution_plan,
            }
        }
        if self.execution_result:
            result["followup_trigger_analysis"]["execution_result"] = (
                self.execution_result.to_dict()
            )
        return result


# Type alias for callback functions
# Callbacks receive the trigger and return optional result data
TriggerCallback = Callable[[FollowupTrigger], Optional[Dict[str, Any]]]
AsyncTriggerCallback = Callable[[FollowupTrigger], "asyncio.Future[Optional[Dict[str, Any]]]"]


class FollowupResearchTrigger:
    """
    Analyzes findings and triggers automated follow-up research.

    IMP-HIGH-005: Includes callback execution mechanism for mid-execution
    research triggering. Register callbacks with `register_callback()` and
    execute them with `execute_triggers()` or `execute_triggers_async()`.

    Example usage:
        ```python
        trigger = FollowupResearchTrigger()

        # Register a callback to handle research triggers
        def handle_research(trigger: FollowupTrigger) -> Optional[Dict]:
            # Perform research based on trigger.research_plan
            return {"findings": [...]}

        trigger.register_callback(handle_research)

        # Analyze and execute
        result = trigger.analyze(analysis_results)
        if result.should_research:
            execution_result = trigger.execute_triggers(result.selected_triggers)
        ```
    """

    # Configuration
    MAX_TRIGGERS_PER_ITERATION = 5
    MAX_FOLLOWUP_ITERATIONS = 3
    MIN_NEW_INFORMATION_THRESHOLD = 0.2
    CONFIDENCE_THRESHOLD = 0.7

    # Critical topics that warrant deeper research
    CRITICAL_TOPICS = {
        "api_integration",
        "pricing",
        "compliance",
        "security",
        "market_size",
        "competition",
        "legal",
        "technical_feasibility",
    }

    # Agent mapping for different trigger types
    AGENT_MAPPING = {
        TriggerType.UNCERTAINTY: "verification-research",
        TriggerType.GAP: None,  # Determined by gap category
        TriggerType.DEPTH: "deep-dive-research",
        TriggerType.VALIDATION: "validation-research",
        TriggerType.EMERGING: "discovery-agent",
    }

    def __init__(self):
        self._trigger_counter = 0
        self._addressed_triggers: Set[str] = set()
        # IMP-HIGH-005: Callback registration
        self._callbacks: List[TriggerCallback] = []
        self._async_callbacks: List[AsyncTriggerCallback] = []

    def analyze(
        self,
        analysis_results: Dict[str, Any],
        validation_results: Optional[Dict[str, Any]] = None,
        previous_triggers: Optional[List[FollowupTrigger]] = None,
    ) -> TriggerAnalysisResult:
        """
        Analyze findings for follow-up research triggers.

        Args:
            analysis_results: Results from analysis phase
            validation_results: Optional validation results
            previous_triggers: Triggers from previous iteration (for dedup)

        Returns:
            TriggerAnalysisResult with detected and selected triggers
        """
        validation_results = validation_results or {}
        previous_trigger_ids = {t.trigger_id for t in (previous_triggers or [])}

        all_triggers = []

        # 1. Check confidence scores for uncertainty triggers
        all_triggers.extend(self._detect_uncertainty_triggers(analysis_results))

        # 2. Check for noted gaps
        all_triggers.extend(self._detect_gap_triggers(analysis_results))

        # 3. Check validation failures
        all_triggers.extend(self._detect_validation_triggers(validation_results))

        # 4. Check for shallow coverage needing depth
        all_triggers.extend(self._detect_depth_triggers(analysis_results))

        # 5. Check for emerging/unresearched topics
        all_triggers.extend(self._detect_emerging_triggers(analysis_results))

        # 6. Check cross-reference conflicts
        all_triggers.extend(self._detect_conflict_triggers(analysis_results))

        # Filter out already addressed triggers
        new_triggers = [
            t
            for t in all_triggers
            if t.trigger_id not in self._addressed_triggers
            and t.trigger_id not in previous_trigger_ids
        ]

        # Prioritize and select
        prioritized = self._prioritize_triggers(new_triggers)
        selected = prioritized[: self.MAX_TRIGGERS_PER_ITERATION]
        not_selected = prioritized[self.MAX_TRIGGERS_PER_ITERATION :]

        # Generate execution plan
        execution_plan = self._generate_execution_plan(selected)

        # Generate summary
        summary = self._generate_trigger_summary(all_triggers)

        return TriggerAnalysisResult(
            triggers_detected=len(all_triggers),
            triggers_selected=len(selected),
            trigger_summary=summary,
            selected_triggers=selected,
            not_selected_triggers=[
                {
                    "trigger_id": t.trigger_id,
                    "reason_skipped": "Lower priority",
                    "can_revisit": True,
                }
                for t in not_selected
            ],
            should_research=len(selected) > 0,
            execution_plan=execution_plan,
        )

    def _generate_trigger_id(self) -> str:
        """Generate unique trigger ID."""
        self._trigger_counter += 1
        return f"trig-{self._trigger_counter:03d}"

    def _detect_uncertainty_triggers(self, analysis_results: Dict) -> List[FollowupTrigger]:
        """Detect triggers from low confidence findings."""
        triggers = []

        findings = analysis_results.get("findings", [])
        for finding in findings:
            confidence = finding.get("confidence", 1.0)
            if confidence < self.CONFIDENCE_THRESHOLD:
                triggers.append(
                    FollowupTrigger(
                        trigger_id=self._generate_trigger_id(),
                        trigger_type=TriggerType.UNCERTAINTY,
                        priority=self._confidence_to_priority(confidence),
                        reason=f"Low confidence ({confidence:.0%}) on: {finding.get('summary', 'unknown')[:50]}",
                        source_finding=finding.get("id", "unknown"),
                        research_plan=ResearchPlan(
                            queries=self._generate_clarification_queries(finding),
                            target_agent="verification-research",
                            expected_outcome="Higher confidence finding with additional sources",
                        ),
                    )
                )

        return triggers

    def _detect_gap_triggers(self, analysis_results: Dict) -> List[FollowupTrigger]:
        """Detect triggers from identified gaps in analysis."""
        triggers = []

        gaps = analysis_results.get("identified_gaps", [])
        for gap in gaps:
            category = gap.get("category", "general")
            triggers.append(
                FollowupTrigger(
                    trigger_id=self._generate_trigger_id(),
                    trigger_type=TriggerType.GAP,
                    priority=TriggerPriority.HIGH,
                    reason=gap.get("description", "Unknown gap"),
                    source_finding=f"gap:{category}",
                    research_plan=ResearchPlan(
                        queries=gap.get("suggested_queries", [f"research {category}"]),
                        target_agent=self._select_agent_for_category(category),
                        expected_outcome=f"Fill {category} gap with comprehensive data",
                    ),
                )
            )

        return triggers

    def _detect_validation_triggers(self, validation_results: Dict) -> List[FollowupTrigger]:
        """Detect triggers from validation failures."""
        triggers = []

        failed = validation_results.get("failed_validations", [])
        for failure in failed:
            triggers.append(
                FollowupTrigger(
                    trigger_id=self._generate_trigger_id(),
                    trigger_type=TriggerType.VALIDATION,
                    priority=TriggerPriority.MEDIUM,
                    reason=f"Validation failed: {failure.get('reason', 'unknown')}",
                    source_finding=failure.get("finding_id", "unknown"),
                    research_plan=ResearchPlan(
                        queries=self._generate_validation_queries(failure),
                        target_agent="validation-research",
                        expected_outcome="Validated claim with primary sources",
                    ),
                )
            )

        return triggers

    def _detect_depth_triggers(self, analysis_results: Dict) -> List[FollowupTrigger]:
        """Detect triggers for topics needing deeper research."""
        triggers = []

        coverage = analysis_results.get("coverage_analysis", {})
        for topic, depth in coverage.items():
            if depth == "shallow" and topic in self.CRITICAL_TOPICS:
                triggers.append(
                    FollowupTrigger(
                        trigger_id=self._generate_trigger_id(),
                        trigger_type=TriggerType.DEPTH,
                        priority=TriggerPriority.HIGH,
                        reason=f"Critical topic '{topic}' has only shallow coverage",
                        source_finding=f"coverage:{topic}",
                        research_plan=ResearchPlan(
                            queries=self._generate_deep_dive_queries(topic),
                            target_agent="deep-dive-research",
                            expected_outcome=f"Comprehensive analysis of {topic}",
                        ),
                    )
                )

        return triggers

    def _detect_emerging_triggers(self, analysis_results: Dict) -> List[FollowupTrigger]:
        """Detect triggers for newly mentioned but unresearched topics."""
        triggers = []

        # Find entities mentioned but not in researched list
        mentioned = set(analysis_results.get("mentioned_entities", []))
        researched = set(analysis_results.get("researched_entities", []))
        unresearched = mentioned - researched

        for entity in list(unresearched)[:3]:  # Limit to top 3
            triggers.append(
                FollowupTrigger(
                    trigger_id=self._generate_trigger_id(),
                    trigger_type=TriggerType.EMERGING,
                    priority=TriggerPriority.MEDIUM,
                    reason=f"New entity mentioned but not researched: {entity}",
                    source_finding=f"emerging:{entity}",
                    research_plan=ResearchPlan(
                        queries=[f"{entity} analysis", f"{entity} review"],
                        target_agent="discovery-agent",
                        expected_outcome=f"Basic understanding of {entity}",
                    ),
                )
            )

        return triggers

    def _detect_conflict_triggers(self, analysis_results: Dict) -> List[FollowupTrigger]:
        """Detect triggers from cross-reference conflicts."""
        triggers = []

        conflicts = analysis_results.get("cross_reference_conflicts", [])
        for conflict in conflicts:
            triggers.append(
                FollowupTrigger(
                    trigger_id=self._generate_trigger_id(),
                    trigger_type=TriggerType.UNCERTAINTY,
                    priority=TriggerPriority.HIGH,
                    reason=f"Conflicting information: {conflict.get('summary', 'unknown')[:50]}",
                    source_finding=conflict.get("id", "conflict"),
                    research_plan=ResearchPlan(
                        queries=self._generate_resolution_queries(conflict),
                        target_agent="verification-research",
                        expected_outcome="Resolved conflict with authoritative source",
                    ),
                )
            )

        return triggers

    def _confidence_to_priority(self, confidence: float) -> TriggerPriority:
        """Convert confidence score to trigger priority."""
        if confidence < 0.3:
            return TriggerPriority.CRITICAL
        elif confidence < 0.5:
            return TriggerPriority.HIGH
        elif confidence < 0.7:
            return TriggerPriority.MEDIUM
        return TriggerPriority.LOW

    def _prioritize_triggers(self, triggers: List[FollowupTrigger]) -> List[FollowupTrigger]:
        """Sort triggers by priority."""
        priority_order = {
            TriggerPriority.CRITICAL: 0,
            TriggerPriority.HIGH: 1,
            TriggerPriority.MEDIUM: 2,
            TriggerPriority.LOW: 3,
        }
        return sorted(triggers, key=lambda t: priority_order.get(t.priority, 4))

    def _generate_trigger_summary(self, triggers: List[FollowupTrigger]) -> Dict[str, int]:
        """Generate summary of triggers by type."""
        summary = {t.value: 0 for t in TriggerType}
        for trigger in triggers:
            summary[trigger.trigger_type.value] += 1
        return summary

    def _generate_execution_plan(self, triggers: List[FollowupTrigger]) -> Dict[str, Any]:
        """Generate parallel execution plan for triggers."""
        # Group triggers that can run in parallel
        parallel_groups = []
        current_group = []

        for trigger in triggers:
            # Validation and uncertainty can run together
            if trigger.trigger_type in [TriggerType.UNCERTAINTY, TriggerType.VALIDATION]:
                current_group.append(trigger.trigger_id)
                if len(current_group) >= 3:
                    parallel_groups.append(current_group)
                    current_group = []
            else:
                if current_group:
                    parallel_groups.append(current_group)
                    current_group = []
                parallel_groups.append([trigger.trigger_id])

        if current_group:
            parallel_groups.append(current_group)

        estimated_time = sum(t.research_plan.estimated_time_minutes for t in triggers) // max(
            len(parallel_groups), 1
        )

        return {
            "parallel_batches": [
                {"batch": i + 1, "triggers": group} for i, group in enumerate(parallel_groups)
            ],
            "estimated_additional_time_minutes": estimated_time,
            "estimated_api_calls": len(triggers) * 5,  # Rough estimate
        }

    def _select_agent_for_category(self, category: str) -> str:
        """Select appropriate agent for a gap category."""
        category_agents = {
            "market_research": "market-research-agent",
            "competitive_analysis": "competitive-analysis-agent",
            "technical_feasibility": "technical-feasibility-agent",
            "legal_policy": "legal-policy-agent",
            "social_sentiment": "social-sentiment-agent",
            "tool_availability": "tool-availability-agent",
        }
        return category_agents.get(category, "general-research-agent")

    def _generate_clarification_queries(self, finding: Dict) -> List[str]:
        """Generate queries to clarify a low-confidence finding."""
        summary = finding.get("summary", "")
        topic = finding.get("topic", "")

        queries = [
            f"{topic} verified data 2024",
            f"{topic} primary source research",
        ]

        if "market" in summary.lower():
            queries.append(f"{topic} market research report")
        if "api" in summary.lower():
            queries.append(f"{topic} API documentation official")

        return queries[:3]

    def _generate_validation_queries(self, failure: Dict) -> List[str]:
        """Generate queries to validate a failed claim."""
        claim = failure.get("claim", "")
        return [
            f"{claim} verification",
            f"{claim} primary source",
            f"{claim} official documentation",
        ][:2]

    def _generate_deep_dive_queries(self, topic: str) -> List[str]:
        """Generate queries for deep-dive research on a topic."""
        topic_queries = {
            "api_integration": [
                f"{topic} rate limits documentation",
                f"{topic} authentication methods",
                f"{topic} error handling best practices",
            ],
            "pricing": [
                f"{topic} detailed pricing breakdown",
                f"{topic} enterprise pricing",
                f"{topic} volume discounts",
            ],
            "compliance": [
                f"{topic} regulatory requirements",
                f"{topic} data privacy compliance",
                f"{topic} terms of service analysis",
            ],
            "security": [
                f"{topic} security best practices",
                f"{topic} vulnerability assessment",
                f"{topic} authentication security",
            ],
        }
        return topic_queries.get(topic, [f"{topic} deep analysis", f"{topic} comprehensive guide"])

    def _generate_resolution_queries(self, conflict: Dict) -> List[str]:
        """Generate queries to resolve conflicting information."""
        topics = conflict.get("topics", [])
        return [
            f"{' '.join(topics[:2])} authoritative source",
            f"{' '.join(topics[:2])} official documentation",
        ]

    def mark_addressed(self, trigger_id: str):
        """Mark a trigger as addressed."""
        self._addressed_triggers.add(trigger_id)

    def should_continue_followup(
        self,
        iteration: int,
        prev_results: Dict[str, Any],
        new_results: Dict[str, Any],
    ) -> bool:
        """
        Determine if follow-up research should continue.

        Args:
            iteration: Current iteration number (0-indexed)
            prev_results: Results from previous iteration
            new_results: Results from current iteration

        Returns:
            True if should continue, False otherwise
        """
        # Hard limit on iterations
        if iteration >= self.MAX_FOLLOWUP_ITERATIONS:
            return False

        # Check if meaningful new information gained
        new_info_ratio = self._calculate_new_info_ratio(prev_results, new_results)
        if new_info_ratio < self.MIN_NEW_INFORMATION_THRESHOLD:
            return False

        # Check if critical gaps remain
        triggers = self.analyze(new_results)
        critical_remaining = [
            t for t in triggers.selected_triggers if t.priority == TriggerPriority.CRITICAL
        ]
        if not critical_remaining:
            return False

        return True

    def _calculate_new_info_ratio(
        self,
        prev_results: Dict[str, Any],
        new_results: Dict[str, Any],
    ) -> float:
        """Calculate ratio of new information gained."""
        prev_findings = set(
            hashlib.md5(str(f).encode()).hexdigest()[:8] for f in prev_results.get("findings", [])
        )
        new_findings = set(
            hashlib.md5(str(f).encode()).hexdigest()[:8] for f in new_results.get("findings", [])
        )

        if not new_findings:
            return 0.0

        truly_new = new_findings - prev_findings
        return len(truly_new) / len(new_findings)

    # === IMP-HIGH-005: Callback Registration and Execution ===

    def register_callback(self, callback: TriggerCallback) -> None:
        """Register a synchronous callback for trigger execution.

        IMP-HIGH-005: Callbacks are invoked when `execute_triggers()` is called.
        Each callback receives a FollowupTrigger and should return optional
        result data (e.g., research findings).

        Args:
            callback: Function that takes a FollowupTrigger and returns
                     optional Dict with result data.

        Example:
            ```python
            def handle_research(trigger: FollowupTrigger) -> Optional[Dict]:
                # Perform research based on trigger.research_plan
                return {"findings": [...], "confidence": 0.8}

            trigger.register_callback(handle_research)
            ```
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)
            logger.debug(f"[IMP-HIGH-005] Registered callback (total: {len(self._callbacks)})")

    def register_async_callback(self, callback: AsyncTriggerCallback) -> None:
        """Register an asynchronous callback for trigger execution.

        IMP-HIGH-005: Async callbacks are invoked when `execute_triggers_async()`
        is called. They enable concurrent research execution.

        Args:
            callback: Async function that takes a FollowupTrigger and returns
                     optional Dict with result data.

        Example:
            ```python
            async def handle_research_async(trigger: FollowupTrigger) -> Optional[Dict]:
                # Perform async research
                result = await research_orchestrator.execute(trigger.research_plan)
                return {"findings": result.findings}

            trigger.register_async_callback(handle_research_async)
            ```
        """
        if callback not in self._async_callbacks:
            self._async_callbacks.append(callback)
            logger.debug(
                f"[IMP-HIGH-005] Registered async callback (total: {len(self._async_callbacks)})"
            )

    def unregister_callback(self, callback: TriggerCallback) -> bool:
        """Unregister a synchronous callback.

        Args:
            callback: The callback to unregister

        Returns:
            True if callback was found and removed, False otherwise
        """
        try:
            self._callbacks.remove(callback)
            logger.debug(
                f"[IMP-HIGH-005] Unregistered callback (remaining: {len(self._callbacks)})"
            )
            return True
        except ValueError:
            return False

    def unregister_async_callback(self, callback: AsyncTriggerCallback) -> bool:
        """Unregister an asynchronous callback.

        Args:
            callback: The async callback to unregister

        Returns:
            True if callback was found and removed, False otherwise
        """
        try:
            self._async_callbacks.remove(callback)
            logger.debug(
                f"[IMP-HIGH-005] Unregistered async callback "
                f"(remaining: {len(self._async_callbacks)})"
            )
            return True
        except ValueError:
            return False

    def get_callback_count(self) -> int:
        """Get total number of registered callbacks (sync + async).

        Returns:
            Total callback count
        """
        return len(self._callbacks) + len(self._async_callbacks)

    def execute_triggers(
        self,
        triggers: List[FollowupTrigger],
        stop_on_failure: bool = False,
    ) -> TriggerExecutionResult:
        """Execute all registered callbacks for the given triggers.

        IMP-HIGH-005: Invokes all registered synchronous callbacks for each
        trigger. Results are tracked and triggers are marked as addressed
        upon successful execution.

        Args:
            triggers: List of triggers to execute callbacks for
            stop_on_failure: If True, stop execution on first failure

        Returns:
            TriggerExecutionResult with execution summary and results

        Example:
            ```python
            result = trigger.analyze(analysis_results)
            if result.should_research:
                exec_result = trigger.execute_triggers(result.selected_triggers)
                print(f"Executed {exec_result.triggers_executed} triggers")
            ```
        """
        import time

        start_time = time.time()
        callback_results: List[CallbackResult] = []
        integrated_findings: List[Dict[str, Any]] = []
        successful = 0
        failed = 0

        if not self._callbacks:
            logger.warning("[IMP-HIGH-005] No callbacks registered for execution")
            return TriggerExecutionResult(
                triggers_executed=0,
                callbacks_invoked=0,
                successful_executions=0,
                failed_executions=0,
                total_execution_time_ms=0,
            )

        logger.info(
            f"[IMP-HIGH-005] Executing {len(self._callbacks)} callbacks "
            f"for {len(triggers)} triggers"
        )

        for trigger in triggers:
            if trigger.trigger_id in self._addressed_triggers:
                logger.debug(
                    f"[IMP-HIGH-005] Skipping already addressed trigger: {trigger.trigger_id}"
                )
                continue

            for callback in self._callbacks:
                cb_start = time.time()
                try:
                    result_data = callback(trigger)
                    cb_elapsed = int((time.time() - cb_start) * 1000)

                    cb_result = CallbackResult(
                        trigger_id=trigger.trigger_id,
                        success=True,
                        result_data=result_data,
                        execution_time_ms=cb_elapsed,
                    )
                    callback_results.append(cb_result)
                    trigger.mark_executed(cb_result)

                    if result_data:
                        integrated_findings.append(result_data)

                    successful += 1
                    self._addressed_triggers.add(trigger.trigger_id)

                    logger.debug(
                        f"[IMP-HIGH-005] Callback executed successfully for "
                        f"{trigger.trigger_id} ({cb_elapsed}ms)"
                    )

                except Exception as e:
                    cb_elapsed = int((time.time() - cb_start) * 1000)
                    cb_result = CallbackResult(
                        trigger_id=trigger.trigger_id,
                        success=False,
                        error_message=str(e),
                        execution_time_ms=cb_elapsed,
                    )
                    callback_results.append(cb_result)
                    trigger.mark_executed(cb_result)
                    failed += 1

                    logger.warning(f"[IMP-HIGH-005] Callback failed for {trigger.trigger_id}: {e}")

                    if stop_on_failure:
                        logger.info(
                            "[IMP-HIGH-005] Stopping execution due to failure "
                            "(stop_on_failure=True)"
                        )
                        break

            if stop_on_failure and failed > 0:
                break

        total_time_ms = int((time.time() - start_time) * 1000)

        result = TriggerExecutionResult(
            triggers_executed=len(triggers),
            callbacks_invoked=len(callback_results),
            successful_executions=successful,
            failed_executions=failed,
            total_execution_time_ms=total_time_ms,
            callback_results=callback_results,
            integrated_findings=integrated_findings,
        )

        logger.info(
            f"[IMP-HIGH-005] Execution complete: {successful} successful, "
            f"{failed} failed, {total_time_ms}ms total"
        )

        return result

    async def execute_triggers_async(
        self,
        triggers: List[FollowupTrigger],
        max_concurrent: int = 3,
        stop_on_failure: bool = False,
    ) -> TriggerExecutionResult:
        """Execute all registered async callbacks for the given triggers.

        IMP-HIGH-005: Invokes all registered asynchronous callbacks concurrently,
        up to max_concurrent at a time. Enables parallel research execution.

        Args:
            triggers: List of triggers to execute callbacks for
            max_concurrent: Maximum number of concurrent callback executions
            stop_on_failure: If True, stop execution on first failure

        Returns:
            TriggerExecutionResult with execution summary and results

        Example:
            ```python
            result = trigger.analyze(analysis_results)
            if result.should_research:
                exec_result = await trigger.execute_triggers_async(
                    result.selected_triggers,
                    max_concurrent=5
                )
                print(f"Executed {exec_result.triggers_executed} triggers")
            ```
        """
        import time

        start_time = time.time()
        callback_results: List[CallbackResult] = []
        integrated_findings: List[Dict[str, Any]] = []
        successful = 0
        failed = 0

        # Use both sync and async callbacks
        all_callbacks = self._callbacks + self._async_callbacks

        if not all_callbacks:
            logger.warning("[IMP-HIGH-005] No callbacks registered for async execution")
            return TriggerExecutionResult(
                triggers_executed=0,
                callbacks_invoked=0,
                successful_executions=0,
                failed_executions=0,
                total_execution_time_ms=0,
            )

        logger.info(
            f"[IMP-HIGH-005] Executing {len(all_callbacks)} callbacks "
            f"for {len(triggers)} triggers (max_concurrent={max_concurrent})"
        )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_single(
            trigger: FollowupTrigger, callback: Union[TriggerCallback, AsyncTriggerCallback]
        ) -> CallbackResult:
            """Execute a single callback with semaphore control."""
            async with semaphore:
                cb_start = time.time()
                try:
                    # Check if callback is async
                    if asyncio.iscoroutinefunction(callback):
                        result_data = await callback(trigger)
                    else:
                        # Run sync callback in executor
                        loop = asyncio.get_event_loop()
                        result_data = await loop.run_in_executor(None, callback, trigger)

                    cb_elapsed = int((time.time() - cb_start) * 1000)

                    return CallbackResult(
                        trigger_id=trigger.trigger_id,
                        success=True,
                        result_data=result_data,
                        execution_time_ms=cb_elapsed,
                    )

                except Exception as e:
                    cb_elapsed = int((time.time() - cb_start) * 1000)
                    return CallbackResult(
                        trigger_id=trigger.trigger_id,
                        success=False,
                        error_message=str(e),
                        execution_time_ms=cb_elapsed,
                    )

        # Execute all trigger-callback combinations
        tasks = []
        for trigger in triggers:
            if trigger.trigger_id in self._addressed_triggers:
                logger.debug(
                    f"[IMP-HIGH-005] Skipping already addressed trigger: {trigger.trigger_id}"
                )
                continue

            for callback in all_callbacks:
                tasks.append((trigger, execute_single(trigger, callback)))

        # Gather results
        should_stop = False
        for trigger, task in tasks:
            if should_stop:
                break

            try:
                result = await task
                callback_results.append(result)
                trigger.mark_executed(result)

                if result.success:
                    successful += 1
                    self._addressed_triggers.add(trigger.trigger_id)
                    if result.result_data:
                        integrated_findings.append(result.result_data)
                else:
                    failed += 1
                    if stop_on_failure:
                        logger.info("[IMP-HIGH-005] Stopping async execution due to failure")
                        should_stop = True

            except Exception as e:
                logger.error(f"[IMP-HIGH-005] Unexpected error in async execution: {e}")
                failed += 1
                if stop_on_failure:
                    should_stop = True

        total_time_ms = int((time.time() - start_time) * 1000)

        result = TriggerExecutionResult(
            triggers_executed=len(triggers),
            callbacks_invoked=len(callback_results),
            successful_executions=successful,
            failed_executions=failed,
            total_execution_time_ms=total_time_ms,
            callback_results=callback_results,
            integrated_findings=integrated_findings,
        )

        logger.info(
            f"[IMP-HIGH-005] Async execution complete: {successful} successful, "
            f"{failed} failed, {total_time_ms}ms total"
        )

        return result

    def analyze_and_execute(
        self,
        analysis_results: Dict[str, Any],
        validation_results: Optional[Dict[str, Any]] = None,
        previous_triggers: Optional[List[FollowupTrigger]] = None,
    ) -> TriggerAnalysisResult:
        """Analyze findings and execute callbacks in one operation.

        IMP-HIGH-005: Convenience method that combines `analyze()` and
        `execute_triggers()` into a single call. Use this for synchronous
        research triggering in the autonomy loop.

        Args:
            analysis_results: Results from analysis phase
            validation_results: Optional validation results
            previous_triggers: Triggers from previous iteration (for dedup)

        Returns:
            TriggerAnalysisResult with execution_result populated if
            callbacks were executed
        """
        result = self.analyze(
            analysis_results=analysis_results,
            validation_results=validation_results,
            previous_triggers=previous_triggers,
        )

        if result.should_research and self._callbacks:
            logger.info(
                f"[IMP-HIGH-005] Executing callbacks for "
                f"{result.triggers_selected} selected triggers"
            )
            execution_result = self.execute_triggers(result.selected_triggers)
            result.execution_result = execution_result

        return result

    async def analyze_and_execute_async(
        self,
        analysis_results: Dict[str, Any],
        validation_results: Optional[Dict[str, Any]] = None,
        previous_triggers: Optional[List[FollowupTrigger]] = None,
        max_concurrent: int = 3,
    ) -> TriggerAnalysisResult:
        """Analyze findings and execute async callbacks in one operation.

        IMP-HIGH-005: Async version of `analyze_and_execute()` that uses
        concurrent callback execution.

        Args:
            analysis_results: Results from analysis phase
            validation_results: Optional validation results
            previous_triggers: Triggers from previous iteration (for dedup)
            max_concurrent: Maximum concurrent callback executions

        Returns:
            TriggerAnalysisResult with execution_result populated if
            callbacks were executed
        """
        result = self.analyze(
            analysis_results=analysis_results,
            validation_results=validation_results,
            previous_triggers=previous_triggers,
        )

        if result.should_research and (self._callbacks or self._async_callbacks):
            logger.info(
                f"[IMP-HIGH-005] Executing async callbacks for "
                f"{result.triggers_selected} selected triggers"
            )
            execution_result = await self.execute_triggers_async(
                result.selected_triggers,
                max_concurrent=max_concurrent,
            )
            result.execution_result = execution_result

        return result
