"""Tests for quality monitoring and auto-switching."""

import pytest
from datetime import datetime

from autopack.generative.quality_monitor import (
    QualityMonitor,
    QualityMetrics,
    ModelQualitySnapshot,
)


class TestQualityMetrics:
    """Test quality metrics calculations."""

    def test_quality_metrics_creation(self):
        """Test creating quality metrics."""
        metrics = QualityMetrics(
            relevance_score=0.9,
            coherence_rating=0.85,
            completeness_score=0.8,
            generation_time=2.5,
        )
        assert metrics.relevance_score == 0.9
        assert metrics.generation_time == 2.5

    def test_overall_score_calculation(self):
        """Test overall score calculation from components."""
        metrics = QualityMetrics(
            relevance_score=1.0,
            coherence_rating=0.8,
            completeness_score=0.6,
            generation_time=2.0,
        )
        # Overall = 1.0 * 0.5 + 0.8 * 0.3 + 0.6 * 0.2 = 0.5 + 0.24 + 0.12 = 0.86
        assert metrics.calculate_overall_score() == pytest.approx(0.86, abs=0.01)

    def test_overall_score_with_user_satisfaction(self):
        """Test overall score with user satisfaction feedback."""
        metrics = QualityMetrics(
            relevance_score=0.8,
            coherence_rating=0.8,
            completeness_score=0.8,
            generation_time=2.0,
            user_satisfaction=0.5,
        )
        # Base score: 0.8 * 0.5 + 0.8 * 0.3 + 0.8 * 0.2 = 0.8
        # With satisfaction: 0.8 * 0.7 + 0.5 * 0.3 = 0.56 + 0.15 = 0.71
        expected = 0.8 * 0.7 + 0.5 * 0.3
        assert metrics.calculate_overall_score() == pytest.approx(expected, abs=0.01)

    def test_overall_score_bounds(self):
        """Test that overall score is bounded 0.0-1.0."""
        # Test with values exceeding bounds (shouldn't happen but test bounds)
        metrics = QualityMetrics(
            relevance_score=0.5,
            coherence_rating=0.5,
            completeness_score=0.5,
            generation_time=1.0,
            user_satisfaction=1.5,  # Exceeds 1.0
        )
        score = metrics.calculate_overall_score()
        assert 0.0 <= score <= 1.0


