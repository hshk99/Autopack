"""Tests for LLM Auditor.

Part of IMP-LLM-002: LLM Auditor Role for Routing Decisions.
"""

from datetime import datetime, timedelta, timezone

import pytest

from autopack.llm.llm_auditor import (
    AuditFlag,
    AuditLogEntry,
    AuditResult,
    ExecutionMetrics,
    LLMAuditor,
    ModelPerformanceStats,
    OverrideReason,
    OverrideSuggestion,
    RoutingReport,
)
from autopack.llm.model_registry import (
    ModelCapabilities,
    ModelCost,
    ModelInfo,
    ModelLimits,
    ModelRegistry,
    ModelTier,
)
from autopack.llm.routing_engine import (
    RoutingDecision,
    RoutingEngine,
    RoutingStrategy,
)


class TestExecutionMetrics:
    """Tests for ExecutionMetrics class."""

    def test_creation(self):
        """Test creating execution metrics."""
        metrics = ExecutionMetrics(
            task_id="task-123",
            model_id="claude-sonnet-4-5",
            latency_ms=1500.0,
            input_tokens=1000,
            output_tokens=500,
            cost=0.005,
            success=True,
        )
        assert metrics.task_id == "task-123"
        assert metrics.model_id == "claude-sonnet-4-5"
        assert metrics.success is True

    def test_tokens_per_second(self):
        """Test tokens per second calculation."""
        metrics = ExecutionMetrics(
            task_id="task-123",
            model_id="claude-sonnet-4-5",
            latency_ms=2000.0,  # 2 seconds
            input_tokens=1000,
            output_tokens=500,
            cost=0.005,
            success=True,
        )
        # 1500 tokens / 2 seconds = 750 tokens/second
        assert metrics.tokens_per_second == 750.0

    def test_tokens_per_second_zero_latency(self):
        """Test tokens per second with zero latency."""
        metrics = ExecutionMetrics(
            task_id="task-123",
            model_id="claude-sonnet-4-5",
            latency_ms=0.0,
            input_tokens=1000,
            output_tokens=500,
            cost=0.005,
            success=True,
        )
        assert metrics.tokens_per_second == 0.0


class TestAuditResult:
    """Tests for AuditResult class."""

    def test_creation(self):
        """Test creating audit result."""
        result = AuditResult(
            approved=True,
            confidence=0.95,
            reasoning="Model approved for task",
        )
        assert result.approved is True
        assert result.confidence == 0.95
        assert result.has_warnings is False

    def test_has_warnings(self):
        """Test has_warnings property."""
        result_with_flags = AuditResult(
            approved=True,
            confidence=0.8,
            reasoning="Approved with warnings",
            flags=[AuditFlag.COST_CONCERN],
        )
        assert result_with_flags.has_warnings is True

        result_without_flags = AuditResult(
            approved=True,
            confidence=0.95,
            reasoning="Clean approval",
        )
        assert result_without_flags.has_warnings is False


class TestOverrideSuggestion:
    """Tests for OverrideSuggestion class."""

    def test_creation(self):
        """Test creating override suggestion."""
        suggestion = OverrideSuggestion(
            current_model="claude-opus-4-5",
            suggested_model="claude-sonnet-4-5",
            reason=OverrideReason.COST_OPTIMIZATION,
            confidence=0.85,
            expected_improvement="60% cost savings",
        )
        assert suggestion.current_model == "claude-opus-4-5"
        assert suggestion.suggested_model == "claude-sonnet-4-5"
        assert suggestion.reason == OverrideReason.COST_OPTIMIZATION


