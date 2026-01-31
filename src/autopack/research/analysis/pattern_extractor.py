"""Pattern Extractor for Cross-Project Learning.

Extracts successful patterns from past project decisions and outcomes.
Identifies recurring patterns in tech stack choices, architecture decisions,
monetization strategies, and deployment configurations that correlate with
successful project outcomes.

This module bridges historical learning data to actionable recommendations
for new projects by identifying patterns that have proven successful.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Types of patterns that can be extracted."""

    TECH_STACK = "tech_stack"
    ARCHITECTURE = "architecture"
    MONETIZATION = "monetization"
    DEPLOYMENT = "deployment"
    TESTING = "testing"
    INTEGRATION = "integration"
    WORKFLOW = "workflow"


class PatternConfidence(Enum):
    """Confidence level of extracted patterns."""

    HIGH = "high"  # 5+ successful occurrences
    MEDIUM = "medium"  # 3-4 successful occurrences
    LOW = "low"  # 1-2 successful occurrences
    EXPERIMENTAL = "experimental"  # New pattern, limited data


class ProjectOutcome(Enum):
    """Project outcome classification."""

    SUCCESSFUL = "successful"
    PARTIAL = "partial"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"


@dataclass
class ExtractedPattern:
    """Represents an extracted pattern from project history.

    Attributes:
        pattern_id: Unique identifier for the pattern.
        pattern_type: Type of pattern (tech_stack, architecture, etc.).
        name: Human-readable name for the pattern.
        description: Detailed description of the pattern.
        context: Project context where this pattern applies.
        components: Specific components or elements that make up the pattern.
        success_rate: Ratio of successful applications (0.0-1.0).
        occurrence_count: Number of times this pattern has been observed.
        confidence: Confidence level based on occurrence count.
        associated_project_types: Project types where this pattern excels.
        success_factors: Factors that contribute to pattern success.
        risk_factors: Factors that may cause pattern to fail.
        recommended_for: List of scenario keywords where pattern is recommended.
        avoid_for: List of scenario keywords where pattern should be avoided.
        first_seen: When the pattern was first observed.
        last_seen: When the pattern was last observed.
        metadata: Additional pattern-specific metadata.
    """

    pattern_id: str
    pattern_type: PatternType
    name: str
    description: str
    context: str = ""
    components: list[str] = field(default_factory=list)
    success_rate: float = 0.0
    occurrence_count: int = 0
    confidence: PatternConfidence = PatternConfidence.LOW
    associated_project_types: list[str] = field(default_factory=list)
    success_factors: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    recommended_for: list[str] = field(default_factory=list)
    avoid_for: list[str] = field(default_factory=list)
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type.value,
            "name": self.name,
            "description": self.description,
            "context": self.context,
            "components": self.components,
            "success_rate": self.success_rate,
            "occurrence_count": self.occurrence_count,
            "confidence": self.confidence.value,
            "associated_project_types": self.associated_project_types,
            "success_factors": self.success_factors,
            "risk_factors": self.risk_factors,
            "recommended_for": self.recommended_for,
            "avoid_for": self.avoid_for,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedPattern:
        """Create from dictionary representation."""
        return cls(
            pattern_id=data.get("pattern_id", ""),
            pattern_type=PatternType(data.get("pattern_type", "tech_stack")),
            name=data.get("name", ""),
            description=data.get("description", ""),
            context=data.get("context", ""),
            components=data.get("components", []),
            success_rate=data.get("success_rate", 0.0),
            occurrence_count=data.get("occurrence_count", 0),
            confidence=PatternConfidence(data.get("confidence", "low")),
            associated_project_types=data.get("associated_project_types", []),
            success_factors=data.get("success_factors", []),
            risk_factors=data.get("risk_factors", []),
            recommended_for=data.get("recommended_for", []),
            avoid_for=data.get("avoid_for", []),
            first_seen=data.get("first_seen"),
            last_seen=data.get("last_seen"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PatternExtractionResult:
    """Result of pattern extraction analysis.

    Attributes:
        patterns: List of extracted patterns.
        total_projects_analyzed: Number of projects used for extraction.
        extraction_timestamp: When the extraction was performed.
        coverage_by_type: Pattern count by type.
        top_patterns: Highest confidence patterns.
        emerging_patterns: Recently observed patterns with limited data.
        deprecated_patterns: Patterns with declining success rates.
    """

    patterns: list[ExtractedPattern] = field(default_factory=list)
    total_projects_analyzed: int = 0
    extraction_timestamp: Optional[str] = None
    coverage_by_type: dict[str, int] = field(default_factory=dict)
    top_patterns: list[ExtractedPattern] = field(default_factory=list)
    emerging_patterns: list[ExtractedPattern] = field(default_factory=list)
    deprecated_patterns: list[ExtractedPattern] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "patterns": [p.to_dict() for p in self.patterns],
            "total_projects_analyzed": self.total_projects_analyzed,
            "extraction_timestamp": self.extraction_timestamp,
            "coverage_by_type": self.coverage_by_type,
            "top_patterns": [p.to_dict() for p in self.top_patterns],
            "emerging_patterns": [p.to_dict() for p in self.emerging_patterns],
            "deprecated_patterns": [p.to_dict() for p in self.deprecated_patterns],
        }


class PatternExtractor:
    """Extracts successful patterns from historical project data.

    Analyzes past project decisions and outcomes to identify patterns
    that correlate with successful projects. Uses learning database
    data to extract actionable patterns for new project recommendations.

    Attributes:
        min_occurrences_for_pattern: Minimum observations to consider a pattern.
        success_threshold: Minimum success rate to consider pattern successful.
        recency_weight: Weight given to recent observations (0-1).
    """

    def __init__(
        self,
        min_occurrences_for_pattern: int = 2,
        success_threshold: float = 0.6,
        recency_weight: float = 0.3,
    ):
        """Initialize the PatternExtractor.

        Args:
            min_occurrences_for_pattern: Minimum occurrences to extract pattern.
            success_threshold: Minimum success rate for pattern consideration.
            recency_weight: Weight for recent data in pattern scoring.
        """
        self.min_occurrences_for_pattern = min_occurrences_for_pattern
        self.success_threshold = success_threshold
        self.recency_weight = recency_weight
        self._pattern_cache: dict[str, ExtractedPattern] = {}

    def extract_patterns(
        self,
        project_history: list[dict[str, Any]],
        improvement_outcomes: dict[str, dict[str, Any]],
        cycle_data: dict[str, dict[str, Any]],
    ) -> PatternExtractionResult:
        """Extract patterns from historical project data.

        Args:
            project_history: List of project records with decisions and outcomes.
            improvement_outcomes: Map of improvement ID to outcome data.
            cycle_data: Map of cycle ID to cycle metrics.

        Returns:
            PatternExtractionResult with extracted patterns.
        """
        logger.info(
            "Extracting patterns from %d projects, %d improvements, %d cycles",
            len(project_history),
            len(improvement_outcomes),
            len(cycle_data),
        )

        result = PatternExtractionResult(
            extraction_timestamp=datetime.now().isoformat(),
            total_projects_analyzed=len(project_history),
        )

        # Extract patterns by type
        tech_stack_patterns = self._extract_tech_stack_patterns(project_history)
        architecture_patterns = self._extract_architecture_patterns(project_history)
        monetization_patterns = self._extract_monetization_patterns(project_history)
        deployment_patterns = self._extract_deployment_patterns(project_history)
        workflow_patterns = self._extract_workflow_patterns(
            improvement_outcomes, cycle_data
        )

        # Combine all patterns
        all_patterns = (
            tech_stack_patterns
            + architecture_patterns
            + monetization_patterns
            + deployment_patterns
            + workflow_patterns
        )

        result.patterns = all_patterns

        # Calculate coverage by type
        for pattern in all_patterns:
            type_key = pattern.pattern_type.value
            result.coverage_by_type[type_key] = (
                result.coverage_by_type.get(type_key, 0) + 1
            )

        # Identify top patterns (high confidence, high success rate)
        result.top_patterns = [
            p
            for p in all_patterns
            if p.confidence in (PatternConfidence.HIGH, PatternConfidence.MEDIUM)
            and p.success_rate >= self.success_threshold
        ]
        result.top_patterns.sort(key=lambda p: p.success_rate, reverse=True)

        # Identify emerging patterns (low confidence but positive signals)
        result.emerging_patterns = [
            p
            for p in all_patterns
            if p.confidence == PatternConfidence.EXPERIMENTAL
            and p.success_rate >= 0.5
        ]

        # Identify deprecated patterns (declining success rate)
        result.deprecated_patterns = [
            p
            for p in all_patterns
            if p.occurrence_count >= self.min_occurrences_for_pattern
            and p.success_rate < 0.4
        ]

        logger.info(
            "Extracted %d patterns: %d top, %d emerging, %d deprecated",
            len(all_patterns),
            len(result.top_patterns),
            len(result.emerging_patterns),
            len(result.deprecated_patterns),
        )

        return result

    def _extract_tech_stack_patterns(
        self, project_history: list[dict[str, Any]]
    ) -> list[ExtractedPattern]:
        """Extract technology stack patterns from project history.

        Args:
            project_history: List of project records.

        Returns:
            List of extracted tech stack patterns.
        """
        patterns: list[ExtractedPattern] = []
        stack_occurrences: dict[str, list[dict[str, Any]]] = {}

        for project in project_history:
            tech_stack = project.get("tech_stack", {})
            outcome = project.get("outcome", "unknown")
            project_type = project.get("project_type", "unknown")

            # Create stack signature from components
            components = []
            components.extend(tech_stack.get("languages", []))
            components.extend(tech_stack.get("frameworks", []))
            components.extend(tech_stack.get("databases", []))

            if not components:
                continue

            stack_key = "-".join(sorted(components))

            if stack_key not in stack_occurrences:
                stack_occurrences[stack_key] = []

            stack_occurrences[stack_key].append(
                {
                    "outcome": outcome,
                    "project_type": project_type,
                    "components": components,
                    "timestamp": project.get("timestamp", ""),
                }
            )

        # Convert occurrences to patterns
        for stack_key, occurrences in stack_occurrences.items():
            if len(occurrences) < self.min_occurrences_for_pattern:
                continue

            success_count = sum(
                1 for o in occurrences if o["outcome"] in ("successful", "implemented")
            )
            success_rate = success_count / len(occurrences)

            pattern = ExtractedPattern(
                pattern_id=f"tech-{stack_key[:16]}",
                pattern_type=PatternType.TECH_STACK,
                name=f"Stack: {', '.join(occurrences[0]['components'][:3])}",
                description=f"Technology stack pattern with {len(occurrences)} occurrences",
                components=occurrences[0]["components"],
                success_rate=round(success_rate, 3),
                occurrence_count=len(occurrences),
                confidence=self._calculate_confidence(len(occurrences)),
                associated_project_types=list(
                    {o["project_type"] for o in occurrences if o["project_type"]}
                ),
                first_seen=min((o["timestamp"] for o in occurrences if o["timestamp"]), default=None),
                last_seen=max((o["timestamp"] for o in occurrences if o["timestamp"]), default=None),
            )

            patterns.append(pattern)

        return patterns

    def _extract_architecture_patterns(
        self, project_history: list[dict[str, Any]]
    ) -> list[ExtractedPattern]:
        """Extract architecture decision patterns from project history.

        Args:
            project_history: List of project records.

        Returns:
            List of extracted architecture patterns.
        """
        patterns: list[ExtractedPattern] = []
        arch_occurrences: dict[str, list[dict[str, Any]]] = {}

        for project in project_history:
            architecture = project.get("architecture", {})
            outcome = project.get("outcome", "unknown")
            project_type = project.get("project_type", "unknown")

            pattern_name = architecture.get("pattern", "")
            if not pattern_name:
                continue

            if pattern_name not in arch_occurrences:
                arch_occurrences[pattern_name] = []

            arch_occurrences[pattern_name].append(
                {
                    "outcome": outcome,
                    "project_type": project_type,
                    "components": architecture.get("components", []),
                    "decisions": architecture.get("decisions", []),
                    "timestamp": project.get("timestamp", ""),
                }
            )

        # Convert to patterns
        for arch_name, occurrences in arch_occurrences.items():
            if len(occurrences) < self.min_occurrences_for_pattern:
                continue

            success_count = sum(
                1 for o in occurrences if o["outcome"] in ("successful", "implemented")
            )
            success_rate = success_count / len(occurrences)

            # Extract common decisions
            all_decisions = []
            for o in occurrences:
                all_decisions.extend(o.get("decisions", []))

            pattern = ExtractedPattern(
                pattern_id=f"arch-{arch_name.lower().replace(' ', '-')[:16]}",
                pattern_type=PatternType.ARCHITECTURE,
                name=f"Architecture: {arch_name}",
                description=f"Architecture pattern '{arch_name}' with {len(occurrences)} applications",
                context=arch_name,
                success_rate=round(success_rate, 3),
                occurrence_count=len(occurrences),
                confidence=self._calculate_confidence(len(occurrences)),
                associated_project_types=list(
                    {o["project_type"] for o in occurrences if o["project_type"]}
                ),
                success_factors=list(set(all_decisions))[:5],
                first_seen=min((o["timestamp"] for o in occurrences if o["timestamp"]), default=None),
                last_seen=max((o["timestamp"] for o in occurrences if o["timestamp"]), default=None),
            )

            patterns.append(pattern)

        return patterns

    def _extract_monetization_patterns(
        self, project_history: list[dict[str, Any]]
    ) -> list[ExtractedPattern]:
        """Extract monetization strategy patterns from project history.

        Args:
            project_history: List of project records.

        Returns:
            List of extracted monetization patterns.
        """
        patterns: list[ExtractedPattern] = []
        mon_occurrences: dict[str, list[dict[str, Any]]] = {}

        for project in project_history:
            monetization = project.get("monetization", {})
            outcome = project.get("outcome", "unknown")
            project_type = project.get("project_type", "unknown")

            model = monetization.get("model", "")
            if not model:
                continue

            if model not in mon_occurrences:
                mon_occurrences[model] = []

            mon_occurrences[model].append(
                {
                    "outcome": outcome,
                    "project_type": project_type,
                    "pricing": monetization.get("pricing", {}),
                    "revenue": monetization.get("revenue", 0),
                    "timestamp": project.get("timestamp", ""),
                }
            )

        # Convert to patterns
        for model_name, occurrences in mon_occurrences.items():
            if len(occurrences) < self.min_occurrences_for_pattern:
                continue

            success_count = sum(
                1 for o in occurrences if o["outcome"] in ("successful", "implemented")
            )
            success_rate = success_count / len(occurrences)

            pattern = ExtractedPattern(
                pattern_id=f"mon-{model_name.lower().replace(' ', '-')[:16]}",
                pattern_type=PatternType.MONETIZATION,
                name=f"Monetization: {model_name}",
                description=f"Monetization model '{model_name}' with {len(occurrences)} applications",
                context=model_name,
                success_rate=round(success_rate, 3),
                occurrence_count=len(occurrences),
                confidence=self._calculate_confidence(len(occurrences)),
                associated_project_types=list(
                    {o["project_type"] for o in occurrences if o["project_type"]}
                ),
                recommended_for=[model_name.lower(), "revenue", "pricing"],
                first_seen=min((o["timestamp"] for o in occurrences if o["timestamp"]), default=None),
                last_seen=max((o["timestamp"] for o in occurrences if o["timestamp"]), default=None),
            )

            patterns.append(pattern)

        return patterns

    def _extract_deployment_patterns(
        self, project_history: list[dict[str, Any]]
    ) -> list[ExtractedPattern]:
        """Extract deployment configuration patterns from project history.

        Args:
            project_history: List of project records.

        Returns:
            List of extracted deployment patterns.
        """
        patterns: list[ExtractedPattern] = []
        deploy_occurrences: dict[str, list[dict[str, Any]]] = {}

        for project in project_history:
            deployment = project.get("deployment", {})
            outcome = project.get("outcome", "unknown")
            project_type = project.get("project_type", "unknown")

            platform = deployment.get("platform", "")
            if not platform:
                continue

            if platform not in deploy_occurrences:
                deploy_occurrences[platform] = []

            deploy_occurrences[platform].append(
                {
                    "outcome": outcome,
                    "project_type": project_type,
                    "config": deployment.get("config", {}),
                    "cicd": deployment.get("cicd", ""),
                    "timestamp": project.get("timestamp", ""),
                }
            )

        # Convert to patterns
        for platform_name, occurrences in deploy_occurrences.items():
            if len(occurrences) < self.min_occurrences_for_pattern:
                continue

            success_count = sum(
                1 for o in occurrences if o["outcome"] in ("successful", "implemented")
            )
            success_rate = success_count / len(occurrences)

            # Extract common CI/CD configurations
            cicd_configs = [o["cicd"] for o in occurrences if o["cicd"]]

            pattern = ExtractedPattern(
                pattern_id=f"dep-{platform_name.lower().replace(' ', '-')[:16]}",
                pattern_type=PatternType.DEPLOYMENT,
                name=f"Deployment: {platform_name}",
                description=f"Deployment to '{platform_name}' with {len(occurrences)} applications",
                context=platform_name,
                components=list(set(cicd_configs))[:3],
                success_rate=round(success_rate, 3),
                occurrence_count=len(occurrences),
                confidence=self._calculate_confidence(len(occurrences)),
                associated_project_types=list(
                    {o["project_type"] for o in occurrences if o["project_type"]}
                ),
                first_seen=min((o["timestamp"] for o in occurrences if o["timestamp"]), default=None),
                last_seen=max((o["timestamp"] for o in occurrences if o["timestamp"]), default=None),
            )

            patterns.append(pattern)

        return patterns

    def _extract_workflow_patterns(
        self,
        improvement_outcomes: dict[str, dict[str, Any]],
        cycle_data: dict[str, dict[str, Any]],
    ) -> list[ExtractedPattern]:
        """Extract workflow patterns from improvement and cycle data.

        Args:
            improvement_outcomes: Map of improvement ID to outcome data.
            cycle_data: Map of cycle ID to cycle metrics.

        Returns:
            List of extracted workflow patterns.
        """
        patterns: list[ExtractedPattern] = []
        category_stats: dict[str, dict[str, Any]] = {}

        # Analyze improvement outcomes by category
        for imp_id, imp_data in improvement_outcomes.items():
            category = imp_data.get("category", "unknown")
            outcome = imp_data.get("current_outcome", "unknown")

            if category not in category_stats:
                category_stats[category] = {
                    "total": 0,
                    "successful": 0,
                    "blocked": 0,
                    "reasons": [],
                }

            category_stats[category]["total"] += 1

            if outcome in ("implemented",):
                category_stats[category]["successful"] += 1
            elif outcome == "blocked":
                category_stats[category]["blocked"] += 1
                # Collect blocking reasons
                for entry in imp_data.get("outcome_history", []):
                    if entry.get("outcome") == "blocked" and entry.get("notes"):
                        category_stats[category]["reasons"].append(entry["notes"])

        # Convert category stats to workflow patterns
        for category, stats in category_stats.items():
            if stats["total"] < self.min_occurrences_for_pattern:
                continue

            success_rate = stats["successful"] / stats["total"]

            # Identify common blocking reasons
            risk_factors = []
            if stats["reasons"]:
                from collections import Counter

                reason_counts = Counter(stats["reasons"])
                risk_factors = [r for r, _ in reason_counts.most_common(3)]

            pattern = ExtractedPattern(
                pattern_id=f"wf-{category.lower()[:16]}",
                pattern_type=PatternType.WORKFLOW,
                name=f"Workflow: {category.title()} improvements",
                description=f"Improvement workflow for '{category}' category",
                context=category,
                success_rate=round(success_rate, 3),
                occurrence_count=stats["total"],
                confidence=self._calculate_confidence(stats["total"]),
                risk_factors=risk_factors,
                metadata={
                    "total_improvements": stats["total"],
                    "successful": stats["successful"],
                    "blocked": stats["blocked"],
                },
            )

            patterns.append(pattern)

        # Extract patterns from cycle completion rates
        if cycle_data:
            completion_rates = [
                c.get("metrics", {}).get("completion_rate", 0)
                for c in cycle_data.values()
            ]
            if completion_rates:
                avg_completion = sum(completion_rates) / len(completion_rates)

                pattern = ExtractedPattern(
                    pattern_id="wf-cycle-completion",
                    pattern_type=PatternType.WORKFLOW,
                    name="Cycle Completion Pattern",
                    description=f"Average cycle completion rate: {avg_completion:.1%}",
                    success_rate=round(avg_completion, 3),
                    occurrence_count=len(completion_rates),
                    confidence=self._calculate_confidence(len(completion_rates)),
                    metadata={
                        "avg_completion_rate": round(avg_completion, 3),
                        "total_cycles": len(completion_rates),
                    },
                )
                patterns.append(pattern)

        return patterns

    def _calculate_confidence(self, occurrence_count: int) -> PatternConfidence:
        """Calculate confidence level based on occurrence count.

        Args:
            occurrence_count: Number of pattern occurrences.

        Returns:
            PatternConfidence level.
        """
        if occurrence_count >= 5:
            return PatternConfidence.HIGH
        elif occurrence_count >= 3:
            return PatternConfidence.MEDIUM
        elif occurrence_count >= self.min_occurrences_for_pattern:
            return PatternConfidence.LOW
        else:
            return PatternConfidence.EXPERIMENTAL

    def get_patterns_for_project_type(
        self,
        extraction_result: PatternExtractionResult,
        project_type: str,
    ) -> list[ExtractedPattern]:
        """Get patterns relevant to a specific project type.

        Args:
            extraction_result: Result from extract_patterns().
            project_type: Project type to filter for.

        Returns:
            List of relevant patterns sorted by success rate.
        """
        relevant = [
            p
            for p in extraction_result.patterns
            if not p.associated_project_types
            or project_type.lower() in [t.lower() for t in p.associated_project_types]
        ]

        # Sort by success rate and confidence
        relevant.sort(
            key=lambda p: (
                p.confidence == PatternConfidence.HIGH,
                p.success_rate,
            ),
            reverse=True,
        )

        return relevant

    def get_recommended_patterns(
        self,
        extraction_result: PatternExtractionResult,
        project_context: dict[str, Any],
    ) -> list[ExtractedPattern]:
        """Get pattern recommendations for a new project.

        Args:
            extraction_result: Result from extract_patterns().
            project_context: Context of the new project including type, requirements, etc.

        Returns:
            List of recommended patterns with highest relevance.
        """
        project_type = project_context.get("project_type", "")
        keywords = project_context.get("keywords", [])

        recommendations: list[ExtractedPattern] = []

        for pattern in extraction_result.patterns:
            relevance_score = 0.0

            # Check project type match
            if project_type:
                if project_type.lower() in [
                    t.lower() for t in pattern.associated_project_types
                ]:
                    relevance_score += 0.3

            # Check keyword matches in recommended_for
            for keyword in keywords:
                if keyword.lower() in [r.lower() for r in pattern.recommended_for]:
                    relevance_score += 0.2

            # Check avoid_for (negative match)
            for keyword in keywords:
                if keyword.lower() in [a.lower() for a in pattern.avoid_for]:
                    relevance_score -= 0.3

            # Factor in success rate and confidence
            relevance_score += pattern.success_rate * 0.3

            if pattern.confidence == PatternConfidence.HIGH:
                relevance_score += 0.2
            elif pattern.confidence == PatternConfidence.MEDIUM:
                relevance_score += 0.1

            if relevance_score > 0.3:  # Threshold for recommendation
                pattern.metadata["relevance_score"] = round(relevance_score, 3)
                recommendations.append(pattern)

        # Sort by relevance score
        recommendations.sort(
            key=lambda p: p.metadata.get("relevance_score", 0),
            reverse=True,
        )

        return recommendations[:10]  # Return top 10 recommendations