class TestQualityMonitor:
    """Test quality monitoring."""

    def test_monitor_creation(self):
        """Test creating a quality monitor."""
        monitor = QualityMonitor()
        assert len(monitor.quality_history) == 0
        assert len(monitor.model_stats) == 0

    def test_record_generation(self):
        """Test recording a generation."""
        monitor = QualityMonitor()
        metrics = QualityMetrics(
            relevance_score=0.9,
            coherence_rating=0.85,
            completeness_score=0.8,
            generation_time=2.5,
        )
        monitor.record_generation(
            model_id="model_1",
            provider="provider_a",
            capability_type="image_generation",
            metrics=metrics,
        )

        assert "model_1" in monitor.quality_history
        assert len(monitor.quality_history["model_1"]) == 1
        assert "model_1" in monitor.model_stats
        assert monitor.model_stats["model_1"]["total_generations"] == 1

    def test_record_multiple_generations(self):
        """Test recording multiple generations."""
        monitor = QualityMonitor()

        for i in range(5):
            metrics = QualityMetrics(
                relevance_score=0.8 + i * 0.02,
                coherence_rating=0.75 + i * 0.02,
                completeness_score=0.7 + i * 0.02,
                generation_time=2.0 + i * 0.1,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        assert len(monitor.quality_history["model_1"]) == 5
        assert monitor.model_stats["model_1"]["total_generations"] == 5

    def test_get_model_quality_score(self):
        """Test getting model quality score."""
        monitor = QualityMonitor()

        # Add metrics with known scores
        metrics1 = QualityMetrics(
            relevance_score=1.0,
            coherence_rating=0.8,
            completeness_score=0.6,
            generation_time=2.0,
        )
        metrics2 = QualityMetrics(
            relevance_score=0.8,
            coherence_rating=0.9,
            completeness_score=0.8,
            generation_time=2.0,
        )

        monitor.record_generation(
            model_id="model_1",
            provider="provider_a",
            capability_type="image_generation",
            metrics=metrics1,
        )
        monitor.record_generation(
            model_id="model_1",
            provider="provider_a",
            capability_type="image_generation",
            metrics=metrics2,
        )

        score = monitor.get_model_quality_score("model_1")
        # Average of two overall scores
        score1 = metrics1.calculate_overall_score()
        score2 = metrics2.calculate_overall_score()
        expected = (score1 + score2) / 2
        assert score == pytest.approx(expected, abs=0.01)

    def test_get_model_average_generation_time(self):
        """Test getting average generation time."""
        monitor = QualityMonitor()

        for gen_time in [2.0, 3.0, 1.0]:
            metrics = QualityMetrics(
                relevance_score=0.8,
                coherence_rating=0.8,
                completeness_score=0.8,
                generation_time=gen_time,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        avg_time = monitor.get_model_average_generation_time("model_1")
        assert avg_time == pytest.approx(2.0, abs=0.01)

    def test_get_model_success_rate(self):
        """Test getting model success rate."""
        monitor = QualityMonitor()

        # Record 3 successful generations
        for _ in range(3):
            metrics = QualityMetrics(
                relevance_score=0.8,
                coherence_rating=0.8,
                completeness_score=0.8,
                generation_time=2.0,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        # Record 2 failures
        monitor.record_generation_failure("model_1", provider="provider_a", error="Timeout")
        monitor.record_generation_failure("model_1", provider="provider_a", error="Rate limit")

        success_rate = monitor.get_model_success_rate("model_1")
        assert success_rate == pytest.approx(0.6, abs=0.01)  # 3 out of 5

    def test_record_generation_failure(self):
        """Test recording generation failures."""
        monitor = QualityMonitor()

        # Initialize model stats
        metrics = QualityMetrics(
            relevance_score=0.8,
            coherence_rating=0.8,
            completeness_score=0.8,
            generation_time=2.0,
        )
        monitor.record_generation(
            model_id="model_1",
            provider="provider_a",
            capability_type="image_generation",
            metrics=metrics,
        )

        # Record failures
        monitor.record_generation_failure("model_1", provider="provider_a", error="Error 1")
        monitor.record_generation_failure("model_1", provider="provider_a", error="Error 2")

        assert monitor.model_stats["model_1"]["failed_generations"] == 2
        assert monitor.get_model_success_rate("model_1") == pytest.approx(0.33, abs=0.01)

    def test_evaluate_model_quality_insufficient_data(self):
        """Test quality evaluation with insufficient data."""
        monitor = QualityMonitor()

        # Add only 2 generations (below MIN_GENERATIONS_FOR_EVALUATION)
        for i in range(2):
            metrics = QualityMetrics(
                relevance_score=0.8,
                coherence_rating=0.8,
                completeness_score=0.8,
                generation_time=2.0,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        snapshot = monitor.evaluate_model_quality("model_1")
        assert snapshot is None

    def test_evaluate_model_quality_sufficient_data(self):
        """Test quality evaluation with sufficient data."""
        monitor = QualityMonitor()

        # Add 5+ generations
        for i in range(5):
            metrics = QualityMetrics(
                relevance_score=0.8 + i * 0.02,
                coherence_rating=0.75 + i * 0.02,
                completeness_score=0.7 + i * 0.02,
                generation_time=2.0 + i * 0.1,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        snapshot = monitor.evaluate_model_quality("model_1")
        assert snapshot is not None
        assert snapshot.model_id == "model_1"
        assert snapshot.total_generations == 5
        assert snapshot.quality_trend == "improving"  # Scores increasing
        assert snapshot.success_rate == 1.0  # All successful

    def test_check_quality_thresholds_degradation(self):
        """Test quality degradation alert."""
        monitor = QualityMonitor()

        # Add generations with low quality
        for _ in range(6):
            metrics = QualityMetrics(
                relevance_score=0.5,
                coherence_rating=0.5,
                completeness_score=0.5,
                generation_time=2.0,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        alerts = monitor.check_quality_thresholds("model_1")
        assert len(alerts) > 0
        assert any(a.alert_type == "quality_degradation" for a in alerts)

    def test_check_quality_thresholds_slow_generation(self):
        """Test slow generation alert."""
        monitor = QualityMonitor()

        # Add generations with slow times
        for _ in range(6):
            metrics = QualityMetrics(
                relevance_score=0.8,
                coherence_rating=0.8,
                completeness_score=0.8,
                generation_time=40.0,  # Above SLOW_GENERATION_THRESHOLD
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        alerts = monitor.check_quality_thresholds("model_1")
        assert len(alerts) > 0
        assert any(a.alert_type == "slow_generation" for a in alerts)

    def test_check_quality_thresholds_high_failure_rate(self):
        """Test high failure rate alert."""
        monitor = QualityMonitor()

        # Add successful generations
        for _ in range(3):
            metrics = QualityMetrics(
                relevance_score=0.8,
                coherence_rating=0.8,
                completeness_score=0.8,
                generation_time=2.0,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        # Add many failures
        for _ in range(7):
            monitor.record_generation_failure("model_1", provider="provider_a", error="Error")

        alerts = monitor.check_quality_thresholds("model_1")
        assert len(alerts) > 0
        assert any(a.alert_type == "high_failure_rate" for a in alerts)

    def test_should_switch_model(self):
        """Test model switching recommendation."""
        monitor = QualityMonitor()

        # Add generations for current model
        for i in range(5):
            metrics = QualityMetrics(
                relevance_score=0.6,
                coherence_rating=0.6,
                completeness_score=0.6,
                generation_time=2.0,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        # Check if should switch to a much better model
        result = monitor.should_switch_model(
            current_model_id="model_1",
            alternative_models={
                "model_2": 0.95,  # Much better
                "model_3": 0.55,  # Worse
            },
        )

        assert result is not None
        new_model, reason = result
        assert new_model == "model_2"
        assert "better" in reason.lower()

    def test_should_not_switch_model_small_gap(self):
        """Test that doesn't recommend switch for small quality gap."""
        monitor = QualityMonitor()

        # Add generations for current model
        for i in range(5):
            metrics = QualityMetrics(
                relevance_score=0.8,
                coherence_rating=0.8,
                completeness_score=0.8,
                generation_time=2.0,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        # Check with slightly better alternative
        result = monitor.should_switch_model(
            current_model_id="model_1",
            alternative_models={
                "model_2": 0.85,  # Only slightly better
            },
        )

        assert result is None  # No switch recommended

    def test_get_quality_dashboard(self):
        """Test getting quality dashboard."""
        monitor = QualityMonitor()

        # Add data for two models
        for model_id in ["model_1", "model_2"]:
            for i in range(6):
                metrics = QualityMetrics(
                    relevance_score=0.8 + i * 0.01,
                    coherence_rating=0.8,
                    completeness_score=0.8,
                    generation_time=2.0,
                )
                monitor.record_generation(
                    model_id=model_id,
                    provider="provider_a",
                    capability_type="image_generation",
                    metrics=metrics,
                )

        dashboard = monitor.get_quality_dashboard()
        assert "timestamp" in dashboard
        assert "models" in dashboard
        assert "model_1" in dashboard["models"]
        assert "model_2" in dashboard["models"]
        assert dashboard["total_models_monitored"] >= 2

        # Check model dashboard entries
        for model_id in ["model_1", "model_2"]:
            model_info = dashboard["models"][model_id]
            assert "quality_score" in model_info
            assert "quality_trend" in model_info
            assert "generation_time" in model_info
            assert "success_rate" in model_info

    def test_get_alerts(self):
        """Test getting alerts."""
        monitor = QualityMonitor()

        # Create low quality generations to trigger alerts
        for _ in range(6):
            metrics = QualityMetrics(
                relevance_score=0.4,
                coherence_rating=0.4,
                completeness_score=0.4,
                generation_time=2.0,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        monitor.check_quality_thresholds("model_1")
        alerts = monitor.get_alerts()
        assert len(alerts) > 0

    def test_get_alerts_by_model(self):
        """Test filtering alerts by model."""
        monitor = QualityMonitor()

        # Create low quality for two models
        for model_id in ["model_1", "model_2"]:
            for _ in range(6):
                metrics = QualityMetrics(
                    relevance_score=0.4,
                    coherence_rating=0.4,
                    completeness_score=0.4,
                    generation_time=2.0,
                )
                monitor.record_generation(
                    model_id=model_id,
                    provider="provider_a",
                    capability_type="image_generation",
                    metrics=metrics,
                )

            monitor.check_quality_thresholds(model_id)

        # Get alerts for specific model
        alerts = monitor.get_alerts(model_id="model_1")
        assert all(a.model_id == "model_1" for a in alerts)

    def test_reset_model_tracking(self):
        """Test resetting model quality tracking."""
        monitor = QualityMonitor()

        # Add data
        metrics = QualityMetrics(
            relevance_score=0.8,
            coherence_rating=0.8,
            completeness_score=0.8,
            generation_time=2.0,
        )
        monitor.record_generation(
            model_id="model_1",
            provider="provider_a",
            capability_type="image_generation",
            metrics=metrics,
        )

        assert monitor.model_stats["model_1"]["total_generations"] == 1

        # Reset
        monitor.reset_model_tracking("model_1")

        assert len(monitor.quality_history["model_1"]) == 0
        assert monitor.model_stats["model_1"]["total_generations"] == 0

    def test_get_model_quality_timeline(self):
        """Test getting quality timeline for a model."""
        monitor = QualityMonitor()

        # Add generations to create snapshots
        for i in range(6):
            metrics = QualityMetrics(
                relevance_score=0.8 + i * 0.01,
                coherence_rating=0.8,
                completeness_score=0.8,
                generation_time=2.0,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        # Evaluate to create snapshots
        monitor.evaluate_model_quality("model_1")
        monitor.evaluate_model_quality("model_1")

        timeline = monitor.get_model_quality_timeline("model_1")
        assert len(timeline) >= 1
        assert all(isinstance(s, ModelQualitySnapshot) for s in timeline)
        assert all(s.model_id == "model_1" for s in timeline)

    def test_history_window_limit(self):
        """Test that history is limited to window size."""
        monitor = QualityMonitor()

        # Add more generations than QUALITY_HISTORY_WINDOW
        for i in range(150):
            metrics = QualityMetrics(
                relevance_score=0.8,
                coherence_rating=0.8,
                completeness_score=0.8,
                generation_time=2.0,
            )
            monitor.record_generation(
                model_id="model_1",
                provider="provider_a",
                capability_type="image_generation",
                metrics=metrics,
            )

        # History should not exceed window limit
        assert len(monitor.quality_history["model_1"]) <= monitor.QUALITY_HISTORY_WINDOW

    def test_last_model_for_capability_tracking(self):
        """Test tracking of last used model per capability."""
        monitor = QualityMonitor()

        # Record for different capabilities
        metrics = QualityMetrics(
            relevance_score=0.8,
            coherence_rating=0.8,
            completeness_score=0.8,
            generation_time=2.0,
        )
        monitor.record_generation(
            model_id="model_1",
            provider="provider_a",
            capability_type="image_generation",
            metrics=metrics,
        )
        monitor.record_generation(
            model_id="model_2",
            provider="provider_b",
            capability_type="video_generation",
            metrics=metrics,
        )

        assert monitor.last_model_for_capability["image_generation"] == "model_1"
        assert monitor.last_model_for_capability["video_generation"] == "model_2"