class TestModelPerformanceStats:
    """Tests for ModelPerformanceStats class."""

    def test_creation(self):
        """Test creating performance stats."""
        stats = ModelPerformanceStats(
            model_id="claude-sonnet-4-5",
            total_executions=100,
            successful_executions=95,
            failed_executions=5,
            total_cost=5.0,
            average_latency_ms=1500.0,
            average_quality_score=0.9,
            success_rate=0.95,
        )
        assert stats.model_id == "claude-sonnet-4-5"
        assert stats.success_rate == 0.95

    def test_empty_factory(self):
        """Test creating empty stats."""
        stats = ModelPerformanceStats.empty("test-model")
        assert stats.model_id == "test-model"
        assert stats.total_executions == 0
        assert stats.success_rate == 1.0


class TestLLMAuditor:
    """Tests for LLMAuditor class."""

    @pytest.fixture
    def registry(self):
        """Create a test registry with models."""
        reg = ModelRegistry.__new__(ModelRegistry)
        reg._models = {}
        reg._providers = set()
        reg._config = {}
        reg._config_path = "test"

        # Add test models
        models = [
            ModelInfo(
                model_id="claude-opus-4-5",
                provider="anthropic",
                display_name="Claude Opus 4.5",
                tier=ModelTier.PREMIUM,
                capabilities=ModelCapabilities(
                    capabilities=("reasoning", "coding", "analysis"),
                    benchmark_scores={"reasoning": 0.95, "coding": 0.92},
                ),
                cost=ModelCost(0.015, 0.075),
                limits=ModelLimits(200000, 32000),
                fallback_model_id="claude-sonnet-4-5",
            ),
            ModelInfo(
                model_id="claude-sonnet-4-5",
                provider="anthropic",
                display_name="Claude Sonnet 4.5",
                tier=ModelTier.STANDARD,
                capabilities=ModelCapabilities(
                    capabilities=("reasoning", "coding", "fast_response"),
                    benchmark_scores={"reasoning": 0.88, "coding": 0.90},
                ),
                cost=ModelCost(0.003, 0.015),
                limits=ModelLimits(200000, 16000),
                fallback_model_id="claude-3-haiku-20240307",
            ),
            ModelInfo(
                model_id="claude-3-haiku-20240307",
                provider="anthropic",
                display_name="Claude 3 Haiku",
                tier=ModelTier.ECONOMY,
                capabilities=ModelCapabilities(
                    capabilities=("fast_response", "simple_tasks"),
                    benchmark_scores={"reasoning": 0.72, "speed": 0.98},
                ),
                cost=ModelCost(0.00025, 0.00125),
                limits=ModelLimits(200000, 4096),
            ),
        ]
        for model in models:
            reg.register_model(model)

        return reg

    @pytest.fixture
    def routing_engine(self, registry):
        """Create a test routing engine."""
        eng = RoutingEngine.__new__(RoutingEngine)
        eng.registry = registry
        eng.validator = None
        eng._config = {
            "routing_rules": [
                {
                    "task_type": "code_generation",
                    "description": "Code generation",
                    "preferred_model": "claude-sonnet-4-5",
                    "complexity_threshold": 0.7,
                    "required_capabilities": ["coding"],
                    "fallback_chain": ["claude-sonnet-4-5", "claude-opus-4-5"],
                },
            ],
            "complexity_estimation": {
                "token_thresholds": {"simple": 1000, "moderate": 5000, "complex": 20000},
            },
            "fallback": {"max_retries": 3},
        }
        eng._routing_rules = eng._load_routing_rules()
        eng._active_chains = {}
        return eng

    @pytest.fixture
    def auditor(self, routing_engine, registry):
        """Create a test LLM auditor."""
        aud = LLMAuditor.__new__(LLMAuditor)
        aud.routing_engine = routing_engine
        aud.model_registry = registry
        aud.audit_log = []
        aud._execution_history = {}
        aud._config_path = "test"
        aud._cost_threshold_ratio = 2.0
        aud._complexity_tolerance = 0.2
        aud._min_confidence_for_override = 0.7
        return aud

    @pytest.mark.asyncio
    async def test_audit_routing_decision_approved(self, auditor):
        """Test auditing an approved routing decision."""
        result = await auditor.audit_routing_decision(
            task_type="code_generation",
            selected_model="claude-sonnet-4-5",
            complexity_score=0.5,
            required_capabilities=["coding"],
        )
        assert result.approved is True
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_audit_routing_decision_missing_capabilities(self, auditor):
        """Test auditing a decision with missing capabilities."""
        result = await auditor.audit_routing_decision(
            task_type="code_generation",
            selected_model="claude-3-haiku-20240307",
            complexity_score=0.5,
            required_capabilities=["coding"],  # Haiku doesn't have coding
        )
        assert result.approved is False
        assert AuditFlag.CAPABILITY_MISMATCH in result.flags

    @pytest.mark.asyncio
    async def test_audit_routing_decision_model_not_found(self, auditor):
        """Test auditing with non-existent model."""
        result = await auditor.audit_routing_decision(
            task_type="test",
            selected_model="non-existent-model",
            complexity_score=0.5,
        )
        assert result.approved is False
        assert AuditFlag.CAPABILITY_MISMATCH in result.flags

    @pytest.mark.asyncio
    async def test_audit_routing_decision_overqualified(self, auditor):
        """Test auditing a decision with overqualified model."""
        result = await auditor.audit_routing_decision(
            task_type="simple_task",
            selected_model="claude-opus-4-5",  # Premium tier
            complexity_score=0.1,  # Very simple task
            required_capabilities=["reasoning"],
        )
        # Should flag as overqualified but still approve
        assert AuditFlag.OVERQUALIFIED_MODEL in result.flags

    @pytest.mark.asyncio
    async def test_audit_routing_decision_underqualified(self, auditor):
        """Test auditing a decision with underqualified model."""
        result = await auditor.audit_routing_decision(
            task_type="complex_task",
            selected_model="claude-3-haiku-20240307",  # Economy tier
            complexity_score=0.9,  # Very complex task
            required_capabilities=["fast_response"],
        )
        assert AuditFlag.UNDERQUALIFIED_MODEL in result.flags
        assert result.approved is False

    @pytest.mark.asyncio
    async def test_suggest_override_cost_optimization(self, auditor):
        """Test override suggestion for cost optimization."""
        suggestion = await auditor.suggest_override(
            task_type="simple_task",
            current_selection="claude-opus-4-5",
            complexity_score=0.3,  # Simple task
            required_capabilities=["reasoning"],
        )
        # Should suggest a cheaper model
        if suggestion:
            assert suggestion.suggested_model != "claude-opus-4-5"

    @pytest.mark.asyncio
    async def test_suggest_override_no_alternatives(self, auditor):
        """Test override suggestion when no alternatives exist."""
        # Mock a scenario with only one model
        auditor.model_registry._models = {
            "only-model": auditor.model_registry._models["claude-sonnet-4-5"]
        }
        suggestion = await auditor.suggest_override(
            task_type="test",
            current_selection="only-model",
            complexity_score=0.5,
        )
        assert suggestion is None

    @pytest.mark.asyncio
    async def test_record_outcome_success(self, auditor):
        """Test recording a successful outcome."""
        routing_decision = RoutingDecision(
            model_id="claude-sonnet-4-5",
            task_type="code_generation",
            complexity_score=0.5,
            strategy_used=RoutingStrategy.PROGRESSIVE,
            fallback_position=0,
            reasoning="Test decision",
            alternatives=[],
        )
        metrics = ExecutionMetrics(
            task_id="task-123",
            model_id="claude-sonnet-4-5",
            latency_ms=1500.0,
            input_tokens=1000,
            output_tokens=500,
            cost=0.005,
            success=True,
        )

        await auditor.record_outcome(
            task_id="task-123",
            task_type="code_generation",
            routing_decision=routing_decision,
            success=True,
            metrics=metrics,
        )

        assert len(auditor.audit_log) == 1
        assert "claude-sonnet-4-5" in auditor._execution_history
        assert len(auditor._execution_history["claude-sonnet-4-5"]) == 1

    @pytest.mark.asyncio
    async def test_record_outcome_failure(self, auditor):
        """Test recording a failed outcome."""
        routing_decision = RoutingDecision(
            model_id="claude-sonnet-4-5",
            task_type="code_generation",
            complexity_score=0.5,
            strategy_used=RoutingStrategy.PROGRESSIVE,
            fallback_position=0,
            reasoning="Test decision",
            alternatives=[],
        )
        metrics = ExecutionMetrics(
            task_id="task-456",
            model_id="claude-sonnet-4-5",
            latency_ms=5000.0,
            input_tokens=1000,
            output_tokens=0,
            cost=0.003,
            success=False,
            error_message="Model timeout",
        )

        await auditor.record_outcome(
            task_id="task-456",
            task_type="code_generation",
            routing_decision=routing_decision,
            success=False,
            metrics=metrics,
        )

        assert len(auditor.audit_log) == 1
        assert auditor.audit_log[0].execution_metrics.success is False

    def test_generate_routing_report_empty(self, auditor):
        """Test generating report with no data."""
        report = auditor.generate_routing_report(timedelta(days=7))
        assert report.total_requests == 0
        assert report.total_cost == 0.0
        assert report.success_rate == 1.0
        assert len(report.model_stats) == 0

    @pytest.mark.asyncio
    async def test_generate_routing_report_with_data(self, auditor):
        """Test generating report with data."""
        # Record some outcomes
        for i in range(5):
            routing_decision = RoutingDecision(
                model_id="claude-sonnet-4-5",
                task_type="code_generation",
                complexity_score=0.5,
                strategy_used=RoutingStrategy.PROGRESSIVE,
                fallback_position=0,
                reasoning="Test",
                alternatives=[],
            )
            metrics = ExecutionMetrics(
                task_id=f"task-{i}",
                model_id="claude-sonnet-4-5",
                latency_ms=1500.0 + i * 100,
                input_tokens=1000,
                output_tokens=500,
                cost=0.005,
                success=i < 4,  # 4 success, 1 failure
            )
            await auditor.record_outcome(
                task_id=f"task-{i}",
                task_type="code_generation",
                routing_decision=routing_decision,
                success=i < 4,
                metrics=metrics,
            )

        report = auditor.generate_routing_report(timedelta(days=1))
        assert report.total_requests == 5
        assert report.success_rate == 0.8
        assert "claude-sonnet-4-5" in report.model_stats

    def test_get_audit_history_empty(self, auditor):
        """Test getting empty audit history."""
        history = auditor.get_audit_history()
        assert len(history) == 0

    @pytest.mark.asyncio
    async def test_get_audit_history_filtered(self, auditor):
        """Test getting filtered audit history."""
        # Record outcomes for different models
        for model_id in ["claude-sonnet-4-5", "claude-opus-4-5"]:
            routing_decision = RoutingDecision(
                model_id=model_id,
                task_type="code_generation",
                complexity_score=0.5,
                strategy_used=RoutingStrategy.PROGRESSIVE,
                fallback_position=0,
                reasoning="Test",
                alternatives=[],
            )
            metrics = ExecutionMetrics(
                task_id=f"task-{model_id}",
                model_id=model_id,
                latency_ms=1500.0,
                input_tokens=1000,
                output_tokens=500,
                cost=0.005,
                success=True,
            )
            await auditor.record_outcome(
                task_id=f"task-{model_id}",
                task_type="code_generation",
                routing_decision=routing_decision,
                success=True,
                metrics=metrics,
            )

        # Filter by model
        history = auditor.get_audit_history(model_id="claude-sonnet-4-5")
        assert len(history) == 1
        assert history[0].routing_decision.model_id == "claude-sonnet-4-5"

    def test_get_model_performance_empty(self, auditor):
        """Test getting performance stats for model with no history."""
        stats = auditor.get_model_performance("unknown-model")
        assert stats.model_id == "unknown-model"
        assert stats.total_executions == 0

    @pytest.mark.asyncio
    async def test_get_model_performance_with_data(self, auditor):
        """Test getting performance stats with execution history."""
        routing_decision = RoutingDecision(
            model_id="claude-sonnet-4-5",
            task_type="code_generation",
            complexity_score=0.5,
            strategy_used=RoutingStrategy.PROGRESSIVE,
            fallback_position=0,
            reasoning="Test",
            alternatives=[],
        )
        metrics = ExecutionMetrics(
            task_id="task-1",
            model_id="claude-sonnet-4-5",
            latency_ms=1500.0,
            input_tokens=1000,
            output_tokens=500,
            cost=0.005,
            success=True,
        )
        await auditor.record_outcome(
            task_id="task-1",
            task_type="code_generation",
            routing_decision=routing_decision,
            success=True,
            metrics=metrics,
        )

        stats = auditor.get_model_performance("claude-sonnet-4-5")
        assert stats.total_executions == 1
        assert stats.success_rate == 1.0
        assert stats.total_cost == 0.005

    def test_clear_history(self, auditor):
        """Test clearing audit history."""
        # Add some dummy data
        auditor.audit_log.append(
            AuditLogEntry(
                timestamp=datetime.now(timezone.utc),
                task_id="task-1",
                task_type="test",
                routing_decision=RoutingDecision(
                    model_id="test",
                    task_type="test",
                    complexity_score=0.5,
                    strategy_used=RoutingStrategy.PROGRESSIVE,
                    fallback_position=0,
                    reasoning="Test",
                    alternatives=[],
                ),
                audit_result=AuditResult(
                    approved=True,
                    confidence=1.0,
                    reasoning="Test",
                ),
            )
        )
        auditor._execution_history["test-model"] = []

        auditor.clear_history()
        assert len(auditor.audit_log) == 0
        assert len(auditor._execution_history) == 0


