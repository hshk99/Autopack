"""Unit tests for additional anomaly detection signals.

IMP-TELE-002: Tests for model staleness, policy effectiveness,
cross-phase correlation, memory retrieval quality, and hint effectiveness
anomaly detection.
"""

from datetime import datetime, timedelta


from autopack.telemetry.anomaly_detector import (
    AlertSeverity,
    TelemetryAnomalyDetector,
)


class TestModelStalenessDetection:
    """Tests for detect_model_staleness() method."""

    def test_no_alert_when_no_models_registered(self):
        """No alert when no models have been registered."""
        detector = TelemetryAnomalyDetector()
        alert = detector.detect_model_staleness()
        assert alert is None

    def test_no_alert_when_models_fresh(self):
        """No alert when models are recently updated."""
        detector = TelemetryAnomalyDetector(staleness_threshold_hours=24.0)
        detector.record_model_update("embeddings")
        detector.record_model_update("learning_model")

        alert = detector.detect_model_staleness()
        assert alert is None

    def test_alert_when_model_stale(self):
        """Alert generated when model exceeds staleness threshold."""
        detector = TelemetryAnomalyDetector(staleness_threshold_hours=24.0)

        # Set model update time to 30 hours ago
        stale_time = datetime.utcnow() - timedelta(hours=30)
        detector.model_update_times["embeddings"] = stale_time

        alert = detector.detect_model_staleness()

        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING
        assert alert.metric == "model_staleness"
        assert "embeddings" in alert.recommendation
        assert alert.current_value > 24.0

    def test_alert_includes_most_stale_model(self):
        """Alert identifies the most stale model."""
        detector = TelemetryAnomalyDetector(staleness_threshold_hours=24.0)

        # One model 30 hours stale, one 50 hours stale
        detector.model_update_times["model_a"] = datetime.utcnow() - timedelta(hours=30)
        detector.model_update_times["model_b"] = datetime.utcnow() - timedelta(hours=50)

        alert = detector.detect_model_staleness()

        assert alert is not None
        assert "model_b" in alert.recommendation
        assert alert.current_value > 48.0  # model_b is most stale


class TestPolicyEffectivenessDegradation:
    """Tests for detect_policy_effectiveness_degradation() method."""

    def test_no_alert_with_insufficient_history(self):
        """No alert when not enough policy outcomes recorded."""
        detector = TelemetryAnomalyDetector()

        # Record only 5 outcomes (need 10)
        for _ in range(5):
            detector.record_policy_outcome("test_policy", success=True)

        alert = detector.detect_policy_effectiveness_degradation()
        assert alert is None

    def test_no_alert_when_effectiveness_stable(self):
        """No alert when policy effectiveness is stable."""
        detector = TelemetryAnomalyDetector(policy_degradation_threshold=0.15)

        # Record stable success (80% throughout)
        for i in range(20):
            detector.record_policy_outcome("test_policy", success=(i % 5 != 0))

        alert = detector.detect_policy_effectiveness_degradation()
        assert alert is None

    def test_alert_on_effectiveness_degradation(self):
        """Alert when policy effectiveness degrades significantly."""
        detector = TelemetryAnomalyDetector(policy_degradation_threshold=0.15)

        # First half: 100% success
        for _ in range(10):
            detector.record_policy_outcome("degrading_policy", success=True)

        # Second half: 50% success (significant degradation)
        for i in range(10):
            detector.record_policy_outcome("degrading_policy", success=(i % 2 == 0))

        alert = detector.detect_policy_effectiveness_degradation()

        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING
        assert alert.metric == "policy_effectiveness"
        assert "degrading_policy" in alert.recommendation

    def test_tracks_multiple_policies(self):
        """Can track multiple policies independently."""
        detector = TelemetryAnomalyDetector()

        # Policy A: stable
        for _ in range(20):
            detector.record_policy_outcome("policy_a", success=True)

        # Policy B: degrading
        for _ in range(10):
            detector.record_policy_outcome("policy_b", success=True)
        for _ in range(10):
            detector.record_policy_outcome("policy_b", success=False)

        alert = detector.detect_policy_effectiveness_degradation()

        assert alert is not None
        assert "policy_b" in alert.recommendation


