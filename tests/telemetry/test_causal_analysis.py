"""Tests for ROAD-H causal analysis."""

from datetime import datetime, timedelta

import pytest

from autopack.telemetry.causal_analysis import (
    CausalAnalyzer,
    CausalStrength,
    ChangeEvent,
    OutcomeMetric,
)


@pytest.fixture
def analyzer():
    """Create causal analyzer with default settings."""
    return CausalAnalyzer(
        significance_level=0.05,
        min_sample_size=10,
        temporal_window_hours=24.0,
        effect_size_threshold=0.10,
    )


@pytest.fixture
def code_change():
    """Sample code change event."""
    return ChangeEvent(
        change_id="CHG_001",
        change_type="code",
        timestamp=datetime.now(),
        affected_components=["executor", "builder"],
        description="Optimize token usage in code generation phase",
        metadata={"pr_number": 123, "author": "dev@example.com"},
    )


@pytest.fixture
def baseline_token_metrics():
    """Baseline token usage metrics (before change)."""
    base_time = datetime.now() - timedelta(hours=48)
    return {
        "token_usage": [
            OutcomeMetric(
                metric_name="token_usage",
                value=10000 + i * 100,
                timestamp=base_time + timedelta(hours=i),
                phase_id="code_generation",
                run_id=f"run_{i}",
            )
            for i in range(20)
        ]
    }


@pytest.fixture
def improved_token_metrics(code_change):
    """Improved token usage metrics (after change with 30% reduction)."""
    return {
        "token_usage": [
            OutcomeMetric(
                metric_name="token_usage",
                value=7000 + i * 70,  # 30% reduction
                timestamp=code_change.timestamp + timedelta(hours=i + 1),
                phase_id="code_generation",
                run_id=f"run_{20 + i}",
            )
            for i in range(20)
        ]
    }


@pytest.fixture
def degraded_duration_metrics(code_change):
    """Degraded duration metrics (after change with 50% increase)."""
    return {
        "duration": [
            OutcomeMetric(
                metric_name="duration",
                value=15.0 + i * 0.75,  # 50% increase
                timestamp=code_change.timestamp + timedelta(hours=i + 1),
                phase_id="code_generation",
                run_id=f"run_{20 + i}",
            )
            for i in range(20)
        ]
    }


@pytest.fixture
def baseline_duration_metrics():
    """Baseline duration metrics (before change)."""
    base_time = datetime.now() - timedelta(hours=48)
    return {
        "duration": [
            OutcomeMetric(
                metric_name="duration",
                value=10.0 + i * 0.5,
                timestamp=base_time + timedelta(hours=i),
                phase_id="code_generation",
                run_id=f"run_{i}",
            )
            for i in range(20)
        ]
    }


def test_analyzer_initialization():
    """Test CausalAnalyzer initialization."""
    analyzer = CausalAnalyzer(
        significance_level=0.01,
        min_sample_size=20,
        temporal_window_hours=48.0,
        effect_size_threshold=0.15,
    )

    assert analyzer.significance_level == 0.01
    assert analyzer.min_sample_size == 20
    assert analyzer.temporal_window == timedelta(hours=48)
    assert analyzer.effect_size_threshold == 0.15


def test_analyze_positive_impact(
    analyzer, code_change, baseline_token_metrics, improved_token_metrics
):
    """Test causal analysis for positive impact (token reduction)."""
    report = analyzer.analyze_change_impact(
        change_event=code_change,
        baseline_metrics=baseline_token_metrics,
        post_change_metrics=improved_token_metrics,
    )

    assert report.change_event == code_change
    assert len(report.relationships) > 0
    assert report.overall_impact == "positive"
    assert report.metrics_improved >= 1
    assert report.confidence > 0.5

    # Check token relationship
    token_rel = next(r for r in report.relationships if r.outcome_metric == "token_usage")
    assert token_rel.effect_direction == "positive"  # Lower tokens = improvement
    assert token_rel.causal_strength in [CausalStrength.STRONG, CausalStrength.MODERATE]
    assert token_rel.temporal_precedence is True
    assert token_rel.percent_change < -20  # At least 20% reduction


