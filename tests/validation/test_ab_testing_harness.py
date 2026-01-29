"""Tests for A-B testing harness (IMP-ARCH-005)."""

from src.autopack.validation.ab_testing_harness import ABTestingHarness, ABTestResult


class TestABTestingHarness:
    """Test suite for ABTestingHarness."""

    def test_run_test_basic(self):
        """Test basic A-B test execution."""
        harness = ABTestingHarness()

        # Simulated control: baseline metrics with some variance
        import random

        random.seed(42)

        def control():
            base_tokens = 1000.0
            base_duration = 10.0
            return {
                "token_usage": base_tokens + random.uniform(-50, 50),
                "duration": base_duration + random.uniform(-0.5, 0.5),
                "success_rate": 0.90 + random.uniform(-0.02, 0.02),
            }

        # Simulated treatment: improved metrics with variance
        def treatment():
            base_tokens = 800.0
            base_duration = 8.0
            return {
                "token_usage": base_tokens + random.uniform(-40, 40),
                "duration": base_duration + random.uniform(-0.4, 0.4),
                "success_rate": 0.95 + random.uniform(-0.01, 0.01),
            }

        result = harness.run_test(
            control=control,
            treatment=treatment,
            iterations=10,
            metrics=["token_usage", "duration", "success_rate"],
        )

        assert isinstance(result, ABTestResult)
        assert result.test_id is not None
        assert "token_usage" in result.p_values
        assert "duration" in result.p_values
        assert result.validated is True  # Should validate: significant improvement

    def test_run_test_no_improvement(self):
        """Test A-B test when treatment has no improvement."""
        harness = ABTestingHarness()

        # Control and treatment are identical
        def control():
            return {"token_usage": 1000.0}

        def treatment():
            return {"token_usage": 1000.0}

        result = harness.run_test(control=control, treatment=treatment, iterations=10)

        # Should not validate: no significant difference
        assert result.validated is False

    def test_run_test_regression_detection(self):
        """Test that regression triggers validation failure."""
        harness = ABTestingHarness(regression_threshold=0.05)

        # Control: baseline
        def control():
            return {"token_usage": 1000.0, "error_rate": 0.05}

        # Treatment: worse performance (>5% regression)
        def treatment():
            return {"token_usage": 1200.0, "error_rate": 0.12}

        result = harness.run_test(control=control, treatment=treatment, iterations=10)

        # Should not validate: regression detected
        assert result.validated is False

    def test_validate_improvement_with_pre_collected_data(self):
        """Test validation using pre-collected run data."""
        harness = ABTestingHarness()

        # Pre-collected control runs
        control_runs = [
            {"token_usage": 1000.0, "duration": 10.0},
            {"token_usage": 1100.0, "duration": 11.0},
            {"token_usage": 950.0, "duration": 9.5},
            {"token_usage": 1050.0, "duration": 10.5},
            {"token_usage": 1000.0, "duration": 10.0},
        ]

        # Pre-collected treatment runs (20% improvement)
        treatment_runs = [
            {"token_usage": 800.0, "duration": 8.0},
            {"token_usage": 880.0, "duration": 8.8},
            {"token_usage": 760.0, "duration": 7.6},
            {"token_usage": 840.0, "duration": 8.4},
            {"token_usage": 800.0, "duration": 8.0},
        ]

        result = harness.validate_improvement(
            control_runs=control_runs,
            treatment_runs=treatment_runs,
            metrics=["token_usage", "duration"],
        )

        assert result.validated is True
        assert result.p_value < 0.05  # Statistically significant
        assert abs(result.effect_size) > 0.2  # Meaningful effect size