class TestCrossPhaseCorrelation:
    """Tests for detect_cross_phase_correlation() method."""

    def test_no_alert_with_single_phase(self):
        """No alert when only one phase type tracked."""
        detector = TelemetryAnomalyDetector()

        for _ in range(10):
            detector.record_phase_outcome_for_correlation("phase_a", success=True)

        alert = detector.detect_cross_phase_correlation()
        assert alert is None

    def test_no_alert_with_insufficient_aligned_data(self):
        """No alert when phases don't have aligned timestamps."""
        detector = TelemetryAnomalyDetector()

        # Record phases at very different times (won't align)
        now = datetime.utcnow()
        for i in range(10):
            detector.record_phase_outcome_for_correlation(
                "phase_a", success=True, timestamp=now - timedelta(hours=i * 2)
            )
            detector.record_phase_outcome_for_correlation(
                "phase_b", success=True, timestamp=now - timedelta(hours=i * 2 + 1)
            )

        alert = detector.detect_cross_phase_correlation()
        assert alert is None  # No aligned data

    def test_establishes_baseline_correlation(self):
        """First run establishes baseline, no alert."""
        detector = TelemetryAnomalyDetector()

        now = datetime.utcnow()
        for i in range(10):
            ts = now - timedelta(seconds=i * 30)
            detector.record_phase_outcome_for_correlation("phase_a", success=True, timestamp=ts)
            detector.record_phase_outcome_for_correlation("phase_b", success=True, timestamp=ts)

        alert = detector.detect_cross_phase_correlation()
        assert alert is None  # First run sets baseline

        # Verify baseline was set
        assert ("phase_a", "phase_b") in detector.phase_correlation_baseline

    def test_alert_on_correlation_shift(self):
        """Alert when correlation shifts significantly."""
        detector = TelemetryAnomalyDetector(correlation_change_threshold=0.3)

        now = datetime.utcnow()

        # Pre-set a high baseline correlation
        detector.phase_correlation_baseline[("phase_a", "phase_b")] = 0.9

        # Add anti-correlated data (should trigger alert due to shift from 0.9 baseline)
        for i in range(10):
            ts = now + timedelta(seconds=i * 10)
            # When phase_a succeeds, phase_b fails and vice versa
            detector.record_phase_outcome_for_correlation(
                "phase_a", success=(i % 2 == 0), timestamp=ts
            )
            detector.record_phase_outcome_for_correlation(
                "phase_b", success=(i % 2 != 0), timestamp=ts
            )

        alert = detector.detect_cross_phase_correlation()

        assert alert is not None
        assert alert.metric == "cross_phase_correlation"
        assert "phase_a" in alert.phase_id
        assert "phase_b" in alert.phase_id


class TestMemoryRetrievalQuality:
    """Tests for detect_memory_retrieval_quality() method."""

    def test_no_alert_with_insufficient_history(self):
        """No alert when not enough retrieval data."""
        detector = TelemetryAnomalyDetector()

        # Only 3 records (need 5)
        for _ in range(3):
            detector.record_retrieval_quality(relevance_score=0.8, hit_count=5)

        alert = detector.detect_memory_retrieval_quality()
        assert alert is None

    def test_no_alert_when_quality_good(self):
        """No alert when retrieval quality is good."""
        detector = TelemetryAnomalyDetector(retrieval_quality_min_threshold=0.5)

        for _ in range(10):
            detector.record_retrieval_quality(relevance_score=0.8, hit_count=5)

        alert = detector.detect_memory_retrieval_quality()
        assert alert is None

    def test_alert_on_low_relevance(self):
        """Alert when average relevance score is too low."""
        detector = TelemetryAnomalyDetector(retrieval_quality_min_threshold=0.5)

        for _ in range(10):
            detector.record_retrieval_quality(relevance_score=0.3, hit_count=5)

        alert = detector.detect_memory_retrieval_quality()

        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING
        assert alert.metric == "memory_retrieval_quality"
        assert alert.current_value < 0.5

    def test_alert_on_low_hit_count(self):
        """Alert when retrieval returns too few results."""
        detector = TelemetryAnomalyDetector()

        for _ in range(10):
            detector.record_retrieval_quality(relevance_score=0.8, hit_count=0)

        alert = detector.detect_memory_retrieval_quality()

        assert alert is not None
        assert (
            "few results" in alert.recommendation.lower() or "hits" in alert.recommendation.lower()
        )

    def test_includes_trend_in_recommendation(self):
        """Alert recommendation includes trend information."""
        detector = TelemetryAnomalyDetector(retrieval_quality_min_threshold=0.5)

        # First half: moderate quality
        for _ in range(5):
            detector.record_retrieval_quality(relevance_score=0.4, hit_count=3)

        # Second half: worse quality (declining trend)
        for _ in range(5):
            detector.record_retrieval_quality(relevance_score=0.2, hit_count=1)

        alert = detector.detect_memory_retrieval_quality()

        assert alert is not None
        assert "declining" in alert.recommendation.lower()