def test_analyze_negative_impact(
    analyzer, code_change, baseline_duration_metrics, degraded_duration_metrics
):
    """Test causal analysis for negative impact (duration increase)."""
    report = analyzer.analyze_change_impact(
        change_event=code_change,
        baseline_metrics=baseline_duration_metrics,
        post_change_metrics=degraded_duration_metrics,
    )

    assert report.overall_impact == "negative"
    assert report.metrics_degraded >= 1

    # Check duration relationship
    duration_rel = next(r for r in report.relationships if r.outcome_metric == "duration")
    assert duration_rel.effect_direction == "negative"  # Higher duration = degradation
    assert duration_rel.causal_strength in [CausalStrength.STRONG, CausalStrength.MODERATE]


def test_analyze_mixed_impact(
    analyzer,
    code_change,
    baseline_token_metrics,
    baseline_duration_metrics,
    improved_token_metrics,
    degraded_duration_metrics,
):
    """Test causal analysis with mixed impact (some metrics improve, others degrade)."""
    baseline = {**baseline_token_metrics, **baseline_duration_metrics}
    post_change = {**improved_token_metrics, **degraded_duration_metrics}

    report = analyzer.analyze_change_impact(
        change_event=code_change, baseline_metrics=baseline, post_change_metrics=post_change
    )

    assert report.overall_impact == "mixed"
    assert report.metrics_improved >= 1
    assert report.metrics_degraded >= 1
    assert "tradeoffs" in " ".join(report.recommendations).lower()


def test_temporal_precedence_verification(analyzer, code_change):
    """Test that temporal precedence is correctly verified."""
    # Metrics before change
    before_metrics = [
        OutcomeMetric(
            metric_name="test_metric",
            value=100,
            timestamp=code_change.timestamp - timedelta(hours=1),
            phase_id="test",
            run_id="run_1",
        )
    ]

    # Metrics after change
    after_metrics = [
        OutcomeMetric(
            metric_name="test_metric",
            value=80,
            timestamp=code_change.timestamp + timedelta(hours=1),
            phase_id="test",
            run_id="run_2",
        )
    ]

    # Should pass precedence check
    precedence = analyzer._verify_temporal_precedence(code_change, before_metrics, after_metrics)
    assert precedence is True

    # Metrics "after" that are actually before change should fail
    invalid_after = [
        OutcomeMetric(
            metric_name="test_metric",
            value=80,
            timestamp=code_change.timestamp - timedelta(hours=1),
            phase_id="test",
            run_id="run_2",
        )
    ]

    precedence = analyzer._verify_temporal_precedence(code_change, before_metrics, invalid_after)
    assert precedence is False


def test_insufficient_samples_ignored(analyzer, code_change):
    """Test that metrics with insufficient samples are ignored."""
    # Only 5 samples (< min_sample_size of 10)
    small_baseline = {
        "test_metric": [
            OutcomeMetric(
                metric_name="test_metric",
                value=100 + i,
                timestamp=datetime.now() - timedelta(hours=10 + i),
                phase_id="test",
                run_id=f"run_{i}",
            )
            for i in range(5)
        ]
    }

    small_post = {
        "test_metric": [
            OutcomeMetric(
                metric_name="test_metric",
                value=80 + i,
                timestamp=datetime.now() + timedelta(hours=i),
                phase_id="test",
                run_id=f"run_{5 + i}",
            )
            for i in range(5)
        ]
    }

    report = analyzer.analyze_change_impact(
        change_event=code_change, baseline_metrics=small_baseline, post_change_metrics=small_post
    )

    # Should have no relationships due to insufficient samples
    assert len(report.relationships) == 0


