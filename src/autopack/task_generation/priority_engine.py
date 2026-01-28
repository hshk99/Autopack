"""Data-Driven Task Priority Engine.

Prioritizes tasks based on historical learnings:
- Past success rate by category/complexity
- Blocking pattern detection (skip likely blockers)
- Dependency chain optimization
- Task effectiveness feedback (IMP-LOOP-019)

This module bridges the memory->task_generation link in the self-improvement loop
by using historical outcomes to inform what tasks to work on next.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..memory.learning_db import LearningDatabase
    from ..telemetry.analyzer import TaskEffectivenessStats
    from .task_effectiveness_tracker import TaskEffectivenessTracker


@dataclass
class ExecutionPlanResult:
    """Result of execution plan computation.

    Attributes:
        ordered_tasks: Tasks sorted by optimal execution order.
        total_estimated_tokens: Total token cost for all tasks.
        dependency_graph: The computed dependency DAG.
        pareto_frontier_count: Number of tasks on the Pareto frontier.
        budget_constrained: Whether budget constraint was applied.
    """

    ordered_tasks: list[dict[str, Any]]
    total_estimated_tokens: float
    dependency_graph: dict[str, list[str]]
    pareto_frontier_count: int
    budget_constrained: bool


logger = logging.getLogger(__name__)

# Priority levels and their base scores
PRIORITY_BASE_SCORES: dict[str, float] = {
    "critical": 1.0,
    "high": 0.75,
    "medium": 0.5,
    "low": 0.25,
}

# Category patterns for extracting category from improvement IDs
CATEGORY_PATTERNS: dict[str, str] = {
    "TEL": "telemetry",
    "MEM": "memory",
    "TGN": "task_generation",
    "GEN": "generation",
    "LOG": "logging",
    "API": "api",
    "CI": "ci",
    "TEST": "testing",
    "DOC": "documentation",
    "PERF": "performance",
    "SEC": "security",
    "FIX": "bugfix",
}

# Complexity indicators that may affect success likelihood
COMPLEXITY_KEYWORDS: dict[str, float] = {
    "refactor": 0.85,  # Refactoring is usually successful
    "add": 0.90,  # Adding new features is straightforward
    "fix": 0.80,  # Bug fixes can be tricky
    "migrate": 0.60,  # Migrations are complex
    "rewrite": 0.50,  # Rewrites have high risk
    "integrate": 0.70,  # Integration work varies
    "optimize": 0.75,  # Optimization is moderately risky
    "remove": 0.95,  # Removal is usually simple
    "update": 0.85,  # Updates are usually safe
}


class PriorityEngine:
    """Data-driven task priority engine.

    Uses historical learning data to prioritize improvements based on:
    - Category success rates (e.g., "memory" improvements succeed 80% of the time)
    - Known blocking patterns (e.g., "dependency conflict" blocks 30% of tasks)
    - Complexity estimation from improvement descriptions
    - Recent trend analysis
    - Task effectiveness feedback from completion telemetry (IMP-LOOP-019)
    - Category effectiveness from TaskEffectivenessTracker (IMP-TASK-001)

    Attributes:
        learning_db: The learning database containing historical outcomes.
        effectiveness_stats: Optional task effectiveness stats for feedback closure.
        effectiveness_tracker: Optional TaskEffectivenessTracker for category effectiveness.
    """

    # Weight factors for priority calculation
    # IMP-LOOP-019: Adjusted weights to include effectiveness factor
    CATEGORY_SUCCESS_WEIGHT = 0.30
    BLOCKING_RISK_WEIGHT = 0.20
    PRIORITY_LEVEL_WEIGHT = 0.20
    COMPLEXITY_WEIGHT = 0.15
    EFFECTIVENESS_WEIGHT = 0.15  # IMP-LOOP-019: Weight for historical effectiveness

    # Thresholds
    HIGH_BLOCKING_RISK_THRESHOLD = 0.3
    LOW_SUCCESS_RATE_THRESHOLD = 0.4

    def __init__(
        self,
        learning_db: LearningDatabase,
        effectiveness_stats: Optional[TaskEffectivenessStats] = None,
        effectiveness_tracker: Optional[TaskEffectivenessTracker] = None,
    ) -> None:
        """Initialize the PriorityEngine.

        Args:
            learning_db: The learning database containing historical outcomes.
            effectiveness_stats: Optional task effectiveness stats for feedback
                closure (IMP-LOOP-019). If provided, historical task completion
                outcomes will factor into priority calculation.
            effectiveness_tracker: Optional TaskEffectivenessTracker for category
                effectiveness feedback (IMP-TASK-001). If provided, category-level
                effectiveness data will dynamically adjust priority weights.
        """
        self.learning_db = learning_db
        self._patterns_cache: dict[str, Any] | None = None
        self._effectiveness_stats = effectiveness_stats
        self._effectiveness_tracker = effectiveness_tracker

    def _get_cached_patterns(self) -> dict[str, Any]:
        """Get historical patterns, caching for performance."""
        if self._patterns_cache is None:
            self._patterns_cache = self.learning_db.get_historical_patterns()
        return self._patterns_cache

    def clear_cache(self) -> None:
        """Clear the cached patterns to force reload."""
        self._patterns_cache = None

    def set_effectiveness_stats(self, stats: TaskEffectivenessStats) -> None:
        """Set or update task effectiveness stats (IMP-LOOP-019).

        Call this method to provide updated effectiveness data from
        task completion telemetry. This enables the feedback loop
        where past task outcomes influence future prioritization.

        Args:
            stats: TaskEffectivenessStats from TelemetryAnalyzer.
        """
        self._effectiveness_stats = stats
        logger.debug(
            "[IMP-LOOP-019] Updated effectiveness stats: success_rate=%.1f%%, "
            "target_achievement_rate=%.1f%%",
            stats.success_rate * 100,
            stats.target_achievement_rate * 100,
        )

    def set_effectiveness_tracker(self, tracker: TaskEffectivenessTracker) -> None:
        """Set or update the TaskEffectivenessTracker (IMP-TASK-001).

        Call this method to connect the priority engine to a TaskEffectivenessTracker
        for category-level effectiveness feedback. This enables dynamic adjustment
        of priority weights based on historical category success rates.

        Args:
            tracker: TaskEffectivenessTracker instance for category effectiveness.
        """
        self._effectiveness_tracker = tracker
        # Clear cache to force recalculation with new effectiveness data
        self.clear_cache()
        logger.debug("[IMP-TASK-001] Connected effectiveness tracker to priority engine")

    def get_effectiveness_factor(self, improvement: dict[str, Any]) -> float:
        """Get effectiveness factor based on historical task outcomes.

        IMP-LOOP-019 + IMP-TASK-001: Calculates an effectiveness multiplier based
        on how well similar tasks have performed historically. This creates a
        feedback loop where task types with poor historical outcomes are deprioritized.

        The method combines data from two sources:
        1. TaskEffectivenessStats (telemetry-based, IMP-LOOP-019)
        2. TaskEffectivenessTracker (category-based, IMP-TASK-001)

        Args:
            improvement: The improvement record to evaluate.

        Returns:
            Effectiveness factor between 0.5 and 1.2:
            - 1.0: No historical data or average effectiveness
            - > 1.0: Above-average historical success (boosted priority)
            - < 1.0: Below-average historical success (reduced priority)
        """
        category = self._extract_category(improvement)
        priority_level = self._extract_priority_level(improvement)
        scores: list[float] = []

        # IMP-TASK-001: Get category effectiveness from TaskEffectivenessTracker
        if self._effectiveness_tracker is not None:
            # Check if we have data for this category (use -1.0 as sentinel for "no data")
            category_effectiveness = (
                self._effectiveness_tracker.get_category_effectiveness_with_history(
                    category, default=-1.0
                )
            )
            # Only use effectiveness if we have actual data (not the sentinel default)
            if category_effectiveness >= 0:
                scores.append(category_effectiveness)
                logger.debug(
                    "[IMP-TASK-001] Category effectiveness for %s (%s): %.2f%%",
                    improvement.get("imp_id", improvement.get("id", "unknown")),
                    category,
                    category_effectiveness * 100,
                )

        # IMP-LOOP-019: Get effectiveness from TaskEffectivenessStats (telemetry)
        if self._effectiveness_stats is not None:
            # Get effectiveness by type if available
            type_effectiveness = self._effectiveness_stats.effectiveness_by_type.get(category, {})
            type_success_rate = type_effectiveness.get("success_rate")
            type_target_rate = type_effectiveness.get("target_rate")

            # Get effectiveness by priority if available
            priority_effectiveness = self._effectiveness_stats.effectiveness_by_priority.get(
                priority_level, {}
            )
            priority_success_rate = priority_effectiveness.get("success_rate")
            priority_target_rate = priority_effectiveness.get("target_rate")

            if type_success_rate is not None:
                # Weight success rate (execution success) and target rate (goal achievement)
                type_score = type_success_rate * 0.6 + (type_target_rate or type_success_rate) * 0.4
                scores.append(type_score)

            if priority_success_rate is not None:
                priority_score = (
                    priority_success_rate * 0.6
                    + (priority_target_rate or priority_success_rate) * 0.4
                )
                scores.append(priority_score)

            # Fall back to overall success rate if no type/priority data
            if not scores and self._effectiveness_stats.success_rate > 0:
                scores.append(self._effectiveness_stats.success_rate)

        # No data from either source
        if not scores:
            return 1.0

        # Average the scores and normalize to a factor
        avg_effectiveness = sum(scores) / len(scores)

        # Scale to factor range [0.5, 1.2]
        # 0% effectiveness -> 0.5 factor (50% reduction)
        # 50% effectiveness -> 0.85 factor
        # 100% effectiveness -> 1.2 factor (20% boost)
        factor = 0.5 + (avg_effectiveness * 0.7)

        logger.debug(
            "[IMP-TASK-001] Effectiveness factor for %s: %.2f (category=%s, "
            "avg_effectiveness=%.2f%%, sources=%d)",
            improvement.get("imp_id", improvement.get("id", "unknown")),
            factor,
            category,
            avg_effectiveness * 100,
            len(scores),
        )

        return factor

    def _extract_category(self, improvement: dict[str, Any]) -> str:
        """Extract the category from an improvement record.

        Args:
            improvement: The improvement record.

        Returns:
            Category string (e.g., "telemetry", "memory").
        """
        # First check for explicit category field
        category = improvement.get("category")
        if category:
            return category.lower()

        # Try to extract from improvement ID (e.g., "IMP-TEL-001" -> "telemetry")
        imp_id = improvement.get("imp_id", improvement.get("id", ""))
        if imp_id:
            # Match patterns like IMP-TEL-001, IMP-MEM-002
            match = re.search(r"IMP-([A-Z]+)-\d+", str(imp_id).upper())
            if match:
                code = match.group(1)
                return CATEGORY_PATTERNS.get(code, code.lower())

        # Fallback to "general"
        return "general"

    def _extract_priority_level(self, improvement: dict[str, Any]) -> str:
        """Extract the priority level from an improvement record.

        Args:
            improvement: The improvement record.

        Returns:
            Priority level string (e.g., "critical", "high", "medium", "low").
        """
        priority = improvement.get("priority", "medium")
        priority_lower = str(priority).lower()

        if priority_lower in PRIORITY_BASE_SCORES:
            return priority_lower

        return "medium"

    def _estimate_complexity(self, improvement: dict[str, Any]) -> float:
        """Estimate complexity based on improvement description.

        Args:
            improvement: The improvement record.

        Returns:
            Complexity factor between 0.0 (very complex) and 1.0 (simple).
            Higher values indicate simpler tasks with higher success likelihood.
        """
        # Gather text fields to analyze
        text_fields = [
            str(improvement.get("title", "")),
            str(improvement.get("description", "")),
            str(improvement.get("problem", "")),
            str(improvement.get("implementation", "")),
        ]
        combined_text = " ".join(text_fields).lower()

        if not combined_text.strip():
            return 0.75  # Default to moderate complexity

        # Check for complexity keywords
        complexity_scores: list[float] = []
        for keyword, score in COMPLEXITY_KEYWORDS.items():
            if keyword in combined_text:
                complexity_scores.append(score)

        if complexity_scores:
            # Use average of all matching keywords
            return sum(complexity_scores) / len(complexity_scores)

        return 0.75  # Default

    def _calculate_blocking_risk(
        self, improvement: dict[str, Any], likely_blockers: list[dict[str, Any]]
    ) -> float:
        """Calculate the risk of blocking based on historical patterns.

        Args:
            improvement: The improvement record.
            likely_blockers: List of likely blocker records from learning DB.

        Returns:
            Blocking risk between 0.0 (no risk) and 1.0 (high risk).
        """
        if not likely_blockers:
            return 0.0

        # Check if any likely blockers match this improvement's characteristics
        category = self._extract_category(improvement)
        text_fields = [
            str(improvement.get("title", "")),
            str(improvement.get("description", "")),
            str(improvement.get("files_to_modify", "")),
        ]
        combined_text = " ".join(text_fields).lower()

        total_risk = 0.0
        matched_blockers = 0

        for blocker in likely_blockers:
            reason = str(blocker.get("reason", "")).lower()
            frequency = blocker.get("frequency", 1)
            likelihood = blocker.get("likelihood", "medium")

            # Check if this blocker reason might apply
            reason_applies = False

            # Check for keyword matches
            if any(word in combined_text for word in reason.split() if len(word) > 3):
                reason_applies = True

            # Check for category-specific blockers
            if category in reason:
                reason_applies = True

            if reason_applies:
                matched_blockers += 1
                # Weight by frequency and likelihood
                likelihood_weight = 0.8 if likelihood == "high" else 0.5
                total_risk += min(1.0, (frequency / 10) * likelihood_weight)

        if matched_blockers == 0:
            return 0.0

        # Normalize and cap at 1.0
        return min(1.0, total_risk / matched_blockers)

    def calculate_priority_score(self, improvement: dict[str, Any]) -> float:
        """Score improvement based on historical success likelihood.

        The score combines multiple factors:
        - Category success rate: How often improvements in this category succeed
        - Blocking risk: Likelihood of hitting known blockers
        - Priority level: The assigned priority (critical, high, medium, low)
        - Complexity estimate: Estimated complexity from description
        - Effectiveness factor: Historical task completion outcomes (IMP-LOOP-019)

        Args:
            improvement: The improvement record to score. Expected keys:
                - imp_id or id: Improvement identifier
                - priority: Priority level (critical, high, medium, low)
                - category: Optional explicit category
                - title, description: Text for complexity estimation

        Returns:
            Priority score between 0.0 and 1.0, where higher is better priority.
        """
        category = self._extract_category(improvement)
        priority_level = self._extract_priority_level(improvement)

        # Get category success rate
        category_success_rate = self.learning_db.get_success_rate(category)
        if category_success_rate == 0.0:
            # No historical data - use default
            category_success_rate = 0.5

        # Get likely blockers for this category
        likely_blockers = self.learning_db.get_likely_blockers(category)
        blocking_risk = self._calculate_blocking_risk(improvement, likely_blockers)

        # Get priority level base score
        priority_base = PRIORITY_BASE_SCORES.get(priority_level, 0.5)

        # Estimate complexity
        complexity_factor = self._estimate_complexity(improvement)

        # IMP-LOOP-019: Get effectiveness factor from task completion telemetry
        effectiveness_factor = self.get_effectiveness_factor(improvement)

        # Calculate weighted score
        # Higher category success rate -> higher score
        # Lower blocking risk -> higher score (invert the risk)
        # Higher priority level -> higher score
        # Higher complexity factor (simpler tasks) -> higher score
        # Higher effectiveness factor -> higher score (IMP-LOOP-019)
        score = (
            (category_success_rate * self.CATEGORY_SUCCESS_WEIGHT)
            + ((1.0 - blocking_risk) * self.BLOCKING_RISK_WEIGHT)
            + (priority_base * self.PRIORITY_LEVEL_WEIGHT)
            + (complexity_factor * self.COMPLEXITY_WEIGHT)
            + (effectiveness_factor * self.EFFECTIVENESS_WEIGHT)
        )

        logger.debug(
            "Priority score for %s: %.3f (category=%.2f, block_risk=%.2f, "
            "priority=%.2f, complexity=%.2f, effectiveness=%.2f)",
            improvement.get("imp_id", improvement.get("id", "unknown")),
            score,
            category_success_rate,
            blocking_risk,
            priority_base,
            complexity_factor,
            effectiveness_factor,
        )

        return round(score, 3)

    def rank_improvements(
        self,
        improvements: list[dict[str, Any]],
        include_scores: bool = False,
    ) -> list[dict[str, Any]]:
        """Return improvements sorted by data-driven priority.

        Args:
            improvements: List of improvement records to rank.
            include_scores: If True, add 'priority_score' field to each record.

        Returns:
            List of improvements sorted by priority score (highest first).
        """
        if not improvements:
            return []

        # Calculate scores and pair with improvements
        scored_improvements: list[tuple[float, dict[str, Any]]] = []

        for imp in improvements:
            score = self.calculate_priority_score(imp)
            if include_scores:
                imp = dict(imp)  # Copy to avoid mutating original
                imp["priority_score"] = score
            scored_improvements.append((score, imp))

        # Sort by score descending
        scored_improvements.sort(key=lambda x: x[0], reverse=True)

        ranked = [imp for _, imp in scored_improvements]

        logger.info(
            "Ranked %d improvements by data-driven priority",
            len(ranked),
        )

        return ranked

    def detect_likely_blockers(self, improvement: dict[str, Any]) -> list[str]:
        """Predict what might block this improvement.

        Analyzes the improvement against historical blocking patterns
        to identify potential blockers before starting work.

        Args:
            improvement: The improvement record to analyze.

        Returns:
            List of likely blocker descriptions.
        """
        category = self._extract_category(improvement)
        likely_blockers = self.learning_db.get_likely_blockers(category)

        if not likely_blockers:
            return []

        # Get improvement text for matching
        text_fields = [
            str(improvement.get("title", "")),
            str(improvement.get("description", "")),
            str(improvement.get("problem", "")),
            str(improvement.get("files_to_modify", "")),
        ]
        combined_text = " ".join(text_fields).lower()

        detected_blockers: list[str] = []

        for blocker in likely_blockers:
            reason = str(blocker.get("reason", ""))
            reason_lower = reason.lower()

            # Check for keyword matches
            keywords = [word for word in reason_lower.split() if len(word) > 3]
            matches = sum(1 for kw in keywords if kw in combined_text)

            # If enough keywords match, or category-specific blocker
            if matches >= 2 or category in reason_lower:
                frequency = blocker.get("frequency", 1)
                likelihood = blocker.get("likelihood", "medium")
                detected_blockers.append(
                    f"{reason} (frequency: {frequency}, likelihood: {likelihood})"
                )

        logger.debug(
            "Detected %d likely blockers for %s",
            len(detected_blockers),
            improvement.get("imp_id", improvement.get("id", "unknown")),
        )

        return detected_blockers

    def get_priority_summary(
        self,
        improvements: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate a summary of priority analysis for a set of improvements.

        Args:
            improvements: List of improvement records to analyze.

        Returns:
            Summary dictionary containing:
            - total_improvements: Total count
            - by_priority_level: Counts by priority level
            - by_category: Counts and avg scores by category
            - high_risk_items: Improvements with high blocking risk
            - recommended_order: Top 5 recommended improvements to work on
        """
        if not improvements:
            return {
                "total_improvements": 0,
                "by_priority_level": {},
                "by_category": {},
                "high_risk_items": [],
                "recommended_order": [],
            }

        by_priority: dict[str, int] = {}
        by_category: dict[str, dict[str, Any]] = {}
        high_risk_items: list[dict[str, Any]] = []

        for imp in improvements:
            # Count by priority level
            priority_level = self._extract_priority_level(imp)
            by_priority[priority_level] = by_priority.get(priority_level, 0) + 1

            # Analyze by category
            category = self._extract_category(imp)
            if category not in by_category:
                by_category[category] = {"count": 0, "scores": []}

            score = self.calculate_priority_score(imp)
            by_category[category]["count"] += 1
            by_category[category]["scores"].append(score)

            # Check for high blocking risk
            likely_blockers = self.learning_db.get_likely_blockers(category)
            blocking_risk = self._calculate_blocking_risk(imp, likely_blockers)
            if blocking_risk >= self.HIGH_BLOCKING_RISK_THRESHOLD:
                high_risk_items.append(
                    {
                        "imp_id": imp.get("imp_id", imp.get("id", "unknown")),
                        "blocking_risk": round(blocking_risk, 3),
                        "likely_blockers": self.detect_likely_blockers(imp)[:3],
                    }
                )

        # Calculate average scores by category
        for category, data in by_category.items():
            scores = data["scores"]
            data["avg_score"] = round(sum(scores) / len(scores), 3) if scores else 0.0
            del data["scores"]  # Remove raw scores from output

        # Get recommended order (top 5)
        ranked = self.rank_improvements(improvements, include_scores=True)
        recommended_order = [
            {
                "imp_id": imp.get("imp_id", imp.get("id", "unknown")),
                "priority_score": imp.get("priority_score", 0.0),
                "priority_level": self._extract_priority_level(imp),
                "category": self._extract_category(imp),
            }
            for imp in ranked[:5]
        ]

        return {
            "total_improvements": len(improvements),
            "by_priority_level": by_priority,
            "by_category": by_category,
            "high_risk_items": high_risk_items,
            "recommended_order": recommended_order,
        }

    def compute_execution_plan(
        self,
        tasks: list[dict[str, Any]],
        budget_tokens: float | None = None,
    ) -> ExecutionPlanResult:
        """Build DAG from task dependencies and compute optimal execution order.

        Uses Pareto frontier optimization balancing:
        - Token cost minimization
        - Impact maximization
        - Dependency satisfaction

        Args:
            tasks: List of task dictionaries to schedule. Each task should have:
                - imp_id or id: Unique identifier
                - depends_on: Optional list of task IDs this task depends on
                - estimated_tokens: Optional estimated token cost
                - priority: Priority level (affects impact score)
            budget_tokens: Optional token budget constraint.

        Returns:
            ExecutionPlanResult containing the ordered tasks and metadata.
        """
        if not tasks:
            return ExecutionPlanResult(
                ordered_tasks=[],
                total_estimated_tokens=0.0,
                dependency_graph={},
                pareto_frontier_count=0,
                budget_constrained=False,
            )

        # Build dependency DAG
        dag = self._build_dependency_dag(tasks)

        # Topological sort respecting dependencies
        ordered = self._topological_sort(tasks, dag)

        # Apply Pareto optimization
        frontier, frontier_count = self._compute_pareto_frontier(ordered)

        # Apply budget constraint if specified
        budget_constrained = False
        if budget_tokens is not None:
            frontier, budget_constrained = self._apply_budget_constraint(frontier, budget_tokens)

        # Calculate total estimated tokens
        total_tokens = sum(task.get("estimated_tokens", 1000.0) for task in frontier)

        logger.info(
            "Computed execution plan: %d tasks, %.0f total tokens, budget_constrained=%s",
            len(frontier),
            total_tokens,
            budget_constrained,
        )

        return ExecutionPlanResult(
            ordered_tasks=frontier,
            total_estimated_tokens=total_tokens,
            dependency_graph=dag,
            pareto_frontier_count=frontier_count,
            budget_constrained=budget_constrained,
        )

    def _build_dependency_dag(self, tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
        """Build directed acyclic graph of task dependencies.

        Args:
            tasks: List of task dictionaries.

        Returns:
            Dictionary mapping task IDs to lists of tasks they depend on.
        """
        dag: dict[str, list[str]] = defaultdict(list)

        # Create a set of valid task IDs
        valid_ids: set[str] = set()
        for task in tasks:
            task_id = task.get("imp_id", task.get("id", ""))
            if task_id:
                valid_ids.add(task_id)

        # Build the dependency graph
        for task in tasks:
            task_id = task.get("imp_id", task.get("id", ""))
            if not task_id:
                continue

            depends_on = task.get("depends_on", [])
            if isinstance(depends_on, str):
                depends_on = [depends_on]

            # Only include valid dependencies
            valid_deps = [dep for dep in depends_on if dep in valid_ids]
            dag[task_id] = valid_deps

            # Ensure all task IDs are in the DAG (even with no dependencies)
            if task_id not in dag:
                dag[task_id] = []

        return dict(dag)

    def _topological_sort(
        self,
        tasks: list[dict[str, Any]],
        dag: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        """Sort tasks respecting dependency order using Kahn's algorithm.

        Args:
            tasks: List of task dictionaries.
            dag: Dependency graph (task -> list of dependencies).

        Returns:
            List of tasks sorted in valid execution order.
        """
        # Create task lookup by ID
        task_by_id: dict[str, dict[str, Any]] = {}
        for task in tasks:
            task_id = task.get("imp_id", task.get("id", ""))
            if task_id:
                task_by_id[task_id] = task

        # Calculate in-degrees (how many tasks depend on each task)
        # We need to invert the DAG for in-degree calculation
        # dag[A] = [B] means A depends on B
        # For topological sort, we need B to come before A
        dependents: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {task_id: 0 for task_id in dag}

        for task_id, dependencies in dag.items():
            in_degree[task_id] = len(dependencies)
            for dep in dependencies:
                dependents[dep].append(task_id)

        # Find all tasks with no dependencies (in-degree 0)
        queue: deque[str] = deque()
        for task_id, degree in in_degree.items():
            if degree == 0:
                queue.append(task_id)

        sorted_ids: list[str] = []
        while queue:
            # Process tasks with same in-degree by priority score
            # to get deterministic, priority-aware ordering
            current_batch = list(queue)
            queue.clear()

            # Sort current batch by priority score (higher first)
            current_batch.sort(
                key=lambda tid: self.calculate_priority_score(task_by_id.get(tid, {})),
                reverse=True,
            )

            for task_id in current_batch:
                sorted_ids.append(task_id)

                # Reduce in-degree of dependent tasks
                for dependent in dependents[task_id]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        # Handle any remaining tasks (cycle detection)
        # Add them at the end, sorted by priority
        remaining = [tid for tid in dag if tid not in sorted_ids]
        if remaining:
            logger.warning(
                "Detected dependency cycle involving %d tasks: %s",
                len(remaining),
                remaining[:5],
            )
            remaining.sort(
                key=lambda tid: self.calculate_priority_score(task_by_id.get(tid, {})),
                reverse=True,
            )
            sorted_ids.extend(remaining)

        # Convert IDs back to tasks
        return [task_by_id[tid] for tid in sorted_ids if tid in task_by_id]

    def _compute_pareto_frontier(
        self, tasks: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int]:
        """Find Pareto-optimal tasks balancing cost vs impact.

        A task is Pareto-optimal if no other task has both lower cost
        AND higher impact. This preserves the execution order from
        topological sort while annotating which tasks are on the frontier.

        Args:
            tasks: List of tasks in topologically sorted order.

        Returns:
            Tuple of (tasks in original order, count of frontier tasks).
            The original topological order is preserved to respect dependencies.
        """
        if not tasks:
            return [], 0

        # Calculate cost and impact for each task
        task_metrics: list[tuple[dict[str, Any], float, float]] = []
        for task in tasks:
            cost = task.get("estimated_tokens", 1000.0)
            impact = self.calculate_priority_score(task)
            task_metrics.append((task, cost, impact))

        # Find Pareto frontier
        # A point is dominated if another point has lower cost AND higher impact
        frontier_count = 0

        for i, (task_i, cost_i, impact_i) in enumerate(task_metrics):
            is_dominated = False
            for j, (task_j, cost_j, impact_j) in enumerate(task_metrics):
                if i == j:
                    continue
                # task_j dominates task_i if:
                # cost_j <= cost_i AND impact_j >= impact_i
                # AND at least one strict inequality
                if cost_j <= cost_i and impact_j >= impact_i:
                    if cost_j < cost_i or impact_j > impact_i:
                        is_dominated = True
                        break

            if not is_dominated:
                frontier_count += 1

        logger.debug(
            "Pareto frontier: %d of %d tasks",
            frontier_count,
            len(tasks),
        )

        # Return tasks in original topological order to respect dependencies
        return tasks, frontier_count

    def _apply_budget_constraint(
        self,
        tasks: list[dict[str, Any]],
        budget_tokens: float,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Filter tasks to fit within token budget.

        Args:
            tasks: List of tasks (ideally Pareto-sorted).
            budget_tokens: Maximum total token budget.

        Returns:
            Tuple of (filtered tasks, whether constraint was applied).
        """
        if budget_tokens <= 0:
            return [], True

        selected: list[dict[str, Any]] = []
        current_cost = 0.0

        for task in tasks:
            task_cost = task.get("estimated_tokens", 1000.0)
            if current_cost + task_cost <= budget_tokens:
                selected.append(task)
                current_cost += task_cost
            else:
                # Budget exceeded, stop adding tasks
                break

        was_constrained = len(selected) < len(tasks)

        if was_constrained:
            logger.info(
                "Budget constraint: selected %d of %d tasks (%.0f of %.0f tokens)",
                len(selected),
                len(tasks),
                current_cost,
                budget_tokens,
            )

        return selected, was_constrained
