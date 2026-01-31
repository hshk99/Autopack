"""Project History Analyzer for Cross-Project Learning.

Analyzes past project decisions, outcomes, and patterns from the learning
database and project artifacts. Extracts insights that can inform
recommendations for new projects.

This module provides the bridge between historical project data stored
in the learning database and the pattern extraction system, enabling
cross-project learning and pattern reuse.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from autopack.memory.learning_db import LearningDatabase

logger = logging.getLogger(__name__)


@dataclass
class ProjectDecision:
    """Represents a decision made in a project.

    Attributes:
        decision_id: Unique identifier for the decision.
        project_id: Project where decision was made.
        decision_type: Category of decision (tech_stack, architecture, etc.).
        choice: The actual choice made.
        rationale: Reasoning behind the decision.
        timestamp: When the decision was made.
        outcome: Result of the decision (successful, problematic, etc.).
        impact_score: Quantified impact (-1.0 to 1.0).
        related_decisions: IDs of related decisions.
        metadata: Additional context.
    """

    decision_id: str
    project_id: str
    decision_type: str
    choice: str
    rationale: str = ""
    timestamp: Optional[str] = None
    outcome: str = "unknown"
    impact_score: float = 0.0
    related_decisions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "decision_id": self.decision_id,
            "project_id": self.project_id,
            "decision_type": self.decision_type,
            "choice": self.choice,
            "rationale": self.rationale,
            "timestamp": self.timestamp,
            "outcome": self.outcome,
            "impact_score": self.impact_score,
            "related_decisions": self.related_decisions,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectDecision:
        """Create from dictionary."""
        return cls(
            decision_id=data.get("decision_id", ""),
            project_id=data.get("project_id", ""),
            decision_type=data.get("decision_type", ""),
            choice=data.get("choice", ""),
            rationale=data.get("rationale", ""),
            timestamp=data.get("timestamp"),
            outcome=data.get("outcome", "unknown"),
            impact_score=data.get("impact_score", 0.0),
            related_decisions=data.get("related_decisions", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ProjectSummary:
    """Summary of a project for historical analysis.

    Attributes:
        project_id: Unique project identifier.
        project_type: Type classification of the project.
        name: Human-readable project name.
        start_date: When the project started.
        end_date: When the project ended (if applicable).
        overall_outcome: Final outcome status.
        success_score: Quantified success (0.0 to 1.0).
        decisions: List of key decisions made.
        tech_stack: Technology stack used.
        architecture: Architecture decisions.
        monetization: Monetization strategy used.
        deployment: Deployment configuration.
        lessons_learned: Key lessons from the project.
        metadata: Additional project context.
    """

    project_id: str
    project_type: str
    name: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    overall_outcome: str = "unknown"
    success_score: float = 0.0
    decisions: list[ProjectDecision] = field(default_factory=list)
    tech_stack: dict[str, Any] = field(default_factory=dict)
    architecture: dict[str, Any] = field(default_factory=dict)
    monetization: dict[str, Any] = field(default_factory=dict)
    deployment: dict[str, Any] = field(default_factory=dict)
    lessons_learned: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "project_id": self.project_id,
            "project_type": self.project_type,
            "name": self.name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "overall_outcome": self.overall_outcome,
            "success_score": self.success_score,
            "decisions": [d.to_dict() for d in self.decisions],
            "tech_stack": self.tech_stack,
            "architecture": self.architecture,
            "monetization": self.monetization,
            "deployment": self.deployment,
            "lessons_learned": self.lessons_learned,
            "metadata": self.metadata,
        }


@dataclass
class HistoryAnalysisResult:
    """Result of project history analysis.

    Attributes:
        projects_analyzed: Number of projects analyzed.
        analysis_timestamp: When the analysis was performed.
        project_summaries: List of project summaries.
        decision_patterns: Common decision patterns found.
        success_correlations: Factors correlated with success.
        failure_correlations: Factors correlated with failure.
        category_insights: Insights by improvement category.
        recommendations: Generated recommendations from history.
    """

    projects_analyzed: int = 0
    analysis_timestamp: Optional[str] = None
    project_summaries: list[ProjectSummary] = field(default_factory=list)
    decision_patterns: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    success_correlations: list[dict[str, Any]] = field(default_factory=list)
    failure_correlations: list[dict[str, Any]] = field(default_factory=list)
    category_insights: dict[str, dict[str, Any]] = field(default_factory=dict)
    recommendations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "projects_analyzed": self.projects_analyzed,
            "analysis_timestamp": self.analysis_timestamp,
            "project_summaries": [p.to_dict() for p in self.project_summaries],
            "decision_patterns": self.decision_patterns,
            "success_correlations": self.success_correlations,
            "failure_correlations": self.failure_correlations,
            "category_insights": self.category_insights,
            "recommendations": self.recommendations,
        }


class ProjectHistoryAnalyzer:
    """Analyzes project history for cross-project learning.

    Processes historical project data from the learning database and
    project artifacts to extract insights that can inform recommendations
    for new projects.

    Attributes:
        learning_db: Optional learning database instance.
        project_history_path: Path to project history storage.
    """

    def __init__(
        self,
        learning_db: Optional[LearningDatabase] = None,
        project_history_path: Optional[Path] = None,
    ):
        """Initialize the ProjectHistoryAnalyzer.

        Args:
            learning_db: Optional LearningDatabase instance for querying.
            project_history_path: Optional path to project history JSON file.
        """
        self._learning_db = learning_db
        self._project_history_path = project_history_path
        self._project_cache: dict[str, ProjectSummary] = {}

    def set_learning_db(self, learning_db: LearningDatabase) -> None:
        """Set the learning database instance.

        Args:
            learning_db: LearningDatabase instance to use.
        """
        self._learning_db = learning_db
        logger.debug("Learning database connected to ProjectHistoryAnalyzer")

    def analyze_history(
        self,
        include_improvements: bool = True,
        include_cycles: bool = True,
        min_projects: int = 1,
    ) -> HistoryAnalysisResult:
        """Analyze project history and extract insights.

        Args:
            include_improvements: Whether to include improvement outcomes.
            include_cycles: Whether to include cycle metrics.
            min_projects: Minimum projects needed for analysis.

        Returns:
            HistoryAnalysisResult with analysis data.
        """
        logger.info("Analyzing project history")

        result = HistoryAnalysisResult(
            analysis_timestamp=datetime.now().isoformat(),
        )

        # Load project history from file if available
        file_projects = self._load_project_history_file()

        # Extract projects from learning database
        db_projects = self._extract_projects_from_learning_db(
            include_improvements, include_cycles
        )

        # Combine project sources
        all_projects = file_projects + db_projects
        result.projects_analyzed = len(all_projects)
        result.project_summaries = all_projects

        if len(all_projects) < min_projects:
            logger.warning(
                "Insufficient project history for analysis: %d < %d",
                len(all_projects),
                min_projects,
            )
            return result

        # Analyze decision patterns
        result.decision_patterns = self._analyze_decision_patterns(all_projects)

        # Find success correlations
        result.success_correlations = self._find_success_correlations(all_projects)

        # Find failure correlations
        result.failure_correlations = self._find_failure_correlations(all_projects)

        # Extract category insights from learning database
        if self._learning_db and include_improvements:
            result.category_insights = self._extract_category_insights()

        # Generate recommendations
        result.recommendations = self._generate_recommendations(result)

        logger.info(
            "Analysis complete: %d projects, %d decision patterns, %d correlations",
            result.projects_analyzed,
            len(result.decision_patterns),
            len(result.success_correlations) + len(result.failure_correlations),
        )

        return result

    def _load_project_history_file(self) -> list[ProjectSummary]:
        """Load project history from JSON file.

        Returns:
            List of ProjectSummary objects from file.
        """
        if not self._project_history_path or not self._project_history_path.exists():
            return []

        try:
            with open(self._project_history_path, encoding="utf-8") as f:
                data = json.load(f)

            projects = []
            for project_data in data.get("projects", []):
                summary = ProjectSummary(
                    project_id=project_data.get("project_id", ""),
                    project_type=project_data.get("project_type", "unknown"),
                    name=project_data.get("name", ""),
                    start_date=project_data.get("start_date"),
                    end_date=project_data.get("end_date"),
                    overall_outcome=project_data.get("outcome", "unknown"),
                    success_score=project_data.get("success_score", 0.0),
                    tech_stack=project_data.get("tech_stack", {}),
                    architecture=project_data.get("architecture", {}),
                    monetization=project_data.get("monetization", {}),
                    deployment=project_data.get("deployment", {}),
                    lessons_learned=project_data.get("lessons_learned", []),
                    metadata=project_data.get("metadata", {}),
                )

                # Parse decisions
                for decision_data in project_data.get("decisions", []):
                    decision = ProjectDecision.from_dict(decision_data)
                    summary.decisions.append(decision)

                projects.append(summary)

            logger.debug(
                "Loaded %d projects from history file: %s",
                len(projects),
                self._project_history_path,
            )
            return projects

        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load project history file: %s", e)
            return []

    def _extract_projects_from_learning_db(
        self,
        include_improvements: bool,
        include_cycles: bool,
    ) -> list[ProjectSummary]:
        """Extract project summaries from learning database.

        Args:
            include_improvements: Whether to include improvement outcomes.
            include_cycles: Whether to include cycle metrics.

        Returns:
            List of ProjectSummary objects from learning database.
        """
        if not self._learning_db:
            return []

        projects: list[ProjectSummary] = []

        # Extract from cycles if available
        if include_cycles:
            cycles = self._learning_db.list_cycles()
            for cycle in cycles:
                cycle_id = cycle.get("cycle_id", "")
                metrics = cycle.get("metrics", {})

                summary = ProjectSummary(
                    project_id=f"cycle-{cycle_id}",
                    project_type="improvement_cycle",
                    name=f"Cycle {cycle_id}",
                    start_date=cycle.get("recorded_at"),
                    success_score=metrics.get("completion_rate", 0.0),
                    overall_outcome=(
                        "successful"
                        if metrics.get("completion_rate", 0) >= 0.7
                        else "partial"
                    ),
                    metadata={
                        "phases_completed": metrics.get("phases_completed", 0),
                        "phases_blocked": metrics.get("phases_blocked", 0),
                        "total_nudges": metrics.get("total_nudges", 0),
                        "total_escalations": metrics.get("total_escalations", 0),
                    },
                )

                # Add blocking reasons as lessons learned
                for reason in cycle.get("blocking_reasons", []):
                    summary.lessons_learned.append(f"Blocked by: {reason}")

                projects.append(summary)

        # Extract insights from improvements
        if include_improvements:
            improvements = self._learning_db.list_improvements()
            category_groups: dict[str, list[dict[str, Any]]] = {}

            for imp in improvements:
                category = imp.get("category", "unknown")
                if category not in category_groups:
                    category_groups[category] = []
                category_groups[category].append(imp)

            # Create summary per category
            for category, imps in category_groups.items():
                successful = sum(
                    1 for i in imps if i.get("current_outcome") == "implemented"
                )
                total = len(imps)

                summary = ProjectSummary(
                    project_id=f"category-{category}",
                    project_type="improvement_category",
                    name=f"Category: {category}",
                    success_score=successful / total if total > 0 else 0.0,
                    overall_outcome=(
                        "successful" if successful / total >= 0.5 else "partial"
                    ),
                    metadata={
                        "total_improvements": total,
                        "successful": successful,
                        "blocked": sum(
                            1 for i in imps if i.get("current_outcome") == "blocked"
                        ),
                        "abandoned": sum(
                            1 for i in imps if i.get("current_outcome") == "abandoned"
                        ),
                    },
                )

                projects.append(summary)

        logger.debug("Extracted %d projects from learning database", len(projects))
        return projects

    def _analyze_decision_patterns(
        self, projects: list[ProjectSummary]
    ) -> dict[str, list[dict[str, Any]]]:
        """Analyze patterns in project decisions.

        Args:
            projects: List of project summaries to analyze.

        Returns:
            Dictionary mapping decision types to pattern data.
        """
        patterns: dict[str, list[dict[str, Any]]] = {
            "tech_stack": [],
            "architecture": [],
            "monetization": [],
            "deployment": [],
        }

        # Aggregate tech stack choices
        tech_stack_choices: dict[str, list[tuple[str, float]]] = {}
        for project in projects:
            for key, value in project.tech_stack.items():
                if isinstance(value, list):
                    for item in value:
                        if item not in tech_stack_choices:
                            tech_stack_choices[item] = []
                        tech_stack_choices[item].append(
                            (project.project_id, project.success_score)
                        )
                elif isinstance(value, str) and value:
                    if value not in tech_stack_choices:
                        tech_stack_choices[value] = []
                    tech_stack_choices[value].append(
                        (project.project_id, project.success_score)
                    )

        # Convert to patterns
        for choice, occurrences in tech_stack_choices.items():
            if len(occurrences) >= 1:
                avg_success = sum(o[1] for o in occurrences) / len(occurrences)
                patterns["tech_stack"].append(
                    {
                        "choice": choice,
                        "occurrence_count": len(occurrences),
                        "avg_success_score": round(avg_success, 3),
                        "projects": [o[0] for o in occurrences],
                    }
                )

        # Aggregate architecture patterns
        arch_patterns: dict[str, list[tuple[str, float]]] = {}
        for project in projects:
            arch_pattern = project.architecture.get("pattern", "")
            if arch_pattern:
                if arch_pattern not in arch_patterns:
                    arch_patterns[arch_pattern] = []
                arch_patterns[arch_pattern].append(
                    (project.project_id, project.success_score)
                )

        for pattern, occurrences in arch_patterns.items():
            if len(occurrences) >= 1:
                avg_success = sum(o[1] for o in occurrences) / len(occurrences)
                patterns["architecture"].append(
                    {
                        "pattern": pattern,
                        "occurrence_count": len(occurrences),
                        "avg_success_score": round(avg_success, 3),
                        "projects": [o[0] for o in occurrences],
                    }
                )

        # Sort patterns by success score
        for pattern_type in patterns:
            patterns[pattern_type].sort(
                key=lambda x: x.get("avg_success_score", 0), reverse=True
            )

        return patterns

    def _find_success_correlations(
        self, projects: list[ProjectSummary]
    ) -> list[dict[str, Any]]:
        """Find factors correlated with project success.

        Args:
            projects: List of project summaries.

        Returns:
            List of success correlation factors.
        """
        correlations: list[dict[str, Any]] = []

        successful_projects = [p for p in projects if p.success_score >= 0.7]
        all_projects = [p for p in projects if p.success_score > 0]

        if not successful_projects or not all_projects:
            return correlations

        # Analyze what successful projects have in common
        success_rate = len(successful_projects) / len(all_projects)

        # Check for common tech stack elements
        tech_elements: dict[str, int] = {}
        for project in successful_projects:
            for key, value in project.tech_stack.items():
                if isinstance(value, list):
                    for item in value:
                        tech_elements[item] = tech_elements.get(item, 0) + 1
                elif isinstance(value, str) and value:
                    tech_elements[value] = tech_elements.get(value, 0) + 1

        # Find elements that appear in majority of successful projects
        threshold = len(successful_projects) * 0.5
        for element, count in tech_elements.items():
            if count >= threshold:
                correlations.append(
                    {
                        "factor": element,
                        "factor_type": "tech_stack",
                        "success_correlation": round(
                            count / len(successful_projects), 3
                        ),
                        "occurrence_in_successful": count,
                        "total_successful": len(successful_projects),
                    }
                )

        # Check for common architecture patterns
        arch_patterns: dict[str, int] = {}
        for project in successful_projects:
            pattern = project.architecture.get("pattern", "")
            if pattern:
                arch_patterns[pattern] = arch_patterns.get(pattern, 0) + 1

        for pattern, count in arch_patterns.items():
            if count >= threshold:
                correlations.append(
                    {
                        "factor": pattern,
                        "factor_type": "architecture",
                        "success_correlation": round(
                            count / len(successful_projects), 3
                        ),
                        "occurrence_in_successful": count,
                        "total_successful": len(successful_projects),
                    }
                )

        # Sort by correlation strength
        correlations.sort(key=lambda x: x["success_correlation"], reverse=True)

        return correlations

    def _find_failure_correlations(
        self, projects: list[ProjectSummary]
    ) -> list[dict[str, Any]]:
        """Find factors correlated with project failure.

        Args:
            projects: List of project summaries.

        Returns:
            List of failure correlation factors.
        """
        correlations: list[dict[str, Any]] = []

        failed_projects = [p for p in projects if p.success_score < 0.4]
        all_projects = [p for p in projects if p.success_score >= 0]

        if not failed_projects or not all_projects:
            return correlations

        # Analyze lessons learned from failed projects
        lesson_counts: dict[str, int] = {}
        for project in failed_projects:
            for lesson in project.lessons_learned:
                # Extract key phrases from lessons
                lesson_key = lesson[:50]  # Truncate for grouping
                lesson_counts[lesson_key] = lesson_counts.get(lesson_key, 0) + 1

        # Find common failure patterns
        threshold = len(failed_projects) * 0.3
        for lesson, count in lesson_counts.items():
            if count >= max(2, threshold):
                correlations.append(
                    {
                        "factor": lesson,
                        "factor_type": "lesson_learned",
                        "failure_correlation": round(count / len(failed_projects), 3),
                        "occurrence_in_failed": count,
                        "total_failed": len(failed_projects),
                    }
                )

        # Sort by correlation strength
        correlations.sort(key=lambda x: x["failure_correlation"], reverse=True)

        return correlations

    def _extract_category_insights(self) -> dict[str, dict[str, Any]]:
        """Extract insights by improvement category from learning database.

        Returns:
            Dictionary mapping categories to insight data.
        """
        if not self._learning_db:
            return {}

        insights: dict[str, dict[str, Any]] = {}

        # Get category success rates from learning database
        patterns = self._learning_db.get_historical_patterns()
        category_rates = patterns.get("category_success_rates", {})

        for category, stats in category_rates.items():
            insights[category] = {
                "total_improvements": stats.get("total", 0),
                "success_rate": stats.get("success_rate", 0),
                "implemented": stats.get("implemented", 0),
                "blocked": stats.get("blocked", 0),
                "abandoned": stats.get("abandoned", 0),
                "likely_blockers": self._learning_db.get_likely_blockers(category),
            }

        return insights

    def _generate_recommendations(
        self, analysis: HistoryAnalysisResult
    ) -> list[dict[str, Any]]:
        """Generate recommendations from analysis results.

        Args:
            analysis: HistoryAnalysisResult with patterns and correlations.

        Returns:
            List of recommendation dictionaries.
        """
        recommendations: list[dict[str, Any]] = []

        # Recommend high-success tech stack choices
        tech_patterns = analysis.decision_patterns.get("tech_stack", [])
        for pattern in tech_patterns[:5]:  # Top 5
            if pattern.get("avg_success_score", 0) >= 0.7:
                recommendations.append(
                    {
                        "type": "tech_stack",
                        "recommendation": f"Consider using {pattern['choice']}",
                        "confidence": "high"
                        if pattern.get("occurrence_count", 0) >= 3
                        else "medium",
                        "basis": f"Success rate: {pattern['avg_success_score']:.0%} across {pattern['occurrence_count']} projects",
                    }
                )

        # Recommend architecture patterns
        arch_patterns = analysis.decision_patterns.get("architecture", [])
        for pattern in arch_patterns[:3]:
            if pattern.get("avg_success_score", 0) >= 0.6:
                recommendations.append(
                    {
                        "type": "architecture",
                        "recommendation": f"Consider {pattern['pattern']} architecture",
                        "confidence": "medium",
                        "basis": f"Success rate: {pattern['avg_success_score']:.0%} across {pattern['occurrence_count']} projects",
                    }
                )

        # Add warnings based on failure correlations
        for correlation in analysis.failure_correlations[:3]:
            recommendations.append(
                {
                    "type": "warning",
                    "recommendation": f"Watch out for: {correlation['factor']}",
                    "confidence": "medium",
                    "basis": f"Associated with {correlation['failure_correlation']:.0%} of failed projects",
                }
            )

        return recommendations

    def get_project_by_type(
        self, analysis_result: HistoryAnalysisResult, project_type: str
    ) -> list[ProjectSummary]:
        """Get projects of a specific type from analysis results.

        Args:
            analysis_result: HistoryAnalysisResult from analyze_history().
            project_type: Type of project to filter.

        Returns:
            List of matching project summaries.
        """
        return [
            p
            for p in analysis_result.project_summaries
            if p.project_type.lower() == project_type.lower()
        ]

    def get_successful_patterns_for_type(
        self, analysis_result: HistoryAnalysisResult, project_type: str
    ) -> dict[str, list[dict[str, Any]]]:
        """Get successful patterns for a specific project type.

        Args:
            analysis_result: HistoryAnalysisResult from analyze_history().
            project_type: Type of project to analyze.

        Returns:
            Dictionary of pattern types to successful patterns.
        """
        type_projects = self.get_project_by_type(analysis_result, project_type)

        if not type_projects:
            return {}

        # Reanalyze patterns for just this project type
        return self._analyze_decision_patterns(type_projects)

    def save_project_summary(
        self, summary: ProjectSummary, append: bool = True
    ) -> bool:
        """Save a project summary to the history file.

        Args:
            summary: ProjectSummary to save.
            append: Whether to append (True) or overwrite (False).

        Returns:
            True if save was successful.
        """
        if not self._project_history_path:
            logger.warning("No project history path configured")
            return False

        try:
            # Load existing data if appending
            existing_data: dict[str, Any] = {"projects": []}
            if append and self._project_history_path.exists():
                with open(self._project_history_path, encoding="utf-8") as f:
                    existing_data = json.load(f)

            # Add/update project
            projects = existing_data.get("projects", [])

            # Remove existing entry for same project_id
            projects = [p for p in projects if p.get("project_id") != summary.project_id]

            # Add new entry
            projects.append(summary.to_dict())

            existing_data["projects"] = projects
            existing_data["updated_at"] = datetime.now().isoformat()

            # Ensure parent directory exists
            self._project_history_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self._project_history_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)

            logger.info("Saved project summary: %s", summary.project_id)
            return True

        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to save project summary: %s", e)
            return False