def test_confounding_factor_detection(
    analyzer, code_change, baseline_token_metrics, improved_token_metrics
):
    """Test detection of confounding changes."""
    # Another change that happened around the same time
    confounding_change = ChangeEvent(
        change_id="CHG_002",
        change_type="config",
        timestamp=code_change.timestamp + timedelta(hours=2),
        affected_components=["executor"],
        description="Update model configuration",
    )

    report = analyzer.analyze_change_impact(
        change_event=code_change,
        baseline_metrics=baseline_token_metrics,
        post_change_metrics=improved_token_metrics,
        confounding_changes=[confounding_change],
    )

    # Should detect confounding factor
    token_rel = next(r for r in report.relationships if r.outcome_metric == "token_usage")
    assert len(token_rel.confounding_factors) > 0
    assert any("config" in conf.lower() for conf in token_rel.confounding_factors)


def test_high_variance_baseline_detected(analyzer, code_change):
    """Test detection of high variance in baseline (unstable metric)."""
    # Baseline with high variance
    high_variance_baseline = {
        "unstable_metric": [
            OutcomeMetric(
                metric_name="unstable_metric",
                value=100 if i % 2 == 0 else 200,  # High variance
                timestamp=datetime.now() - timedelta(hours=20 - i),
                phase_id="test",
                run_id=f"run_{i}",
            )
            for i in range(15)
        ]
    }

    stable_post = {
        "unstable_metric": [
            OutcomeMetric(
                metric_name="unstable_metric",
                value=120 + i,
                timestamp=code_change.timestamp + timedelta(hours=i),
                phase_id="test",
                run_id=f"run_{15 + i}",
            )
            for i in range(15)
        ]
    }

    report = analyzer.analyze_change_impact(
        change_event=code_change,
        baseline_metrics=high_variance_baseline,
        post_change_metrics=stable_post,
    )

    # Should detect high baseline variance
    if report.relationships:
        rel = report.relationships[0]
        assert any("variance" in conf.lower() for conf in rel.confounding_factors)


def test_causal_strength_determination(analyzer):
    """Test determination of causal strength based on statistics."""
    # Strong causality: low p-value, large effect, temporal precedence, no confounders
    strength = analyzer._determine_causal_strength(
        p_value=0.01, effect_size=1.0, temporal_precedence=True, confounders=[]
    )
    assert strength == CausalStrength.STRONG

    # Moderate causality: low p-value, medium effect
    strength = analyzer._determine_causal_strength(
        p_value=0.04, effect_size=0.6, temporal_precedence=True, confounders=[]
    )
    assert strength == CausalStrength.MODERATE

    # Weak causality: low p-value, small effect
    strength = analyzer._determine_causal_strength(
        p_value=0.04, effect_size=0.3, temporal_precedence=True, confounders=[]
    )
    assert strength == CausalStrength.WEAK

    # No causality: high p-value
    strength = analyzer._determine_causal_strength(
        p_value=0.50, effect_size=0.5, temporal_precedence=True, confounders=[]
    )
    assert strength == CausalStrength.NONE

    # No temporal precedence = no causality
    strength = analyzer._determine_causal_strength(
        p_value=0.01, effect_size=1.0, temporal_precedence=False, confounders=[]
    )
    assert strength == CausalStrength.NONE

    # Confounded: multiple confounders present
    strength = analyzer._determine_causal_strength(
        p_value=0.01,
        effect_size=1.0,
        temporal_precedence=True,
        confounders=["factor1", "factor2"],
    )
    assert strength == CausalStrength.CONFOUNDED


def test_confidence_computation(analyzer):
    """Test confidence score computation."""
    # High confidence: low p-value, large effect, large sample, no confounders
    confidence = analyzer._compute_confidence(
        p_value=0.01,
        effect_size=1.0,
        sample_size=100,
        temporal_precedence=True,
        confounders=[],
    )
    assert confidence >= 0.85

    # Medium confidence: moderate p-value, medium effect
    confidence = analyzer._compute_confidence(
        p_value=0.08,
        effect_size=0.5,
        sample_size=30,
        temporal_precedence=True,
        confounders=[],
    )
    assert 0.5 <= confidence < 0.8

    # Low confidence: high p-value or small sample
    confidence = analyzer._compute_confidence(
        p_value=0.15,
        effect_size=0.2,
        sample_size=15,
        temporal_precedence=True,
        confounders=["factor1"],
    )
    assert confidence < 0.6


