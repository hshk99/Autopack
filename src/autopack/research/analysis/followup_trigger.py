"""
Follow-up Research Trigger for automated gap-filling research.

Analyzes research findings to identify areas requiring deeper investigation
and triggers targeted follow-up research automatically.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


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

    def to_dict(self) -> Dict[str, Any]:
        return {
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


class FollowupResearchTrigger:
    """
    Analyzes findings and triggers automated follow-up research.
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
