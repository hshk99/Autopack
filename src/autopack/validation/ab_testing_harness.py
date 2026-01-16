"""A-B testing harness for validating autonomous improvements (IMP-ARCH-005)."""

import statistics
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from scipy import stats


class ABTestResult:
    """Result of an A-B test with statistical validation."""

    def __init__(
        self,
        test_id: str,
        control_metrics: Dict[str, List[float]],
        treatment_metrics: Dict[str, List[float]],
        p_values: Dict[str, float],
        effect_sizes: Dict[str, float],
        confidence_intervals: Dict[str, tuple[float, float]],
        validated: bool,
        improvement_task_id: Optional[str] = None,
    ):
        self.test_id = test_id
        self.control_metrics = control_metrics
        self.treatment_metrics = treatment_metrics
        self.p_values = p_values
        self.effect_sizes = effect_sizes
        self.confidence_intervals = confidence_intervals
        self.validated = validated
        self.improvement_task_id = improvement_task_id
        self.created_at = datetime.now(timezone.utc)

    @property
    def p_value(self) -> float:
        """Overall p-value (minimum across all metrics)."""
        return min(self.p_values.values()) if self.p_values else 1.0

    @property
    def effect_size(self) -> float:
        """Overall effect size (average across all metrics)."""
        return statistics.mean(self.effect_sizes.values()) if self.effect_sizes else 0.0


