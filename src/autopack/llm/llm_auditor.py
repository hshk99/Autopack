"""LLM Auditor for routing decision oversight and optimization.

This module provides an auditor role that reviews LLM routing decisions,
suggests overrides when needed, and learns from past routing outcomes
to optimize future decisions.

Part of IMP-LLM-002: LLM Auditor Role for Routing Decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .model_registry import ModelInfo, ModelRegistry, ModelTier, get_model_registry
from .routing_engine import RoutingDecision, RoutingEngine, RoutingStrategy, get_routing_engine

logger = logging.getLogger(__name__)


class AuditFlag(Enum):
    """Flags raised during routing audits."""

    COST_CONCERN = "cost_concern"
    CAPABILITY_MISMATCH = "capability_mismatch"
    OVERQUALIFIED_MODEL = "overqualified_model"
    UNDERQUALIFIED_MODEL = "underqualified_model"
    UNHEALTHY_MODEL = "unhealthy_model"
    SUBOPTIMAL_STRATEGY = "suboptimal_strategy"
    HIGH_LATENCY_EXPECTED = "high_latency_expected"
    FALLBACK_RECOMMENDED = "fallback_recommended"


class OverrideReason(Enum):
    """Reasons for suggesting a routing override."""

    BETTER_CAPABILITY_MATCH = "better_capability_match"
    COST_OPTIMIZATION = "cost_optimization"
    LATENCY_OPTIMIZATION = "latency_optimization"
    HEALTH_CONCERN = "health_concern"
    COMPLEXITY_MISMATCH = "complexity_mismatch"
    HISTORICAL_PERFORMANCE = "historical_performance"


@dataclass
class ExecutionMetrics:
    """Metrics from task execution."""

    task_id: str
    model_id: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost: float
    success: bool
    error_message: Optional[str] = None
    quality_score: Optional[float] = None  # 0-1, if available
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def tokens_per_second(self) -> float:
        """Calculate tokens processed per second."""
        if self.latency_ms <= 0:
            return 0.0
        total_tokens = self.input_tokens + self.output_tokens
        return total_tokens / (self.latency_ms / 1000)


@dataclass
class AuditResult:
    """Result of auditing a routing decision."""

    approved: bool
    confidence: float  # 0-1
    reasoning: str
    suggested_model: Optional[str] = None
    flags: List[AuditFlag] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_warnings(self) -> bool:
        """Check if audit has any warning flags."""
        return len(self.flags) > 0


@dataclass
class OverrideSuggestion:
    """Suggestion to override a routing decision."""

    current_model: str
    suggested_model: str
    reason: OverrideReason
    confidence: float  # 0-1
    expected_improvement: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelPerformanceStats:
    """Performance statistics for a model."""

    model_id: str
    total_executions: int
    successful_executions: int
    failed_executions: int
    total_cost: float
    average_latency_ms: float
    average_quality_score: float
    success_rate: float
    task_types: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def empty(cls, model_id: str) -> "ModelPerformanceStats":
        """Create empty stats for a model."""
        return cls(
            model_id=model_id,
            total_executions=0,
            successful_executions=0,
            failed_executions=0,
            total_cost=0.0,
            average_latency_ms=0.0,
            average_quality_score=0.0,
            success_rate=1.0,
        )


@dataclass
class RoutingReport:
    """Report on routing performance over a time period."""

    start_time: datetime
    end_time: datetime
    total_requests: int
    total_cost: float
    average_latency_ms: float
    success_rate: float
    model_stats: Dict[str, ModelPerformanceStats]
    top_task_types: List[tuple[str, int]]
    optimization_suggestions: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditLogEntry:
    """Entry in the audit log."""

    timestamp: datetime
    task_id: str
    task_type: str
    routing_decision: RoutingDecision
    audit_result: AuditResult
    execution_metrics: Optional[ExecutionMetrics] = None


class LLMAuditor:
    """Audits LLM routing decisions and provides optimization suggestions.

    The LLMAuditor provides oversight for automated routing decisions:
    - Pre-routing audit: Reviews task complexity assessment
    - Model suitability check: Verifies selected model is appropriate
    - Override decisions: Flags cases where routing should be overridden
    - Post-execution audit: Assesses if routing decision was optimal
    - Optimization suggestions: Recommends routing rule changes

    Attributes:
        routing_engine: The routing engine to audit.
        model_registry: The model registry for model information.
        audit_log: Log of all audit entries.
    """

    def __init__(
        self,
        routing_engine: Optional[RoutingEngine] = None,
        model_registry: Optional[ModelRegistry] = None,
        config_path: str = "config/llm_validation.yaml",
    ):
        """Initialize the LLM Auditor.

        Args:
            routing_engine: Routing engine instance (uses singleton if not provided).
            model_registry: Model registry instance (uses singleton if not provided).
            config_path: Path to configuration file.
        """
        self.routing_engine = routing_engine or get_routing_engine(config_path)
        self.model_registry = model_registry or get_model_registry(config_path)
        self.audit_log: List[AuditLogEntry] = []
        self._execution_history: Dict[str, List[ExecutionMetrics]] = {}
        self._config_path = config_path

        # Audit thresholds (can be configured)
        self._cost_threshold_ratio = 2.0  # Flag if cost is 2x cheaper alternative
        self._complexity_tolerance = 0.2  # Tolerance for complexity mismatch
        self._min_confidence_for_override = 0.7  # Minimum confidence to suggest override

    async def audit_routing_decision(
        self,
        task_type: str,
        selected_model: str,
        complexity_score: float,
        required_capabilities: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AuditResult:
        """Audit a routing decision before execution.

        This is the primary pre-execution audit that reviews whether
        the selected model is appropriate for the task.

        Args:
            task_type: Type of task being routed.
            selected_model: Model ID that was selected.
            complexity_score: Complexity score of the task.
            required_capabilities: Required capabilities for the task.
            context: Additional context for the audit.

        Returns:
            AuditResult with approval status and any flags.
        """
        required_capabilities = required_capabilities or []
        context = context or {}
        flags: List[AuditFlag] = []
        suggestions: List[str] = []

        model_info = self.model_registry.get_model(selected_model)
        if model_info is None:
            return AuditResult(
                approved=False,
                confidence=1.0,
                reasoning=f"Model {selected_model} not found in registry",
                flags=[AuditFlag.CAPABILITY_MISMATCH],
            )

        # Check model health
        if not model_info.is_available():
            flags.append(AuditFlag.UNHEALTHY_MODEL)
            suggestions.append(f"Model {selected_model} has health issues")

        # Check capability match
        missing_caps = [
            cap
            for cap in required_capabilities
            if not model_info.capabilities.has_capability(cap)
        ]
        if missing_caps:
            flags.append(AuditFlag.CAPABILITY_MISMATCH)
            suggestions.append(f"Model missing capabilities: {missing_caps}")

        # Check complexity vs model tier alignment
        tier_score = self._get_tier_complexity_score(model_info.tier)
        complexity_diff = abs(complexity_score - tier_score)

        if complexity_diff > self._complexity_tolerance:
            if complexity_score > tier_score:
                flags.append(AuditFlag.UNDERQUALIFIED_MODEL)
                suggestions.append(
                    f"Task complexity ({complexity_score:.2f}) exceeds model tier capacity"
                )
            else:
                flags.append(AuditFlag.OVERQUALIFIED_MODEL)
                suggestions.append(
                    f"Model may be overqualified for task complexity ({complexity_score:.2f})"
                )

        # Check for cost optimization opportunities
        cheaper_alternative = self._find_cheaper_alternative(
            selected_model, required_capabilities, complexity_score
        )
        if cheaper_alternative:
            cost_ratio = self._calculate_cost_ratio(selected_model, cheaper_alternative)
            if cost_ratio > self._cost_threshold_ratio:
                flags.append(AuditFlag.COST_CONCERN)
                suggestions.append(
                    f"Cheaper alternative available: {cheaper_alternative} "
                    f"({cost_ratio:.1f}x cost savings)"
                )

        # Check historical performance for this task type
        historical_performance = self._get_model_performance_for_task(
            selected_model, task_type
        )
        if historical_performance and historical_performance.success_rate < 0.8:
            flags.append(AuditFlag.FALLBACK_RECOMMENDED)
            suggestions.append(
                f"Historical success rate for {task_type}: "
                f"{historical_performance.success_rate:.1%}"
            )

        # Determine approval and confidence
        critical_flags = {
            AuditFlag.UNHEALTHY_MODEL,
            AuditFlag.CAPABILITY_MISMATCH,
            AuditFlag.UNDERQUALIFIED_MODEL,
        }
        has_critical = any(f in critical_flags for f in flags)

        approved = not has_critical
        confidence = 1.0 - (len(flags) * 0.15)  # Reduce confidence per flag
        confidence = max(0.0, min(1.0, confidence))

        # Build reasoning
        if approved:
            reasoning = f"Model {selected_model} approved for {task_type}"
            if flags:
                reasoning += f" with warnings: {[f.value for f in flags]}"
        else:
            reasoning = (
                f"Model {selected_model} not recommended for {task_type}. "
                f"Issues: {'; '.join(suggestions)}"
            )

        # Find suggested alternative if not approved
        suggested_model = None
        if not approved:
            alternative = self._find_better_alternative(
                selected_model, task_type, required_capabilities, complexity_score
            )
            if alternative:
                suggested_model = alternative

        return AuditResult(
            approved=approved,
            confidence=confidence,
            reasoning=reasoning,
            suggested_model=suggested_model,
            flags=flags,
            metadata={"task_type": task_type, "context": context},
        )

    async def suggest_override(
        self,
        task_type: str,
        current_selection: str,
        complexity_score: float,
        required_capabilities: Optional[List[str]] = None,
    ) -> Optional[OverrideSuggestion]:
        """Suggest an override if current selection is suboptimal.

        Analyzes the current selection and determines if a better
        alternative exists based on capabilities, cost, and historical
        performance.

        Args:
            task_type: Type of task being routed.
            current_selection: Currently selected model ID.
            complexity_score: Complexity score of the task.
            required_capabilities: Required capabilities for the task.

        Returns:
            OverrideSuggestion if an override is recommended, None otherwise.
        """
        required_capabilities = required_capabilities or []

        current_model = self.model_registry.get_model(current_selection)
        if current_model is None:
            return None

        # Find best alternative
        alternatives = self.model_registry.find_models_for_task(
            required_capabilities=required_capabilities,
            exclude_models={current_selection},
        )

        if not alternatives:
            return None

        # Evaluate each alternative
        best_alternative: Optional[ModelInfo] = None
        best_reason: Optional[OverrideReason] = None
        best_confidence = 0.0
        best_improvement = ""

        for alt in alternatives:
            reason, confidence, improvement = self._evaluate_alternative(
                current_model, alt, task_type, complexity_score, required_capabilities
            )
            if confidence > best_confidence and confidence >= self._min_confidence_for_override:
                best_alternative = alt
                best_reason = reason
                best_confidence = confidence
                best_improvement = improvement

        if best_alternative is None or best_reason is None:
            return None

        return OverrideSuggestion(
            current_model=current_selection,
            suggested_model=best_alternative.model_id,
            reason=best_reason,
            confidence=best_confidence,
            expected_improvement=best_improvement,
        )

    async def record_outcome(
        self,
        task_id: str,
        task_type: str,
        routing_decision: RoutingDecision,
        success: bool,
        metrics: ExecutionMetrics,
    ) -> None:
        """Record execution outcome for learning.

        Records the outcome of a routing decision to build historical
        data for optimizing future decisions.

        Args:
            task_id: Unique identifier for the task.
            task_type: Type of task that was executed.
            routing_decision: The routing decision that was made.
            success: Whether execution was successful.
            metrics: Execution metrics from the task.
        """
        model_id = routing_decision.model_id

        # Update execution history
        if model_id not in self._execution_history:
            self._execution_history[model_id] = []
        self._execution_history[model_id].append(metrics)

        # Limit history size per model
        max_history = 1000
        if len(self._execution_history[model_id]) > max_history:
            self._execution_history[model_id] = self._execution_history[model_id][-max_history:]

        # Create audit log entry (audit result for historical decisions)
        audit_result = AuditResult(
            approved=True,
            confidence=1.0,
            reasoning=f"Post-execution audit: {'success' if success else 'failure'}",
            metadata={"success": success, "task_id": task_id},
        )

        log_entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc),
            task_id=task_id,
            task_type=task_type,
            routing_decision=routing_decision,
            audit_result=audit_result,
            execution_metrics=metrics,
        )
        self.audit_log.append(log_entry)

        # Limit audit log size
        max_log_entries = 10000
        if len(self.audit_log) > max_log_entries:
            self.audit_log = self.audit_log[-max_log_entries:]

        # Update model health in registry
        if success:
            self.model_registry.record_success(model_id, metrics.latency_ms)
        else:
            self.model_registry.record_failure(
                model_id, metrics.error_message or "Execution failed"
            )

        logger.debug(
            f"[LLMAuditor] Recorded outcome for task {task_id}: "
            f"model={model_id}, success={success}"
        )

    def generate_routing_report(
        self,
        time_period: timedelta,
        include_suggestions: bool = True,
    ) -> RoutingReport:
        """Generate report on routing performance.

        Creates a comprehensive report on routing performance over
        the specified time period, including model statistics and
        optimization suggestions.

        Args:
            time_period: Time period to analyze (e.g., timedelta(days=7)).
            include_suggestions: Whether to include optimization suggestions.

        Returns:
            RoutingReport with performance metrics and analysis.
        """
        now = datetime.now(timezone.utc)
        start_time = now - time_period
        end_time = now

        # Filter audit log entries within time period
        relevant_entries = [
            entry
            for entry in self.audit_log
            if entry.timestamp >= start_time
        ]

        if not relevant_entries:
            return RoutingReport(
                start_time=start_time,
                end_time=end_time,
                total_requests=0,
                total_cost=0.0,
                average_latency_ms=0.0,
                success_rate=1.0,
                model_stats={},
                top_task_types=[],
                optimization_suggestions=[],
            )

        # Calculate aggregate metrics
        total_requests = len(relevant_entries)
        total_cost = 0.0
        total_latency = 0.0
        successful_requests = 0
        task_type_counts: Dict[str, int] = {}
        model_metrics: Dict[str, List[ExecutionMetrics]] = {}

        for entry in relevant_entries:
            task_type_counts[entry.task_type] = task_type_counts.get(entry.task_type, 0) + 1

            if entry.execution_metrics:
                metrics = entry.execution_metrics
                total_cost += metrics.cost
                total_latency += metrics.latency_ms
                if metrics.success:
                    successful_requests += 1

                if metrics.model_id not in model_metrics:
                    model_metrics[metrics.model_id] = []
                model_metrics[metrics.model_id].append(metrics)

        average_latency = total_latency / total_requests if total_requests > 0 else 0.0
        success_rate = successful_requests / total_requests if total_requests > 0 else 1.0

        # Calculate per-model statistics
        model_stats = {}
        for model_id, metrics_list in model_metrics.items():
            successful = sum(1 for m in metrics_list if m.success)
            failed = len(metrics_list) - successful
            total_model_cost = sum(m.cost for m in metrics_list)
            avg_latency = (
                sum(m.latency_ms for m in metrics_list) / len(metrics_list)
                if metrics_list
                else 0.0
            )
            quality_scores = [m.quality_score for m in metrics_list if m.quality_score is not None]
            avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

            model_stats[model_id] = ModelPerformanceStats(
                model_id=model_id,
                total_executions=len(metrics_list),
                successful_executions=successful,
                failed_executions=failed,
                total_cost=total_model_cost,
                average_latency_ms=avg_latency,
                average_quality_score=avg_quality,
                success_rate=successful / len(metrics_list) if metrics_list else 1.0,
            )

        # Get top task types
        top_task_types = sorted(
            task_type_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        # Generate optimization suggestions
        suggestions = []
        if include_suggestions:
            suggestions = self._generate_optimization_suggestions(
                model_stats, task_type_counts, success_rate
            )

        return RoutingReport(
            start_time=start_time,
            end_time=end_time,
            total_requests=total_requests,
            total_cost=total_cost,
            average_latency_ms=average_latency,
            success_rate=success_rate,
            model_stats=model_stats,
            top_task_types=top_task_types,
            optimization_suggestions=suggestions,
        )

    def get_audit_history(
        self,
        model_id: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditLogEntry]:
        """Get audit history with optional filtering.

        Args:
            model_id: Filter by model ID.
            task_type: Filter by task type.
            limit: Maximum number of entries to return.

        Returns:
            List of audit log entries matching the filters.
        """
        entries = self.audit_log.copy()

        if model_id:
            entries = [e for e in entries if e.routing_decision.model_id == model_id]

        if task_type:
            entries = [e for e in entries if e.task_type == task_type]

        # Return most recent entries
        return entries[-limit:]

    def get_model_performance(self, model_id: str) -> ModelPerformanceStats:
        """Get performance statistics for a specific model.

        Args:
            model_id: Model identifier.

        Returns:
            ModelPerformanceStats for the model.
        """
        metrics_list = self._execution_history.get(model_id, [])

        if not metrics_list:
            return ModelPerformanceStats.empty(model_id)

        successful = sum(1 for m in metrics_list if m.success)
        failed = len(metrics_list) - successful
        total_cost = sum(m.cost for m in metrics_list)
        avg_latency = sum(m.latency_ms for m in metrics_list) / len(metrics_list)
        quality_scores = [m.quality_score for m in metrics_list if m.quality_score is not None]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        # Count task types
        task_types: Dict[str, int] = {}
        for entry in self.audit_log:
            if entry.routing_decision.model_id == model_id:
                task_types[entry.task_type] = task_types.get(entry.task_type, 0) + 1

        return ModelPerformanceStats(
            model_id=model_id,
            total_executions=len(metrics_list),
            successful_executions=successful,
            failed_executions=failed,
            total_cost=total_cost,
            average_latency_ms=avg_latency,
            average_quality_score=avg_quality,
            success_rate=successful / len(metrics_list) if metrics_list else 1.0,
            task_types=task_types,
        )

    def clear_history(self) -> None:
        """Clear all audit history and execution metrics."""
        self.audit_log.clear()
        self._execution_history.clear()
        logger.info("[LLMAuditor] Cleared all audit history")

    # Private helper methods

    def _get_tier_complexity_score(self, tier: ModelTier) -> float:
        """Map model tier to expected complexity score."""
        tier_scores = {
            ModelTier.ECONOMY: 0.25,
            ModelTier.STANDARD: 0.55,
            ModelTier.PREMIUM: 0.85,
        }
        return tier_scores.get(tier, 0.5)

    def _find_cheaper_alternative(
        self,
        current_model: str,
        required_capabilities: List[str],
        complexity_score: float,
    ) -> Optional[str]:
        """Find a cheaper alternative model that meets requirements."""
        current = self.model_registry.get_model(current_model)
        if current is None:
            return None

        current_cost = (
            current.cost.cost_per_1k_input_tokens + current.cost.cost_per_1k_output_tokens
        )

        candidates = self.model_registry.find_models_for_task(
            required_capabilities=required_capabilities,
            exclude_models={current_model},
        )

        for candidate in candidates:
            candidate_cost = (
                candidate.cost.cost_per_1k_input_tokens
                + candidate.cost.cost_per_1k_output_tokens
            )
            # Check if cheaper and capable enough for the complexity
            tier_score = self._get_tier_complexity_score(candidate.tier)
            if candidate_cost < current_cost and tier_score >= complexity_score - 0.1:
                return candidate.model_id

        return None

    def _calculate_cost_ratio(self, model1: str, model2: str) -> float:
        """Calculate cost ratio between two models (model1 / model2)."""
        m1 = self.model_registry.get_model(model1)
        m2 = self.model_registry.get_model(model2)

        if m1 is None or m2 is None:
            return 1.0

        cost1 = m1.cost.cost_per_1k_input_tokens + m1.cost.cost_per_1k_output_tokens
        cost2 = m2.cost.cost_per_1k_input_tokens + m2.cost.cost_per_1k_output_tokens

        if cost2 == 0:
            return 1.0

        return cost1 / cost2

    def _get_model_performance_for_task(
        self, model_id: str, task_type: str
    ) -> Optional[ModelPerformanceStats]:
        """Get performance stats for a model on a specific task type."""
        relevant_entries = [
            entry
            for entry in self.audit_log
            if entry.routing_decision.model_id == model_id and entry.task_type == task_type
        ]

        if not relevant_entries:
            return None

        metrics_list = [e.execution_metrics for e in relevant_entries if e.execution_metrics]
        if not metrics_list:
            return None

        successful = sum(1 for m in metrics_list if m.success)

        return ModelPerformanceStats(
            model_id=model_id,
            total_executions=len(metrics_list),
            successful_executions=successful,
            failed_executions=len(metrics_list) - successful,
            total_cost=sum(m.cost for m in metrics_list),
            average_latency_ms=sum(m.latency_ms for m in metrics_list) / len(metrics_list),
            average_quality_score=0.0,
            success_rate=successful / len(metrics_list),
            task_types={task_type: len(metrics_list)},
        )

    def _find_better_alternative(
        self,
        current_model: str,
        task_type: str,
        required_capabilities: List[str],
        complexity_score: float,
    ) -> Optional[str]:
        """Find a better alternative model for the task."""
        candidates = self.model_registry.find_models_for_task(
            required_capabilities=required_capabilities,
            exclude_models={current_model},
        )

        if not candidates:
            return None

        # Score each candidate
        best_candidate = None
        best_score = 0.0

        for candidate in candidates:
            if not candidate.is_available():
                continue

            # Calculate suitability score
            tier_score = self._get_tier_complexity_score(candidate.tier)
            complexity_match = 1.0 - abs(complexity_score - tier_score)
            capability_score = candidate.capabilities.weighted_score()

            # Check historical performance
            perf = self._get_model_performance_for_task(candidate.model_id, task_type)
            history_score = perf.success_rate if perf else 0.8

            # Combined score
            score = (complexity_match * 0.3) + (capability_score * 0.4) + (history_score * 0.3)

            if score > best_score:
                best_score = score
                best_candidate = candidate

        return best_candidate.model_id if best_candidate else None

    def _evaluate_alternative(
        self,
        current: ModelInfo,
        alternative: ModelInfo,
        task_type: str,
        complexity_score: float,
        required_capabilities: List[str],
    ) -> tuple[Optional[OverrideReason], float, str]:
        """Evaluate an alternative model against the current selection."""
        # Check capability improvement
        current_caps = set(current.capabilities.capabilities)
        alt_caps = set(alternative.capabilities.capabilities)
        required_set = set(required_capabilities)

        current_missing = required_set - current_caps
        alt_missing = required_set - alt_caps

        if len(alt_missing) < len(current_missing):
            return (
                OverrideReason.BETTER_CAPABILITY_MATCH,
                0.85,
                f"Better capability coverage: {len(alt_caps & required_set)} vs "
                f"{len(current_caps & required_set)} required capabilities",
            )

        # Check cost optimization
        current_cost = (
            current.cost.cost_per_1k_input_tokens + current.cost.cost_per_1k_output_tokens
        )
        alt_cost = (
            alternative.cost.cost_per_1k_input_tokens
            + alternative.cost.cost_per_1k_output_tokens
        )

        if alt_cost < current_cost * 0.5:  # At least 50% cheaper
            tier_score = self._get_tier_complexity_score(alternative.tier)
            if tier_score >= complexity_score - 0.1:
                savings = (1 - alt_cost / current_cost) * 100
                return (
                    OverrideReason.COST_OPTIMIZATION,
                    0.75,
                    f"{savings:.0f}% cost savings with similar capability",
                )

        # Check health concern
        if not current.is_available() and alternative.is_available():
            return (
                OverrideReason.HEALTH_CONCERN,
                0.9,
                f"Current model unhealthy, {alternative.model_id} is available",
            )

        # Check historical performance
        current_perf = self._get_model_performance_for_task(current.model_id, task_type)
        alt_perf = self._get_model_performance_for_task(alternative.model_id, task_type)

        if current_perf and alt_perf:
            if alt_perf.success_rate > current_perf.success_rate + 0.1:
                return (
                    OverrideReason.HISTORICAL_PERFORMANCE,
                    0.8,
                    f"Better success rate: {alt_perf.success_rate:.1%} vs "
                    f"{current_perf.success_rate:.1%}",
                )

        return (None, 0.0, "")

    def _generate_optimization_suggestions(
        self,
        model_stats: Dict[str, ModelPerformanceStats],
        task_type_counts: Dict[str, int],
        overall_success_rate: float,
    ) -> List[str]:
        """Generate optimization suggestions based on performance data."""
        suggestions = []

        # Check for models with low success rates
        for model_id, stats in model_stats.items():
            if stats.success_rate < 0.8 and stats.total_executions >= 10:
                suggestions.append(
                    f"Model {model_id} has low success rate ({stats.success_rate:.1%}). "
                    f"Consider adjusting routing rules or fallback chain."
                )

        # Check for cost optimization opportunities
        high_cost_models = [
            (model_id, stats)
            for model_id, stats in model_stats.items()
            if stats.total_cost > 0
        ]
        if high_cost_models:
            top_cost = sorted(high_cost_models, key=lambda x: x[1].total_cost, reverse=True)
            if len(top_cost) > 1:
                top_model, top_stats = top_cost[0]
                suggestions.append(
                    f"Model {top_model} accounts for highest cost "
                    f"(${top_stats.total_cost:.2f}). "
                    f"Review if tasks can be routed to cheaper alternatives."
                )

        # Check overall health
        if overall_success_rate < 0.9:
            suggestions.append(
                f"Overall success rate ({overall_success_rate:.1%}) is below 90%. "
                f"Review routing rules and model health."
            )

        return suggestions


# Singleton instance
_auditor: Optional[LLMAuditor] = None


def get_llm_auditor(config_path: str = "config/llm_validation.yaml") -> LLMAuditor:
    """Get or create the singleton LLMAuditor instance.

    Args:
        config_path: Path to configuration file.

    Returns:
        LLMAuditor singleton instance.
    """
    global _auditor
    if _auditor is None:
        _auditor = LLMAuditor(config_path=config_path)
    return _auditor