def test_is_improvement_lower_is_better(analyzer):
    """Test improvement detection for metrics where lower is better."""
    # Token usage: lower is better
    assert analyzer._is_improvement("token_usage", 8000, 10000) is True
    assert analyzer._is_improvement("token_usage", 12000, 10000) is False

    # Duration: lower is better
    assert analyzer._is_improvement("duration", 5.0, 10.0) is True
    assert analyzer._is_improvement("duration", 15.0, 10.0) is False

    # Cost: lower is better
    assert analyzer._is_improvement("cost", 1.0, 2.0) is True
    assert analyzer._is_improvement("cost", 3.0, 2.0) is False


def test_is_improvement_higher_is_better(analyzer):
    """Test improvement detection for metrics where higher is better."""
    # Success rate: higher is better
    assert analyzer._is_improvement("success_rate", 0.95, 0.85) is True
    assert analyzer._is_improvement("success_rate", 0.75, 0.85) is False

    # Quality score: higher is better
    assert analyzer._is_improvement("quality_score", 90, 80) is True
    assert analyzer._is_improvement("quality_score", 70, 80) is False


def test_explanation_generation(analyzer, code_change):
    """Test generation of human-readable explanations."""
    explanation = analyzer._generate_explanation(
        change_event=code_change,
        metric_name="token_usage",
        effect_direction="positive",
        percent_change=-30.0,
        causal_strength=CausalStrength.STRONG,
        confounders=[],
    )

    assert "Optimize token usage" in explanation
    assert "likely caused" in explanation
    assert "improved" in explanation
    assert "30" in explanation


def test_recommendations_for_positive_impact(
    analyzer, code_change, baseline_token_metrics, improved_token_metrics
):
    """Test recommendations generated for positive impact."""
    report = analyzer.analyze_change_impact(
        change_event=code_change,
        baseline_metrics=baseline_token_metrics,
        post_change_metrics=improved_token_metrics,
    )

    assert len(report.recommendations) > 0
    recommendations_text = " ".join(report.recommendations).lower()
    assert any(word in recommendations_text for word in ["promote", "production", "improvement"])


def test_recommendations_for_negative_impact(
    analyzer, code_change, baseline_duration_metrics, degraded_duration_metrics
):
    """Test recommendations generated for negative impact."""
    report = analyzer.analyze_change_impact(
        change_event=code_change,
        baseline_metrics=baseline_duration_metrics,
        post_change_metrics=degraded_duration_metrics,
    )

    recommendations_text = " ".join(report.recommendations).lower()
    assert any(word in recommendations_text for word in ["rollback", "degradation"])


def test_recommendations_for_confounded_results(
    analyzer, code_change, baseline_token_metrics, improved_token_metrics
):
    """Test recommendations when confounding factors are present."""
    confounding_change = ChangeEvent(
        change_id="CHG_002",
        change_type="config",
        timestamp=code_change.timestamp + timedelta(hours=1),
        affected_components=["executor"],
        description="Config update",
    )

    report = analyzer.analyze_change_impact(
        change_event=code_change,
        baseline_metrics=baseline_token_metrics,
        post_change_metrics=improved_token_metrics,
        confounding_changes=[confounding_change],
    )

    recommendations_text = " ".join(report.recommendations).lower()
    assert any(word in recommendations_text for word in ["confound", "controlled", "isolate"])


