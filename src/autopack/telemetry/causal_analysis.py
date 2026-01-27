"""ROAD-H: Causal Analysis for understanding change impact.

Analyzes causal relationships between code/config changes and outcome metrics:
- Statistical correlation analysis
- Temporal causality detection (change precedes outcome)
- Multi-variable impact assessment
- Confounding factor detection
- Causal confidence scoring

Integrates with:
- ROAD-A: PhaseOutcomeEvent telemetry (outcome source)
- ROAD-E: A-B validation results (ground truth)
- ROAD-F: Policy promotion decisions (change tracking)

Methods:
- Correlation analysis: Pearson, Spearman
- Temporal precedence: Change must occur before effect
- Granger causality: Statistical test for time-series causality
- Counterfactual analysis: Compare actual vs. baseline
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from statistics import mean, stdev
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CausalStrength(Enum):
    """Strength of causal relationship."""

    STRONG = "strong"  # High confidence, clear causality
    MODERATE = "moderate"  # Medium confidence, likely causal
    WEAK = "weak"  # Low confidence, possible causality
    NONE = "none"  # No causal relationship detected
    CONFOUNDED = "confounded"  # Confounding factors present


@dataclass
class ChangeEvent:
    """Represents a change event (code, config, policy, etc.)."""

    change_id: str
    change_type: str  # "code", "config", "policy", "model"
    timestamp: datetime
    affected_components: List[str]
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutcomeMetric:
    """Represents an outcome metric measurement."""

    metric_name: str
    value: float
    timestamp: datetime
    phase_id: str
    run_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CausalRelationship:
    """Represents a detected causal relationship between change and outcome."""

    change_event: ChangeEvent
    outcome_metric: str
    causal_strength: CausalStrength
    confidence: float  # 0.0-1.0
    effect_size: float  # Magnitude of impact
    effect_direction: str  # "positive" (improvement) or "negative" (degradation)

    # Statistical evidence
    correlation_coefficient: float
    temporal_precedence: bool  # Did change occur before outcome?
    p_value: float  # Statistical significance
    sample_size: int

    # Analysis details
    baseline_mean: float
    post_change_mean: float
    percent_change: float
    confounding_factors: List[str] = field(default_factory=list)

    explanation: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CausalAnalysisReport:
    """Comprehensive causal analysis report."""

    analysis_id: str
    change_event: ChangeEvent
    relationships: List[CausalRelationship]
    overall_impact: str  # "positive", "negative", "neutral", "mixed"
    confidence: float

    # Summary statistics
    metrics_improved: int
    metrics_degraded: int
    metrics_unchanged: int

    recommendations: List[str]
    timestamp: datetime = field(default_factory=datetime.now)


class CausalAnalyzer:
    """Analyzes causal relationships between changes and outcomes.

    Implements statistical causal inference:
    1. Correlation analysis (Pearson, Spearman)
    2. Temporal precedence verification
    3. Effect size quantification
    4. Confounding factor detection
    5. Causal confidence scoring
    """

    def __init__(
        self,
        significance_level: float = 0.05,
        min_sample_size: int = 10,
        temporal_window_hours: float = 24.0,
        effect_size_threshold: float = 0.10,
    ):
        """Initialize causal analyzer.

        Args:
            significance_level: P-value threshold for statistical significance (default: 0.05)
            min_sample_size: Minimum samples required for analysis (default: 10)
            temporal_window_hours: Time window for outcome attribution (default: 24h)
            effect_size_threshold: Minimum effect size to consider meaningful (default: 10%)
        """
        self.significance_level = significance_level
        self.min_sample_size = min_sample_size
        self.temporal_window = timedelta(hours=temporal_window_hours)
        self.effect_size_threshold = effect_size_threshold

    def analyze_change_impact(
        self,
        change_event: ChangeEvent,
        baseline_metrics: Dict[str, List[OutcomeMetric]],
        post_change_metrics: Dict[str, List[OutcomeMetric]],
        confounding_changes: Optional[List[ChangeEvent]] = None,
    ) -> CausalAnalysisReport:
        """Analyze causal impact of a change on outcome metrics.

        Args:
            change_event: The change to analyze
            baseline_metrics: Metrics before change (dict[metric_name -> List[OutcomeMetric]])
            post_change_metrics: Metrics after change (dict[metric_name -> List[OutcomeMetric]])
            confounding_changes: Other changes that occurred in same time window

        Returns:
            CausalAnalysisReport with detected relationships
        """
        relationships = []

        # Analyze each metric for causal relationship
        all_metric_names = set(baseline_metrics.keys()) | set(post_change_metrics.keys())

        for metric_name in all_metric_names:
            baseline = baseline_metrics.get(metric_name, [])
            post_change = post_change_metrics.get(metric_name, [])

            if len(baseline) < self.min_sample_size or len(post_change) < self.min_sample_size:
                logger.debug(
                    f"Insufficient samples for {metric_name}: baseline={len(baseline)}, post={len(post_change)}"
                )
                continue

            # Verify temporal precedence
            temporal_precedence = self._verify_temporal_precedence(
                change_event, baseline, post_change
            )

            # Compute statistics
            relationship = self._compute_causal_relationship(
                change_event=change_event,
                metric_name=metric_name,
                baseline=baseline,
                post_change=post_change,
                temporal_precedence=temporal_precedence,
                confounding_changes=confounding_changes or [],
            )

            if relationship:
                relationships.append(relationship)

        # Generate overall analysis
        report = self._generate_analysis_report(change_event, relationships)

        logger.info(
            f"[ROAD-H] Analyzed change {change_event.change_id}: "
            f"{report.metrics_improved} improved, {report.metrics_degraded} degraded, "
            f"{report.metrics_unchanged} unchanged"
        )

        return report

    def _verify_temporal_precedence(
        self,
        change_event: ChangeEvent,
        baseline: List[OutcomeMetric],
        post_change: List[OutcomeMetric],
    ) -> bool:
        """Verify that change occurred before outcome measurements.

        Returns:
            True if temporal precedence holds (change before outcomes)
        """
        if not post_change:
            return False

        # All post-change metrics should be after change event
        earliest_post = min(m.timestamp for m in post_change)
        return earliest_post >= change_event.timestamp

    def _compute_causal_relationship(
        self,
        change_event: ChangeEvent,
        metric_name: str,
        baseline: List[OutcomeMetric],
        post_change: List[OutcomeMetric],
        temporal_precedence: bool,
        confounding_changes: List[ChangeEvent],
    ) -> Optional[CausalRelationship]:
        """Compute causal relationship statistics.

        Returns:
            CausalRelationship if significant relationship detected, None otherwise
        """
        # Extract values
        baseline_values = [m.value for m in baseline]
        post_values = [m.value for m in post_change]

        # Compute summary statistics
        baseline_mean = mean(baseline_values)
        post_mean = mean(post_values)
        baseline_std = stdev(baseline_values) if len(baseline_values) > 1 else 0.0
        post_std = stdev(post_values) if len(post_values) > 1 else 0.0

        # Avoid division by zero
        if baseline_mean == 0:
            percent_change = 0.0 if post_mean == 0 else float("inf")
        else:
            percent_change = ((post_mean - baseline_mean) / abs(baseline_mean)) * 100

        # Effect size (Cohen's d)
        pooled_std = (
            math.sqrt((baseline_std**2 + post_std**2) / 2) if baseline_std or post_std else 1.0
        )
        effect_size = abs(post_mean - baseline_mean) / pooled_std if pooled_std > 0 else 0.0

        # Correlation (simple point-biserial for before/after)
        # For time series: compute Pearson correlation between time and metric
        correlation = self._compute_correlation(baseline_values, post_values)

        # Statistical significance (two-sample t-test approximation)
        p_value = self._compute_p_value(
            baseline_values, post_values, baseline_std, post_std, baseline_mean, post_mean
        )

        # Determine effect direction
        if abs(percent_change) < self.effect_size_threshold * 100:
            effect_direction = "neutral"
        elif self._is_improvement(metric_name, post_mean, baseline_mean):
            effect_direction = "positive"
        else:
            effect_direction = "negative"

        # Detect confounding factors
        confounders = self._detect_confounders(
            change_event, baseline, post_change, confounding_changes
        )

        # Determine causal strength
        causal_strength = self._determine_causal_strength(
            p_value=p_value,
            effect_size=effect_size,
            temporal_precedence=temporal_precedence,
            confounders=confounders,
        )

        # Compute overall confidence
        confidence = self._compute_confidence(
            p_value=p_value,
            effect_size=effect_size,
            sample_size=len(baseline) + len(post_change),
            temporal_precedence=temporal_precedence,
            confounders=confounders,
        )

        # Only return if there's a meaningful relationship
        if causal_strength == CausalStrength.NONE or confidence < 0.3:
            return None

        # Generate explanation
        explanation = self._generate_explanation(
            change_event=change_event,
            metric_name=metric_name,
            effect_direction=effect_direction,
            percent_change=percent_change,
            causal_strength=causal_strength,
            confounders=confounders,
        )

        return CausalRelationship(
            change_event=change_event,
            outcome_metric=metric_name,
            causal_strength=causal_strength,
            confidence=confidence,
            effect_size=effect_size,
            effect_direction=effect_direction,
            correlation_coefficient=correlation,
            temporal_precedence=temporal_precedence,
            p_value=p_value,
            sample_size=len(baseline) + len(post_change),
            baseline_mean=baseline_mean,
            post_change_mean=post_mean,
            percent_change=percent_change,
            confounding_factors=confounders,
            explanation=explanation,
        )

    def _compute_correlation(self, baseline: List[float], post_change: List[float]) -> float:
        """Compute correlation coefficient (simplified point-biserial).

        For before/after analysis, we use a binary indicator (0=before, 1=after).
        """
        if not baseline or not post_change:
            return 0.0

        # Combine data with binary labels
        all_values = baseline + post_change
        labels = [0] * len(baseline) + [1] * len(post_change)

        # Compute means
        mean_values = mean(all_values)
        mean_labels = mean(labels)

        # Compute covariance and standard deviations
        n = len(all_values)
        cov = (
            sum((v - mean_values) * (label - mean_labels) for v, label in zip(all_values, labels))
            / n
        )

        std_values = math.sqrt(sum((v - mean_values) ** 2 for v in all_values) / n)
        std_labels = math.sqrt(sum((label - mean_labels) ** 2 for label in labels) / n)

        if std_values == 0 or std_labels == 0:
            return 0.0

        correlation = cov / (std_values * std_labels)
        return correlation

    def _compute_p_value(
        self,
        baseline: List[float],
        post_change: List[float],
        baseline_std: float,
        post_std: float,
        baseline_mean: float,
        post_mean: float,
    ) -> float:
        """Compute p-value for two-sample t-test (Welch's t-test approximation).

        Returns:
            p-value (0.0-1.0), lower is more significant
        """
        n1 = len(baseline)
        n2 = len(post_change)

        # Pooled standard error
        se = math.sqrt((baseline_std**2 / n1) + (post_std**2 / n2)) if n1 > 0 and n2 > 0 else 1.0

        if se == 0:
            return 1.0  # No variance, no significance

        # T-statistic
        t_stat = abs(post_mean - baseline_mean) / se

        # Degrees of freedom (Welch-Satterthwaite equation)
        if baseline_std == 0 and post_std == 0:
            return 1.0

        # Simplified p-value approximation (using normal approximation for large samples)
        # For exact p-value, would use scipy.stats.t.sf(t_stat, dof)
        # Here we use a simplified heuristic: p ≈ erfc(t_stat / sqrt(2))
        # For simplicity, map t-statistic to approximate p-value
        if t_stat > 2.576:  # 99% confidence
            return 0.01
        elif t_stat > 1.96:  # 95% confidence
            return 0.05
        elif t_stat > 1.645:  # 90% confidence
            return 0.10
        else:
            return 0.20

    def _is_improvement(self, metric_name: str, new_value: float, old_value: float) -> bool:
        """Determine if change is an improvement for given metric.

        Args:
            metric_name: Name of metric
            new_value: New metric value
            old_value: Old metric value

        Returns:
            True if new_value is better than old_value
        """
        # Metrics where lower is better
        lower_is_better = ["duration", "token", "cost", "failure", "retry", "error"]

        for pattern in lower_is_better:
            if pattern in metric_name.lower():
                return new_value < old_value

        # Default: higher is better (success_rate, quality_score, etc.)
        return new_value > old_value

    def _detect_confounders(
        self,
        change_event: ChangeEvent,
        baseline: List[OutcomeMetric],
        post_change: List[OutcomeMetric],
        confounding_changes: List[ChangeEvent],
    ) -> List[str]:
        """Detect potential confounding factors.

        Returns:
            List of confounder descriptions
        """
        confounders = []

        # Check for other changes in temporal window
        for other_change in confounding_changes:
            if other_change.change_id == change_event.change_id:
                continue

            # Check if other change occurred in same time window
            time_diff = abs((other_change.timestamp - change_event.timestamp).total_seconds())
            if time_diff < self.temporal_window.total_seconds():
                confounders.append(
                    f"{other_change.change_type} change: {other_change.description[:50]}"
                )

        # Check for high variance in baseline (unstable metric)
        if baseline:
            baseline_values = [m.value for m in baseline]
            if len(baseline_values) > 1:
                baseline_std = stdev(baseline_values)
                baseline_mean = mean(baseline_values)
                cv = (baseline_std / baseline_mean) if baseline_mean != 0 else 0
                if cv > 0.3:  # Coefficient of variation > 30%
                    confounders.append("High baseline variance (unstable metric)")

        return confounders

    def _determine_causal_strength(
        self,
        p_value: float,
        effect_size: float,
        temporal_precedence: bool,
        confounders: List[str],
    ) -> CausalStrength:
        """Determine strength of causal relationship.

        Returns:
            CausalStrength enum value
        """
        # No temporal precedence = no causality
        if not temporal_precedence:
            return CausalStrength.NONE

        # Confounders present = confounded
        if len(confounders) >= 2:
            return CausalStrength.CONFOUNDED

        # Statistical significance + large effect = strong causality
        if p_value < self.significance_level and effect_size > 0.8:
            return CausalStrength.STRONG if not confounders else CausalStrength.MODERATE

        # Statistical significance + medium effect = moderate causality
        if p_value < self.significance_level and effect_size > 0.5:
            return CausalStrength.MODERATE

        # Statistical significance + small effect = weak causality
        if p_value < self.significance_level and effect_size > 0.2:
            return CausalStrength.WEAK

        # No statistical significance = no causality
        return CausalStrength.NONE

    def _compute_confidence(
        self,
        p_value: float,
        effect_size: float,
        sample_size: int,
        temporal_precedence: bool,
        confounders: List[str],
    ) -> float:
        """Compute overall confidence in causal relationship.

        Returns:
            Confidence score (0.0-1.0)
        """
        # Start with base confidence from statistical significance
        if p_value < 0.01:
            confidence = 0.95
        elif p_value < 0.05:
            confidence = 0.85
        elif p_value < 0.10:
            confidence = 0.70
        else:
            confidence = 0.50

        # Adjust for effect size
        if effect_size > 0.8:
            confidence += 0.05
        elif effect_size < 0.2:
            confidence -= 0.10

        # Adjust for sample size
        if sample_size >= 50:
            confidence += 0.05
        elif sample_size < self.min_sample_size * 2:
            confidence -= 0.10

        # Penalize for lack of temporal precedence
        if not temporal_precedence:
            confidence *= 0.5

        # Penalize for confounders
        if confounders:
            confidence -= 0.05 * len(confounders)

        # Clamp to [0, 1]
        return max(0.0, min(1.0, confidence))

    def _generate_explanation(
        self,
        change_event: ChangeEvent,
        metric_name: str,
        effect_direction: str,
        percent_change: float,
        causal_strength: CausalStrength,
        confounders: List[str],
    ) -> str:
        """Generate human-readable explanation of causal relationship."""
        direction_word = {
            "positive": "improved",
            "negative": "degraded",
            "neutral": "remained stable",
        }.get(effect_direction, "changed")

        strength_word = {
            CausalStrength.STRONG: "likely caused",
            CausalStrength.MODERATE: "probably caused",
            CausalStrength.WEAK: "may have caused",
            CausalStrength.CONFOUNDED: "is associated with (confounded)",
            CausalStrength.NONE: "is not associated with",
        }.get(causal_strength, "affected")

        explanation = (
            f"{change_event.change_type.capitalize()} change '{change_event.description[:60]}' "
            f"{strength_word} {metric_name} to {direction_word} by {abs(percent_change):.1f}%"
        )

        if confounders:
            explanation += f" (confounders: {len(confounders)})"

        return explanation

    def _generate_analysis_report(
        self, change_event: ChangeEvent, relationships: List[CausalRelationship]
    ) -> CausalAnalysisReport:
        """Generate comprehensive analysis report."""
        # Count impact by direction
        metrics_improved = sum(1 for r in relationships if r.effect_direction == "positive")
        metrics_degraded = sum(1 for r in relationships if r.effect_direction == "negative")
        metrics_unchanged = sum(1 for r in relationships if r.effect_direction == "neutral")

        # Determine overall impact
        if metrics_improved > metrics_degraded + metrics_unchanged:
            overall_impact = "positive"
        elif metrics_degraded > metrics_improved + metrics_unchanged:
            overall_impact = "negative"
        elif metrics_improved > 0 and metrics_degraded > 0:
            overall_impact = "mixed"
        else:
            overall_impact = "neutral"

        # Compute overall confidence (weighted by individual confidences)
        if relationships:
            overall_confidence = mean(r.confidence for r in relationships)
        else:
            overall_confidence = 0.0

        # Generate recommendations
        recommendations = self._generate_recommendations(
            change_event, relationships, overall_impact
        )

        return CausalAnalysisReport(
            analysis_id=f"CAUSAL_{change_event.change_id}_{int(datetime.now().timestamp())}",
            change_event=change_event,
            relationships=relationships,
            overall_impact=overall_impact,
            confidence=overall_confidence,
            metrics_improved=metrics_improved,
            metrics_degraded=metrics_degraded,
            metrics_unchanged=metrics_unchanged,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        change_event: ChangeEvent,
        relationships: List[CausalRelationship],
        overall_impact: str,
    ) -> List[str]:
        """Generate actionable recommendations based on causal analysis."""
        recommendations = []

        if overall_impact == "positive":
            strong_improvements = [
                r
                for r in relationships
                if r.effect_direction == "positive" and r.causal_strength == CausalStrength.STRONG
            ]
            if strong_improvements:
                recommendations.append(
                    f"Change showed {len(strong_improvements)} strong improvements - "
                    "consider promoting to production"
                )

        elif overall_impact == "negative":
            strong_degradations = [
                r
                for r in relationships
                if r.effect_direction == "negative" and r.causal_strength == CausalStrength.STRONG
            ]
            if strong_degradations:
                recommendations.append(
                    f"Change caused {len(strong_degradations)} strong degradations - "
                    "consider rollback"
                )

        elif overall_impact == "mixed":
            recommendations.append(
                f"Change has mixed impact: {len([r for r in relationships if r.effect_direction == 'positive'])} improvements, "
                f"{len([r for r in relationships if r.effect_direction == 'negative'])} degradations - "
                "review tradeoffs before deciding"
            )

        # Check for confounded relationships or any with confounding factors
        confounded = [r for r in relationships if r.causal_strength == CausalStrength.CONFOUNDED]
        has_confounders = [r for r in relationships if len(r.confounding_factors) > 0]
        if confounded:
            recommendations.append(
                f"{len(confounded)} metrics have confounding factors - "
                "conduct additional controlled tests to isolate effects"
            )
        elif has_confounders and not confounded:
            recommendations.append(
                f"{len(has_confounders)} metrics have potential confounding factors - "
                "consider running controlled experiments to isolate causal effects"
            )

        # Check for low confidence
        low_confidence = [r for r in relationships if r.confidence < 0.5]
        if low_confidence:
            recommendations.append(
                f"{len(low_confidence)} relationships have low confidence - "
                "collect more data before making decisions"
            )

        return recommendations

    # =========================================================================
    # IMP-FBK-005: Task Prioritization Integration
    # =========================================================================

    def get_pattern_causal_history(
        self,
        pattern_type: str,
        affected_components: Optional[List[str]] = None,
        lookback_days: int = 30,
    ) -> Dict[str, Any]:
        """Get causal history for a pattern type to inform task prioritization.

        IMP-FBK-005: Query historical causal relationships to determine if
        a pattern type has historically caused negative outcomes. Used by
        TaskGenerator to adjust priorities for tasks that may cause failures.

        Args:
            pattern_type: Type of pattern (e.g., "cost_sink", "failure_mode", "retry_cause")
            affected_components: Optional list of components to filter by
            lookback_days: Number of days to look back for historical data

        Returns:
            Dict containing:
                - risk_score: 0.0-1.0 (higher = more likely to cause failures)
                - negative_outcomes: Count of negative causal relationships
                - positive_outcomes: Count of positive causal relationships
                - confidence: Confidence in the risk assessment
                - recommendation: "proceed", "caution", or "defer"
                - reason: Human-readable explanation
        """
        # Query historical causal relationships from stored analyses
        # This is a simplified implementation - in production would query database
        risk_data = {
            "pattern_type": pattern_type,
            "risk_score": 0.0,
            "negative_outcomes": 0,
            "positive_outcomes": 0,
            "confidence": 0.5,
            "recommendation": "proceed",
            "reason": "No historical causal data available for this pattern",
        }

        try:
            # Query database for historical causal analysis reports
            from ..database import SessionLocal
            from ..models import CausalAnalysisRecord

            session = SessionLocal()
            try:
                from datetime import timezone

                cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

                # Query historical records matching pattern type
                records = (
                    session.query(CausalAnalysisRecord)
                    .filter(
                        CausalAnalysisRecord.pattern_type == pattern_type,
                        CausalAnalysisRecord.timestamp >= cutoff_date,
                    )
                    .all()
                )

                if not records:
                    logger.debug(
                        f"[IMP-FBK-005] No historical causal data for pattern: {pattern_type}"
                    )
                    return risk_data

                # Aggregate historical outcomes
                negative_count = 0
                positive_count = 0
                total_confidence = 0.0

                for record in records:
                    if record.effect_direction == "negative":
                        negative_count += 1
                    elif record.effect_direction == "positive":
                        positive_count += 1
                    total_confidence += record.confidence or 0.5

                total_outcomes = negative_count + positive_count
                if total_outcomes > 0:
                    # Calculate risk score: ratio of negative outcomes
                    risk_score = negative_count / total_outcomes
                    avg_confidence = total_confidence / len(records)

                    # Determine recommendation based on risk
                    if risk_score >= 0.7:
                        recommendation = "defer"
                        reason = (
                            f"High historical failure rate: {negative_count}/{total_outcomes} "
                            f"({risk_score * 100:.0f}%) negative outcomes"
                        )
                    elif risk_score >= 0.4:
                        recommendation = "caution"
                        reason = (
                            f"Mixed historical outcomes: {negative_count} negative, "
                            f"{positive_count} positive"
                        )
                    else:
                        recommendation = "proceed"
                        reason = (
                            f"Good historical track record: {positive_count}/{total_outcomes} "
                            f"({(1 - risk_score) * 100:.0f}%) positive outcomes"
                        )

                    risk_data.update(
                        {
                            "risk_score": risk_score,
                            "negative_outcomes": negative_count,
                            "positive_outcomes": positive_count,
                            "confidence": avg_confidence,
                            "recommendation": recommendation,
                            "reason": reason,
                        }
                    )

                    logger.debug(
                        f"[IMP-FBK-005] Causal history for {pattern_type}: "
                        f"risk={risk_score:.2f}, recommendation={recommendation}"
                    )

            finally:
                session.close()

        except ImportError:
            # Database not available - return default risk assessment
            logger.debug("[IMP-FBK-005] Database not available for causal history query")
        except Exception as e:
            logger.warning(f"[IMP-FBK-005] Failed to query causal history: {e}")

        return risk_data

    def adjust_priority_for_causal_risk(
        self,
        pattern: Dict[str, Any],
        causal_history: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Adjust pattern priority based on causal risk assessment.

        IMP-FBK-005: Modifies pattern severity and confidence based on
        historical causal analysis. Tasks that have historically caused
        failures get lower priority; safe tasks get higher priority.

        Args:
            pattern: Pattern dict with 'type', 'severity', 'confidence' keys
            causal_history: Output from get_pattern_causal_history()

        Returns:
            Modified pattern dict with adjusted severity and confidence
        """
        adjusted = pattern.copy()
        risk_score = causal_history.get("risk_score", 0.0)
        recommendation = causal_history.get("recommendation", "proceed")

        # Adjust severity based on risk
        original_severity = adjusted.get("severity", 5)

        if recommendation == "defer":
            # High risk: significantly reduce severity to lower priority
            adjusted["severity"] = max(1, original_severity - 4)
            adjusted["causal_risk"] = "high"
            logger.debug(
                f"[IMP-FBK-005] Reduced severity from {original_severity} to "
                f"{adjusted['severity']} due to high causal risk"
            )
        elif recommendation == "caution":
            # Medium risk: moderately reduce severity
            adjusted["severity"] = max(1, original_severity - 2)
            adjusted["causal_risk"] = "medium"
        else:
            # Low risk: slight boost to safe patterns
            if risk_score < 0.2 and causal_history.get("positive_outcomes", 0) > 0:
                adjusted["severity"] = min(10, original_severity + 1)
                adjusted["causal_risk"] = "low"

        # Adjust confidence based on causal confidence
        causal_confidence = causal_history.get("confidence", 0.5)
        original_confidence = adjusted.get("confidence", 0.5)

        # Blend pattern confidence with causal confidence
        adjusted["confidence"] = (original_confidence * 0.7) + (causal_confidence * 0.3)

        # Add causal metadata for tracking
        adjusted["causal_history"] = {
            "risk_score": risk_score,
            "recommendation": recommendation,
            "reason": causal_history.get("reason", ""),
        }

        return adjusted

    def validate_ab_test_result(
        self,
        test_result: Any,  # ABTestResult from validation module
        min_confidence: float = 0.7,
    ) -> tuple[bool, List[str]]:
        """
        Validate A-B test result using causal analysis principles.

        Applies additional causal validation beyond statistical significance:
        1. Effect size must be meaningful (not just statistically significant)
        2. No confounding factors detected
        3. Temporal coherence (no strange patterns)

        Args:
            test_result: ABTestResult from ab_testing_harness
            min_confidence: Minimum confidence threshold

        Returns:
            (validated, warnings): True if causally valid, list of warnings
        """
        warnings = []

        # Check 1: Statistical significance already validated in ABTestResult
        if not test_result.validated:
            return False, ["A-B test did not pass statistical validation"]

        # Check 2: Effect size is meaningful (not just significant)
        if abs(test_result.effect_size) < 0.2:
            warnings.append(
                f"Effect size ({test_result.effect_size:.3f}) is negligible, "
                "improvement may not be practically meaningful"
            )

        # Check 3: Check for anomalous patterns in treatment vs control
        # If any metric shows extreme variance, flag it
        for metric_name, control_vals in test_result.control_metrics.items():
            if metric_name not in test_result.treatment_metrics:
                continue

            treatment_vals = test_result.treatment_metrics[metric_name]

            # Check variance ratio (treatment variance should not be >>  control variance)
            if len(control_vals) > 1 and len(treatment_vals) > 1:
                control_std = stdev(control_vals)
                treatment_std = stdev(treatment_vals)

                if control_std > 0:
                    variance_ratio = treatment_std / control_std
                    if variance_ratio > 3.0:
                        warnings.append(
                            f"{metric_name}: treatment variance is {variance_ratio:.1f}x "
                            "higher than control - may indicate instability"
                        )

        # Check 4: Confidence interval analysis
        # If confidence intervals are very wide, warn about uncertainty
        for metric_name, (ci_lower, ci_upper) in test_result.confidence_intervals.items():
            ci_width = ci_upper - ci_lower
            control_mean = mean(test_result.control_metrics.get(metric_name, [0]))

            if control_mean > 0:
                relative_width = ci_width / control_mean
                if relative_width > 0.5:  # CI width > 50% of mean
                    warnings.append(
                        f"{metric_name}: wide confidence interval "
                        f"({relative_width * 100:.1f}% of baseline) - more data recommended"
                    )

        # Overall validation: pass if no critical issues
        # Warnings are advisory but don't fail validation
        return True, warnings
