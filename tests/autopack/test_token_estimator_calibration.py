"""Calibration-specific tests for token_estimator.py.

Tests cover:
- PHASE_OVERHEAD changes and tracking
- Damped updates and smoothing
- Confidence scoring and thresholds
- Calibration lifecycle and persistence
- Edge cases and boundary conditions

NOTE: This is an extended test suite for planned token estimator calibration features.
Tests are marked xfail until the enhanced calibration API is implemented.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, patch

pytestmark = [
    pytest.mark.xfail(strict=False, reason="Token estimator calibration API not implemented - aspirational test suite"),
    pytest.mark.aspirational
]

from autopack.token_estimator import TokenEstimator


class TestPhaseOverheadCalibration:
    """Test PHASE_OVERHEAD changes and tracking."""

    @pytest.fixture
    def estimator(self):
        """Create TokenEstimator instance."""
        return TokenEstimator()

    def test_initial_phase_overhead_value(self, estimator):
        """Test that PHASE_OVERHEAD starts at default value."""
        # Default PHASE_OVERHEAD should be 500 tokens
        assert estimator.PHASE_OVERHEAD == 500

    def test_phase_overhead_increases_on_underestimation(self, estimator):
        """Test that PHASE_OVERHEAD increases when consistently underestimating."""
        initial_overhead = estimator.PHASE_OVERHEAD

        # Simulate multiple underestimations
        for _ in range(5):
            estimator.record_actual_usage(
                phase_id="test_phase",
                estimated_tokens=1000,
                actual_tokens=1600,  # 60% over estimate
                model="claude-sonnet-4"
            )

        # PHASE_OVERHEAD should increase
        assert estimator.PHASE_OVERHEAD > initial_overhead

    def test_phase_overhead_decreases_on_overestimation(self, estimator):
        """Test that PHASE_OVERHEAD decreases when consistently overestimating."""
        # Set higher initial overhead
        estimator.PHASE_OVERHEAD = 1000
        initial_overhead = estimator.PHASE_OVERHEAD

        # Simulate multiple overestimations
        for _ in range(5):
            estimator.record_actual_usage(
                phase_id="test_phase",
                estimated_tokens=2000,
                actual_tokens=1200,  # 40% under actual
                model="claude-sonnet-4"
            )

        # PHASE_OVERHEAD should decrease
        assert estimator.PHASE_OVERHEAD < initial_overhead

    def test_phase_overhead_bounded(self, estimator):
        """Test that PHASE_OVERHEAD stays within reasonable bounds."""
        # Try to push overhead very high
        for _ in range(20):
            estimator.record_actual_usage(
                phase_id="test_phase",
                estimated_tokens=1000,
                actual_tokens=5000,  # Extreme underestimation
                model="claude-sonnet-4"
            )

        # Should have upper bound (e.g., 2000 tokens)
        assert estimator.PHASE_OVERHEAD <= 2000

        # Try to push overhead very low
        estimator.PHASE_OVERHEAD = 500
        for _ in range(20):
            estimator.record_actual_usage(
                phase_id="test_phase",
                estimated_tokens=2000,
                actual_tokens=1100,  # Extreme overestimation
                model="claude-sonnet-4"
            )

        # Should have lower bound (e.g., 200 tokens)
        assert estimator.PHASE_OVERHEAD >= 200

    def test_phase_overhead_persists_across_phases(self, estimator):
        """Test that PHASE_OVERHEAD changes persist across different phases."""
        initial_overhead = estimator.PHASE_OVERHEAD

        # Record usage for phase 1
        estimator.record_actual_usage(
            phase_id="phase_001",
            estimated_tokens=1000,
            actual_tokens=1600,
            model="claude-sonnet-4"
        )

        overhead_after_phase1 = estimator.PHASE_OVERHEAD

        # Record usage for phase 2
        estimator.record_actual_usage(
            phase_id="phase_002",
            estimated_tokens=1000,
            actual_tokens=1600,
            model="claude-sonnet-4"
        )

        # Overhead should continue to adjust
        assert estimator.PHASE_OVERHEAD >= overhead_after_phase1


class TestDampedUpdates:
    """Test damped updates and smoothing."""

    @pytest.fixture
    def estimator(self):
        """Create TokenEstimator instance."""
        return TokenEstimator()

    def test_damping_prevents_wild_swings(self, estimator):
        """Test that damping prevents wild swings in estimates."""
        # Record normal usage
        estimator.record_actual_usage(
            phase_id="phase_001",
            estimated_tokens=1000,
            actual_tokens=1100,
            model="claude-sonnet-4"
        )

        overhead_after_normal = estimator.PHASE_OVERHEAD

        # Record one extreme outlier
        estimator.record_actual_usage(
            phase_id="phase_002",
            estimated_tokens=1000,
            actual_tokens=10000,  # Extreme outlier
            model="claude-sonnet-4"
        )

        overhead_after_outlier = estimator.PHASE_OVERHEAD

        # Change should be damped, not extreme
        change = abs(overhead_after_outlier - overhead_after_normal)
        assert change < 500  # Should not jump by more than 500 tokens

    def test_damping_factor_applied(self, estimator):
        """Test that damping factor is applied to updates."""
        initial_overhead = estimator.PHASE_OVERHEAD

        # Record single underestimation
        estimator.record_actual_usage(
            phase_id="phase_001",
            estimated_tokens=1000,
            actual_tokens=1500,
            model="claude-sonnet-4"
        )

        # Change should be less than full error amount
        error = 500  # Difference between actual and estimated
        actual_change = estimator.PHASE_OVERHEAD - initial_overhead

        # With damping, change should be fraction of error
        assert actual_change < error
        assert actual_change > 0

    def test_gradual_convergence(self, estimator):
        """Test that estimates gradually converge to actual usage."""
        # Set initial overhead far from optimal
        estimator.PHASE_OVERHEAD = 200

        # Record consistent usage pattern
        for _ in range(10):
            estimator.record_actual_usage(
                phase_id="test_phase",
                estimated_tokens=1000,
                actual_tokens=1500,  # Consistently 500 over
                model="claude-sonnet-4"
            )

        # Should converge toward 500 overhead
        # (since we're consistently 500 tokens over base estimate)
        assert 400 <= estimator.PHASE_OVERHEAD <= 600


class TestConfidenceScoring:
    """Test confidence scoring and thresholds."""

    @pytest.fixture
    def estimator(self):
        """Create TokenEstimator instance."""
        return TokenEstimator()

    def test_initial_confidence_low(self, estimator):
        """Test that initial confidence is low with no data."""
        confidence = estimator.get_confidence()
        assert confidence < 0.5  # Low confidence initially

    def test_confidence_increases_with_data(self, estimator):
        """Test that confidence increases as more data is collected."""
        initial_confidence = estimator.get_confidence()

        # Record several accurate estimates
        for i in range(10):
            estimator.record_actual_usage(
                phase_id=f"phase_{i:03d}",
                estimated_tokens=1000,
                actual_tokens=1050,  # Within 5% accuracy
                model="claude-sonnet-4"
            )

        final_confidence = estimator.get_confidence()
        assert final_confidence > initial_confidence

    def test_confidence_high_with_accurate_estimates(self, estimator):
        """Test that confidence is high when estimates are consistently accurate."""
        # Record many accurate estimates
        for i in range(20):
            estimator.record_actual_usage(
                phase_id=f"phase_{i:03d}",
                estimated_tokens=1000,
                actual_tokens=1020,  # Within 2% accuracy
                model="claude-sonnet-4"
            )

        confidence = estimator.get_confidence()
        assert confidence > 0.8  # High confidence

    def test_confidence_low_with_inaccurate_estimates(self, estimator):
        """Test that confidence is low when estimates are inaccurate."""
        # Record inaccurate estimates
        for i in range(20):
            estimator.record_actual_usage(
                phase_id=f"phase_{i:03d}",
                estimated_tokens=1000,
                actual_tokens=2000 if i % 2 == 0 else 500,  # Wildly varying
                model="claude-sonnet-4"
            )

        confidence = estimator.get_confidence()
        assert confidence < 0.5  # Low confidence due to variance

    def test_confidence_per_model(self, estimator):
        """Test that confidence can be tracked per model."""
        # Record accurate estimates for one model
        for i in range(10):
            estimator.record_actual_usage(
                phase_id=f"phase_{i:03d}",
                estimated_tokens=1000,
                actual_tokens=1020,
                model="claude-sonnet-4"
            )

        # Record inaccurate estimates for another model
        for i in range(10):
            estimator.record_actual_usage(
                phase_id=f"phase_{i:03d}",
                estimated_tokens=1000,
                actual_tokens=2000,
                model="gpt-4"
            )

        # Confidence should differ by model
        confidence_sonnet = estimator.get_confidence(model="claude-sonnet-4")
        confidence_gpt = estimator.get_confidence(model="gpt-4")

        assert confidence_sonnet > confidence_gpt


class TestCalibrationLifecycle:
    """Test calibration lifecycle and persistence."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for calibration data."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_calibration_data_persists(self, temp_dir):
        """Test that calibration data persists across instances."""
        calibration_file = temp_dir / "calibration.json"

        # Create estimator and record data
        estimator1 = TokenEstimator(calibration_file=calibration_file)
        for i in range(5):
            estimator1.record_actual_usage(
                phase_id=f"phase_{i:03d}",
                estimated_tokens=1000,
                actual_tokens=1100,
                model="claude-sonnet-4"
            )
        overhead1 = estimator1.PHASE_OVERHEAD

        # Create new estimator instance
        estimator2 = TokenEstimator(calibration_file=calibration_file)

        # Should load previous calibration
        assert estimator2.PHASE_OVERHEAD == overhead1

    def test_calibration_reset(self, temp_dir):
        """Test that calibration can be reset."""
        calibration_file = temp_dir / "calibration.json"

        estimator = TokenEstimator(calibration_file=calibration_file)

        # Record data
        for i in range(5):
            estimator.record_actual_usage(
                phase_id=f"phase_{i:03d}",
                estimated_tokens=1000,
                actual_tokens=1500,
                model="claude-sonnet-4"
            )

        overhead_before = estimator.PHASE_OVERHEAD

        # Reset calibration
        estimator.reset_calibration()

        # Should return to default
        assert estimator.PHASE_OVERHEAD == 500  # Default value
        assert estimator.PHASE_OVERHEAD != overhead_before

    def test_calibration_export_import(self, temp_dir):
        """Test exporting and importing calibration data."""
        export_file = temp_dir / "export.json"

        # Create and calibrate estimator
        estimator1 = TokenEstimator()
        for i in range(5):
            estimator1.record_actual_usage(
                phase_id=f"phase_{i:03d}",
                estimated_tokens=1000,
                actual_tokens=1200,
                model="claude-sonnet-4"
            )

        # Export calibration
        estimator1.export_calibration(export_file)

        # Import into new estimator
        estimator2 = TokenEstimator()
        estimator2.import_calibration(export_file)

        # Should match original
        assert estimator2.PHASE_OVERHEAD == estimator1.PHASE_OVERHEAD


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def estimator(self):
        """Create TokenEstimator instance."""
        return TokenEstimator()

    def test_zero_token_usage(self, estimator):
        """Test handling of zero token usage."""
        # Should not crash or cause division by zero
        estimator.record_actual_usage(
            phase_id="phase_001",
            estimated_tokens=1000,
            actual_tokens=0,
            model="claude-sonnet-4"
        )

        # Should still have valid overhead
        assert estimator.PHASE_OVERHEAD > 0

    def test_negative_token_values_rejected(self, estimator):
        """Test that negative token values are rejected."""
        with pytest.raises(ValueError):
            estimator.record_actual_usage(
                phase_id="phase_001",
                estimated_tokens=-100,
                actual_tokens=1000,
                model="claude-sonnet-4"
            )

        with pytest.raises(ValueError):
            estimator.record_actual_usage(
                phase_id="phase_001",
                estimated_tokens=1000,
                actual_tokens=-100,
                model="claude-sonnet-4"
            )

    def test_extreme_token_values(self, estimator):
        """Test handling of extreme token values."""
        # Very large values
        estimator.record_actual_usage(
            phase_id="phase_001",
            estimated_tokens=1000000,
            actual_tokens=1100000,
            model="claude-sonnet-4"
        )

        # Should still produce reasonable overhead
        assert 200 <= estimator.PHASE_OVERHEAD <= 2000

    def test_missing_model_parameter(self, estimator):
        """Test handling when model parameter is not provided."""
        # Should use default model or handle gracefully
        estimator.record_actual_usage(
            phase_id="phase_001",
            estimated_tokens=1000,
            actual_tokens=1100
        )

        # Should not crash
        assert estimator.PHASE_OVERHEAD > 0

    def test_concurrent_updates(self, estimator):
        """Test thread safety of concurrent calibration updates."""
        import threading

        def record_usage():
            for i in range(10):
                estimator.record_actual_usage(
                    phase_id=f"phase_{i:03d}",
                    estimated_tokens=1000,
                    actual_tokens=1100,
                    model="claude-sonnet-4"
                )

        # Run multiple threads
        threads = [threading.Thread(target=record_usage) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should complete without errors
        assert estimator.PHASE_OVERHEAD > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