def test_correlation_computation(analyzer):
    """Test correlation coefficient computation."""
    # Positive correlation: post-change values higher
    correlation = analyzer._compute_correlation(
        baseline=[10, 12, 11, 13, 12],
        post_change=[18, 20, 19, 21, 20],
    )
    assert correlation > 0

    # Negative correlation: post-change values lower
    correlation = analyzer._compute_correlation(
        baseline=[18, 20, 19, 21, 20],
        post_change=[10, 12, 11, 13, 12],
    )
    assert correlation < 0

    # No correlation: no change
    correlation = analyzer._compute_correlation(
        baseline=[15, 15, 15, 15, 15],
        post_change=[15, 15, 15, 15, 15],
    )
    assert abs(correlation) < 0.1


def test_p_value_computation(analyzer):
    """Test p-value computation for statistical significance."""
    # Large difference should give low p-value
    p_value = analyzer._compute_p_value(
        baseline=[10.0] * 20,
        post_change=[20.0] * 20,
        baseline_std=1.0,
        post_std=1.0,
        baseline_mean=10.0,
        post_mean=20.0,
    )
    assert p_value < 0.05  # Statistically significant

    # Small difference should give high p-value
    p_value = analyzer._compute_p_value(
        baseline=[10.0] * 20,
        post_change=[10.5] * 20,
        baseline_std=2.0,
        post_std=2.0,
        baseline_mean=10.0,
        post_mean=10.5,
    )
    assert p_value > 0.05  # Not statistically significant


def test_analysis_report_structure(
    analyzer, code_change, baseline_token_metrics, improved_token_metrics
):
    """Test that analysis report has correct structure."""
    report = analyzer.analyze_change_impact(
        change_event=code_change,
        baseline_metrics=baseline_token_metrics,
        post_change_metrics=improved_token_metrics,
    )

    # Check required fields
    assert hasattr(report, "analysis_id")
    assert hasattr(report, "change_event")
    assert hasattr(report, "relationships")
    assert hasattr(report, "overall_impact")
    assert hasattr(report, "confidence")
    assert hasattr(report, "metrics_improved")
    assert hasattr(report, "metrics_degraded")
    assert hasattr(report, "metrics_unchanged")
    assert hasattr(report, "recommendations")
    assert hasattr(report, "timestamp")

    # Check values
    assert report.change_event == code_change
    assert report.overall_impact in ["positive", "negative", "neutral", "mixed"]
    assert 0.0 <= report.confidence <= 1.0
    assert report.metrics_improved + report.metrics_degraded + report.metrics_unchanged >= 0


def test_causal_relationship_structure(
    analyzer, code_change, baseline_token_metrics, improved_token_metrics
):
    """Test that CausalRelationship has correct structure."""
    report = analyzer.analyze_change_impact(
        change_event=code_change,
        baseline_metrics=baseline_token_metrics,
        post_change_metrics=improved_token_metrics,
    )

    assert len(report.relationships) > 0
    rel = report.relationships[0]

    # Check required fields
    assert hasattr(rel, "change_event")
    assert hasattr(rel, "outcome_metric")
    assert hasattr(rel, "causal_strength")
    assert hasattr(rel, "confidence")
    assert hasattr(rel, "effect_size")
    assert hasattr(rel, "effect_direction")
    assert hasattr(rel, "correlation_coefficient")
    assert hasattr(rel, "temporal_precedence")
    assert hasattr(rel, "p_value")
    assert hasattr(rel, "sample_size")
    assert hasattr(rel, "baseline_mean")
    assert hasattr(rel, "post_change_mean")
    assert hasattr(rel, "percent_change")
    assert hasattr(rel, "confounding_factors")
    assert hasattr(rel, "explanation")

    # Check value types and ranges
    assert isinstance(rel.causal_strength, CausalStrength)
    assert 0.0 <= rel.confidence <= 1.0
    assert rel.effect_direction in ["positive", "negative", "neutral"]
    assert 0.0 <= rel.p_value <= 1.0
    assert rel.sample_size > 0
    assert isinstance(rel.confounding_factors, list)