class TestHintEffectivenessRegression:
    """Tests for detect_hint_effectiveness_regression() method."""

    def test_no_alert_with_insufficient_history(self):
        """No alert when not enough hint outcomes recorded."""
        detector = TelemetryAnomalyDetector()

        # Only 5 records (need 10)
        for _ in range(5):
            detector.record_hint_outcome(hint_was_applied=True, phase_succeeded=True)

        alert = detector.detect_hint_effectiveness_regression()
        assert alert is None

    def test_no_alert_when_hints_effective(self):
        """No alert when hints are working well."""
        detector = TelemetryAnomalyDetector(hint_effectiveness_min_threshold=0.3)

        # Hints applied with 80% success
        for i in range(20):
            detector.record_hint_outcome(hint_was_applied=True, phase_succeeded=(i % 5 != 0))

        alert = detector.detect_hint_effectiveness_regression()
        assert alert is None

    def test_alert_on_low_hint_effectiveness(self):
        """Alert when hint effectiveness is too low."""
        detector = TelemetryAnomalyDetector(hint_effectiveness_min_threshold=0.3)

        # Hints applied but only 20% success
        for i in range(20):
            detector.record_hint_outcome(hint_was_applied=True, phase_succeeded=(i % 5 == 0))

        alert = detector.detect_hint_effectiveness_regression()

        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING
        assert alert.metric == "hint_effectiveness"
        assert alert.current_value < 0.3

    def test_alert_on_hint_regression(self):
        """Alert when hint effectiveness regresses over time."""
        detector = TelemetryAnomalyDetector(
            hint_effectiveness_min_threshold=0.3,
            policy_degradation_threshold=0.15,
        )

        # First half: 100% success with hints
        for _ in range(10):
            detector.record_hint_outcome(hint_was_applied=True, phase_succeeded=True)

        # Second half: 50% success with hints (regression)
        for i in range(10):
            detector.record_hint_outcome(hint_was_applied=True, phase_succeeded=(i % 2 == 0))

        alert = detector.detect_hint_effectiveness_regression()

        assert alert is not None
        assert "regress" in alert.recommendation.lower()

    def test_compares_with_without_hints(self):
        """Tracks both with-hint and without-hint success rates."""
        detector = TelemetryAnomalyDetector(hint_effectiveness_min_threshold=0.3)

        # With hints: low success
        for _ in range(10):
            detector.record_hint_outcome(hint_was_applied=True, phase_succeeded=False)

        # Without hints: some records
        for _ in range(10):
            detector.record_hint_outcome(hint_was_applied=False, phase_succeeded=True)

        alert = detector.detect_hint_effectiveness_regression()

        assert alert is not None
        # Should mention comparison between with/without hints
        assert (
            "without hints" in alert.recommendation.lower()
            or "benefit" in alert.recommendation.lower()
        )


class TestRunAllDetections:
    """Tests for run_all_detections() batch method."""

    def test_runs_all_detectors(self):
        """Runs all detection methods and collects alerts."""
        detector = TelemetryAnomalyDetector(
            staleness_threshold_hours=24.0,
            retrieval_quality_min_threshold=0.5,
        )

        # Trigger model staleness alert
        detector.model_update_times["test_model"] = datetime.utcnow() - timedelta(hours=48)

        # Trigger retrieval quality alert
        for _ in range(10):
            detector.record_retrieval_quality(relevance_score=0.2, hit_count=0)

        alerts = detector.run_all_detections()

        # Should have at least 2 alerts
        assert len(alerts) >= 2

        metrics = [a.metric for a in alerts]
        assert "model_staleness" in metrics
        assert "memory_retrieval_quality" in metrics

    def test_handles_detector_failures_gracefully(self):
        """Continues running other detectors if one fails."""
        detector = TelemetryAnomalyDetector()

        # Corrupt internal state to cause one detector to fail
        detector.policy_effectiveness_history["bad_policy"] = "not_a_list"

        # Should not raise, other detectors should still run
        alerts = detector.run_all_detections()

        # Should complete without error
        assert isinstance(alerts, list)

    def test_returns_empty_list_when_no_anomalies(self):
        """Returns empty list when everything is healthy."""
        detector = TelemetryAnomalyDetector()

        alerts = detector.run_all_detections()

        assert alerts == []


class TestPendingAlertsIntegration:
    """Tests for pending alerts collection across detectors."""

    def test_alerts_added_to_pending(self):
        """Alerts are added to pending_alerts list."""
        detector = TelemetryAnomalyDetector(staleness_threshold_hours=24.0)

        detector.model_update_times["stale_model"] = datetime.utcnow() - timedelta(hours=48)
        detector.detect_model_staleness()

        pending = detector.get_pending_alerts(clear=False)
        assert len(pending) >= 1
        assert any(a.metric == "model_staleness" for a in pending)

    def test_get_pending_alerts_clears_by_default(self):
        """get_pending_alerts clears the list by default."""
        detector = TelemetryAnomalyDetector(staleness_threshold_hours=24.0)

        detector.model_update_times["stale_model"] = datetime.utcnow() - timedelta(hours=48)
        detector.detect_model_staleness()

        first_get = detector.get_pending_alerts()
        second_get = detector.get_pending_alerts()

        assert len(first_get) >= 1
        assert len(second_get) == 0

    def test_get_pending_alerts_preserves_when_clear_false(self):
        """get_pending_alerts preserves list when clear=False."""
        detector = TelemetryAnomalyDetector(staleness_threshold_hours=24.0)

        detector.model_update_times["stale_model"] = datetime.utcnow() - timedelta(hours=48)
        detector.detect_model_staleness()

        first_get = detector.get_pending_alerts(clear=False)
        second_get = detector.get_pending_alerts(clear=False)

        assert len(first_get) == len(second_get)