class TestRoutingReport:
    """Tests for RoutingReport class."""

    def test_creation(self):
        """Test creating a routing report."""
        report = RoutingReport(
            start_time=datetime.now(timezone.utc) - timedelta(days=7),
            end_time=datetime.now(timezone.utc),
            total_requests=100,
            total_cost=5.0,
            average_latency_ms=1500.0,
            success_rate=0.95,
            model_stats={},
            top_task_types=[("code_generation", 50), ("analysis", 30)],
            optimization_suggestions=["Consider using cheaper models for simple tasks"],
        )
        assert report.total_requests == 100
        assert report.success_rate == 0.95
        assert len(report.top_task_types) == 2


class TestAuditFlag:
    """Tests for AuditFlag enum."""

    def test_all_flags_defined(self):
        """Test all expected flags are defined."""
        expected_flags = [
            "COST_CONCERN",
            "CAPABILITY_MISMATCH",
            "OVERQUALIFIED_MODEL",
            "UNDERQUALIFIED_MODEL",
            "UNHEALTHY_MODEL",
            "SUBOPTIMAL_STRATEGY",
            "HIGH_LATENCY_EXPECTED",
            "FALLBACK_RECOMMENDED",
        ]
        for flag_name in expected_flags:
            assert hasattr(AuditFlag, flag_name)


class TestOverrideReason:
    """Tests for OverrideReason enum."""

    def test_all_reasons_defined(self):
        """Test all expected reasons are defined."""
        expected_reasons = [
            "BETTER_CAPABILITY_MATCH",
            "COST_OPTIMIZATION",
            "LATENCY_OPTIMIZATION",
            "HEALTH_CONCERN",
            "COMPLEXITY_MISMATCH",
            "HISTORICAL_PERFORMANCE",
        ]
        for reason_name in expected_reasons:
            assert hasattr(OverrideReason, reason_name)