class ABTestingHarness:
    """
    Statistical A-B testing harness for autonomous improvement validation.

    Validates improvements using:
    - Paired t-test for statistical significance (p < 0.05)
    - Cohen's d for effect size measurement
    - Confidence intervals for precision
    - Regression detection (>5% degradation triggers rejection)
    """

    def __init__(
        self,
        significance_level: float = 0.05,
        min_effect_size: float = 0.2,  # Small effect size
        regression_threshold: float = 0.05,  # 5% degradation
    ):
        self.significance_level = significance_level
        self.min_effect_size = min_effect_size
        self.regression_threshold = regression_threshold

    def run_test(
        self,
        control: Callable[[], Dict[str, float]],
        treatment: Callable[[], Dict[str, float]],
        iterations: int = 10,
        metrics: Optional[List[str]] = None,
        improvement_task_id: Optional[str] = None,
    ) -> ABTestResult:
        """
        Run A-B test comparing control vs treatment.

        Args:
            control: Function that runs baseline version and returns metrics dict
            treatment: Function that runs improved version and returns metrics dict
            iterations: Number of test iterations to run
            metrics: List of metric names to track (if None, uses all from first run)
            improvement_task_id: Optional task ID for tracking

        Returns:
            ABTestResult with statistical validation
        """
        test_id = str(uuid.uuid4())

        # Collect samples
        control_samples: Dict[str, List[float]] = {}
        treatment_samples: Dict[str, List[float]] = {}

        for i in range(iterations):
            # Run control
            control_result = control()
            for metric, value in control_result.items():
                if metrics is None or metric in metrics:
                    control_samples.setdefault(metric, []).append(value)

            # Run treatment
            treatment_result = treatment()
            for metric, value in treatment_result.items():
                if metrics is None or metric in metrics:
                    treatment_samples.setdefault(metric, []).append(value)

        # Compute statistics
        p_values = {}
        effect_sizes = {}
        confidence_intervals = {}

        for metric in control_samples.keys():
            if metric not in treatment_samples:
                continue

            control_vals = control_samples[metric]
            treatment_vals = treatment_samples[metric]

            # Paired t-test (assumes same ordering for control/treatment pairs)
            t_stat, p_val = stats.ttest_rel(control_vals, treatment_vals)
            p_values[metric] = p_val

            # Cohen's d (effect size)
            d = self._cohens_d(control_vals, treatment_vals)
            effect_sizes[metric] = d

            # 95% confidence interval for mean difference
            ci = self._confidence_interval(control_vals, treatment_vals)
            confidence_intervals[metric] = ci

        # Validate: significant AND meaningful effect size AND no regression
        validated = self._validate_results(
            control_samples, treatment_samples, p_values, effect_sizes
        )

        return ABTestResult(
            test_id=test_id,
            control_metrics=control_samples,
            treatment_metrics=treatment_samples,
            p_values=p_values,
            effect_sizes=effect_sizes,
            confidence_intervals=confidence_intervals,
            validated=validated,
            improvement_task_id=improvement_task_id,
        )

    def _cohens_d(self, control: List[float], treatment: List[float]) -> float:
        """
        Calculate Cohen's d effect size.

        d = (M_treatment - M_control) / pooled_std
        Interpretation:
        - |d| < 0.2: negligible
        - |d| < 0.5: small
        - |d| < 0.8: medium
        - |d| >= 0.8: large
        """
        mean_control = statistics.mean(control)
        mean_treatment = statistics.mean(treatment)

        std_control = statistics.stdev(control) if len(control) > 1 else 0.0
        std_treatment = statistics.stdev(treatment) if len(treatment) > 1 else 0.0

        # Pooled standard deviation
        n1, n2 = len(control), len(treatment)
        pooled_std = (
            ((n1 - 1) * std_control**2 + (n2 - 1) * std_treatment**2) / (n1 + n2 - 2)
        ) ** 0.5

        if pooled_std == 0:
            return 0.0

        return (mean_treatment - mean_control) / pooled_std

    def _confidence_interval(
        self, control: List[float], treatment: List[float], confidence: float = 0.95
    ) -> tuple[float, float]:
        """Calculate confidence interval for mean difference."""
        differences = [t - c for c, t in zip(control, treatment)]
        mean_diff = statistics.mean(differences)
        std_diff = statistics.stdev(differences) if len(differences) > 1 else 0.0

        # t-critical value for 95% CI
        df = len(differences) - 1
        t_crit = stats.t.ppf((1 + confidence) / 2, df)

        margin = t_crit * std_diff / (len(differences) ** 0.5) if len(differences) > 0 else 0

        return (mean_diff - margin, mean_diff + margin)

    def _validate_results(
        self,
        control_samples: Dict[str, List[float]],
        treatment_samples: Dict[str, List[float]],
        p_values: Dict[str, float],
        effect_sizes: Dict[str, float],
    ) -> bool:
        """
        Validate A-B test results.

        Requirements:
        1. p-value < significance_level for at least one metric
        2. |effect_size| > min_effect_size for validated metrics
        3. No regression: treatment must not be >5% worse on any critical metric
        """
        # Check 1: Statistical significance
        has_significant = any(p < self.significance_level for p in p_values.values())
        if not has_significant:
            return False

        # Check 2: Meaningful effect size
        significant_metrics = [m for m, p in p_values.items() if p < self.significance_level]
        has_meaningful_effect = any(
            abs(effect_sizes[m]) > self.min_effect_size for m in significant_metrics
        )
        if not has_meaningful_effect:
            return False

        # Check 3: No regression on cost/error metrics
        # For cost metrics (token_usage, duration): treatment should be ≤ control
        # For quality metrics (success_rate): treatment should be ≥ control
        regression_detected = False

        for metric in control_samples.keys():
            if metric not in treatment_samples:
                continue

            control_mean = statistics.mean(control_samples[metric])
            treatment_mean = statistics.mean(treatment_samples[metric])

            # Cost metrics: lower is better
            if metric in ["token_usage", "duration", "error_rate", "retry_count"]:
                pct_change = (
                    (treatment_mean - control_mean) / control_mean if control_mean > 0 else 0
                )
                if pct_change > self.regression_threshold:
                    regression_detected = True
                    break

            # Quality metrics: higher is better
            elif metric in ["success_rate", "quality_score"]:
                pct_change = (
                    (control_mean - treatment_mean) / control_mean if control_mean > 0 else 0
                )
                if pct_change > self.regression_threshold:
                    regression_detected = True
                    break

        return not regression_detected

    def validate_improvement(
        self,
        control_runs: List[Dict[str, float]],
        treatment_runs: List[Dict[str, float]],
        metrics: Optional[List[str]] = None,
    ) -> ABTestResult:
        """
        Validate improvement using pre-collected run data.

        Args:
            control_runs: List of metric dicts from control runs
            treatment_runs: List of metric dicts from treatment runs
            metrics: Optional list of metrics to validate

        Returns:
            ABTestResult with validation outcome
        """
        test_id = str(uuid.uuid4())

        # Convert runs to samples
        control_samples: Dict[str, List[float]] = {}
        treatment_samples: Dict[str, List[float]] = {}

        for run in control_runs:
            for metric, value in run.items():
                if metrics is None or metric in metrics:
                    control_samples.setdefault(metric, []).append(value)

        for run in treatment_runs:
            for metric, value in run.items():
                if metrics is None or metric in metrics:
                    treatment_samples.setdefault(metric, []).append(value)

        # Compute statistics
        p_values = {}
        effect_sizes = {}
        confidence_intervals = {}

        for metric in control_samples.keys():
            if metric not in treatment_samples:
                continue

            control_vals = control_samples[metric]
            treatment_vals = treatment_samples[metric]

            # Ensure same length for paired t-test
            min_len = min(len(control_vals), len(treatment_vals))
            control_vals = control_vals[:min_len]
            treatment_vals = treatment_vals[:min_len]

            # Paired t-test
            if len(control_vals) > 1:
                t_stat, p_val = stats.ttest_rel(control_vals, treatment_vals)
                p_values[metric] = p_val

                # Cohen's d
                d = self._cohens_d(control_vals, treatment_vals)
                effect_sizes[metric] = d

                # Confidence interval
                ci = self._confidence_interval(control_vals, treatment_vals)
                confidence_intervals[metric] = ci

        # Validate
        validated = self._validate_results(
            control_samples, treatment_samples, p_values, effect_sizes
        )

        return ABTestResult(
            test_id=test_id,
            control_metrics=control_samples,
            treatment_metrics=treatment_samples,
            p_values=p_values,
            effect_sizes=effect_sizes,
            confidence_intervals=confidence_intervals,
            validated=validated,
        )
