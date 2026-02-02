"""Quality monitoring and auto-switching for generative AI models."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """Quality metrics for a single generation output."""

    relevance_score: float  # 0.0 to 1.0 - how well output matches request
    coherence_rating: float  # 0.0 to 1.0 - logical consistency and clarity
    completeness_score: float  # 0.0 to 1.0 - how complete the output is
    generation_time: float  # seconds taken to generate
    user_satisfaction: Optional[float] = None  # 0.0 to 1.0 - optional user feedback
    metadata: Dict = field(default_factory=dict)

    def calculate_overall_score(self) -> float:
        """Calculate overall quality score from component metrics."""
        # Weight the metrics: relevance 50%, coherence 30%, completeness 20%
        overall = (
            self.relevance_score * 0.5 + self.coherence_rating * 0.3 + self.completeness_score * 0.2
        )
        # Apply user satisfaction as a modifier if available
        if self.user_satisfaction is not None:
            overall = (overall * 0.7) + (self.user_satisfaction * 0.3)
        return min(1.0, max(0.0, overall))


@dataclass
class ModelQualitySnapshot:
    """Quality snapshot for a specific model over a time period."""

    model_id: str
    provider: str
    evaluation_window_minutes: int
    timestamp: datetime
    total_generations: int
    average_quality_score: float
    min_quality_score: float
    max_quality_score: float
    quality_trend: str  # 'improving', 'stable', 'degrading'
    avg_generation_time: float
    success_rate: float  # Percentage of successful generations
    switching_count: int = 0  # How many times switched away from this model


@dataclass
class QualityAlert:
    """Alert for quality issues with a model."""

    alert_type: str  # 'quality_degradation', 'slow_generation', 'high_failure_rate'
    model_id: str
    provider: str
    severity: str  # 'warning', 'critical'
    message: str
    timestamp: datetime
    suggested_action: Optional[str] = None


class QualityMonitor:
    """Monitor and track quality of generative AI model outputs."""

    # Configuration constants
    QUALITY_HISTORY_WINDOW = 100  # Keep last N generations per model
    EVALUATION_WINDOW_MINUTES = 30  # Calculate metrics over 30-minute windows
    QUALITY_DEGRADATION_THRESHOLD = 0.75  # Alert if average quality drops below this
    SLOW_GENERATION_THRESHOLD = 30  # Alert if generation takes > 30 seconds
    FAILURE_RATE_THRESHOLD = 0.2  # Alert if failure rate > 20%
    MIN_GENERATIONS_FOR_EVALUATION = 5  # Need at least 5 generations to evaluate
    AUTO_SWITCH_QUALITY_GAP = 0.15  # Switch if another model is 15% better

    def __init__(self):
        """Initialize quality monitor."""
        self.quality_history: Dict[str, List[QualityMetrics]] = {}
        self.model_stats: Dict[str, Dict] = {}
        self.alerts: List[QualityAlert] = []
        self.last_model_for_capability: Dict[str, str] = {}  # Track last used model per capability
        self.quality_snapshots: Dict[str, List[ModelQualitySnapshot]] = {}
        self.last_evaluation_time: Dict[str, datetime] = {}

    def record_generation(
        self,
        model_id: str,
        provider: str,
        capability_type: str,
        metrics: QualityMetrics,
    ) -> None:
        """Record quality metrics for a generation.

        Args:
            model_id: ID of the model used
            provider: Provider name
            capability_type: Type of capability (image_generation, video_generation, etc.)
            metrics: QualityMetrics object with measured quality data
        """
        # Initialize history for this model if needed
        if model_id not in self.quality_history:
            self.quality_history[model_id] = []
            self.model_stats[model_id] = {
                "provider": provider,
                "total_generations": 0,
                "failed_generations": 0,
                "total_generation_time": 0.0,
                "created_at": datetime.now(),
                "last_generation": None,
            }

        # Add to history, keeping only recent generations
        self.quality_history[model_id].append(metrics)
        if len(self.quality_history[model_id]) > self.QUALITY_HISTORY_WINDOW:
            self.quality_history[model_id].pop(0)

        # Update model stats
        stats = self.model_stats[model_id]
        stats["total_generations"] += 1
        stats["total_generation_time"] += metrics.generation_time
        stats["last_generation"] = datetime.now()

        logger.debug(
            f"Recorded quality metrics for {model_id}: "
            f"overall_score={metrics.calculate_overall_score():.2f}"
        )

        # Store last used model for this capability
        self.last_model_for_capability[capability_type] = model_id

    def record_generation_failure(
        self, model_id: str, provider: str = "unknown", error: str = ""
    ) -> None:
        """Record a failed generation attempt.

        Args:
            model_id: ID of the model that failed
            provider: Provider name (optional)
            error: Error message describing the failure
        """
        # Initialize stats if needed
        if model_id not in self.model_stats:
            self.model_stats[model_id] = {
                "provider": provider,
                "total_generations": 0,
                "failed_generations": 0,
                "total_generation_time": 0.0,
                "created_at": datetime.now(),
                "last_generation": None,
            }

        stats = self.model_stats[model_id]
        stats["total_generations"] += 1
        stats["failed_generations"] += 1
        stats["last_generation"] = datetime.now()
        logger.warning(f"Generation failure recorded for {model_id}: {error}")

    def get_model_quality_score(self, model_id: str) -> float:
        """Get current average quality score for a model.

        Args:
            model_id: ID of the model

        Returns:
            Average quality score (0.0 to 1.0) or 0.0 if no data
        """
        if model_id not in self.quality_history or not self.quality_history[model_id]:
            return 0.0

        scores = [m.calculate_overall_score() for m in self.quality_history[model_id]]
        return sum(scores) / len(scores) if scores else 0.0

    def get_model_average_generation_time(self, model_id: str) -> float:
        """Get average generation time for a model.

        Args:
            model_id: ID of the model

        Returns:
            Average generation time in seconds
        """
        if model_id not in self.model_stats:
            return 0.0

        stats = self.model_stats[model_id]
        if stats["total_generations"] == 0:
            return 0.0

        return stats["total_generation_time"] / stats["total_generations"]

    def get_model_success_rate(self, model_id: str) -> float:
        """Get success rate for a model.

        Args:
            model_id: ID of the model

        Returns:
            Success rate as percentage (0.0 to 1.0)
        """
        if model_id not in self.model_stats:
            return 0.0

        stats = self.model_stats[model_id]
        if stats["total_generations"] == 0:
            return 0.0

        successful = stats["total_generations"] - stats["failed_generations"]
        return successful / stats["total_generations"]

    def evaluate_model_quality(
        self,
        model_id: str,
        window_minutes: Optional[int] = None,
    ) -> Optional[ModelQualitySnapshot]:
        """Evaluate model quality over a time window.

        Args:
            model_id: ID of the model
            window_minutes: Time window in minutes (defaults to EVALUATION_WINDOW_MINUTES)

        Returns:
            ModelQualitySnapshot or None if insufficient data
        """
        if model_id not in self.quality_history or model_id not in self.model_stats:
            return None

        if window_minutes is None:
            window_minutes = self.EVALUATION_WINDOW_MINUTES

        history = self.quality_history[model_id]
        stats = self.model_stats[model_id]

        # Check if we have enough total generations (including failures)
        if stats["total_generations"] < self.MIN_GENERATIONS_FOR_EVALUATION:
            return None

        # Get metrics from recent generations
        scores = [m.calculate_overall_score() for m in history]
        gen_times = [m.generation_time for m in history]

        avg_score = sum(scores) / len(scores) if scores else 0.0
        min_score = min(scores)
        max_score = max(scores)
        avg_gen_time = sum(gen_times) / len(gen_times) if gen_times else 0.0

        # Determine trend
        if len(scores) >= 3:
            recent = scores[-3:]
            older = scores[:-3]
            recent_avg = sum(recent) / len(recent)
            older_avg = sum(older) / len(older) if older else recent_avg
            # Use a more sensitive threshold - 2% improvement/degradation
            if recent_avg > older_avg + 0.02:
                trend = "improving"
            elif recent_avg < older_avg - 0.02:
                trend = "degrading"
            else:
                trend = "stable"
        else:
            trend = "stable"

        success_rate = self.get_model_success_rate(model_id)

        snapshot = ModelQualitySnapshot(
            model_id=model_id,
            provider=stats.get("provider", "unknown"),
            evaluation_window_minutes=window_minutes,
            timestamp=datetime.now(),
            total_generations=len(history),
            average_quality_score=avg_score,
            min_quality_score=min_score,
            max_quality_score=max_score,
            quality_trend=trend,
            avg_generation_time=avg_gen_time,
            success_rate=success_rate,
        )

        # Store snapshot
        if model_id not in self.quality_snapshots:
            self.quality_snapshots[model_id] = []
        self.quality_snapshots[model_id].append(snapshot)

        # Keep only recent snapshots
        self.quality_snapshots[model_id] = self.quality_snapshots[model_id][-20:]

        return snapshot

    def check_quality_thresholds(self, model_id: str) -> List[QualityAlert]:
        """Check if model violates any quality thresholds.

        Args:
            model_id: ID of the model

        Returns:
            List of QualityAlert objects for any threshold violations
        """
        snapshot = self.evaluate_model_quality(model_id)
        if not snapshot:
            return []

        new_alerts = []

        # Check quality degradation
        if snapshot.average_quality_score < self.QUALITY_DEGRADATION_THRESHOLD:
            alert = QualityAlert(
                alert_type="quality_degradation",
                model_id=model_id,
                provider=snapshot.provider,
                severity="warning" if snapshot.average_quality_score > 0.6 else "critical",
                message=(
                    f"Quality score degraded to {snapshot.average_quality_score:.2f} "
                    f"(threshold: {self.QUALITY_DEGRADATION_THRESHOLD})"
                ),
                timestamp=datetime.now(),
                suggested_action="Consider switching to a higher quality model",
            )
            new_alerts.append(alert)

        # Check generation speed
        if snapshot.avg_generation_time > self.SLOW_GENERATION_THRESHOLD:
            alert = QualityAlert(
                alert_type="slow_generation",
                model_id=model_id,
                provider=snapshot.provider,
                severity="warning",
                message=(
                    f"Average generation time is {snapshot.avg_generation_time:.1f}s "
                    f"(threshold: {self.SLOW_GENERATION_THRESHOLD}s)"
                ),
                timestamp=datetime.now(),
                suggested_action="Consider using a faster model or optimizing parameters",
            )
            new_alerts.append(alert)

        # Check failure rate
        if snapshot.success_rate < (1.0 - self.FAILURE_RATE_THRESHOLD):
            alert = QualityAlert(
                alert_type="high_failure_rate",
                model_id=model_id,
                provider=snapshot.provider,
                severity="critical",
                message=(
                    f"Failure rate is {(1.0 - snapshot.success_rate) * 100:.1f}% "
                    f"(threshold: {self.FAILURE_RATE_THRESHOLD * 100}%)"
                ),
                timestamp=datetime.now(),
                suggested_action="Investigate model health and provider status",
            )
            new_alerts.append(alert)

        # Add new alerts to history
        for alert in new_alerts:
            # Check if similar alert already exists
            existing = any(
                a.alert_type == alert.alert_type
                and a.model_id == alert.model_id
                and (datetime.now() - a.timestamp).total_seconds() < 300  # Within 5 minutes
                for a in self.alerts
            )
            if not existing:
                self.alerts.append(alert)
                logger.warning(f"Quality alert: {alert.message}")

        return new_alerts

    def should_switch_model(
        self,
        current_model_id: str,
        alternative_models: Dict[str, float],
    ) -> Optional[Tuple[str, str]]:
        """Determine if should switch from current model to alternative.

        Args:
            current_model_id: ID of currently used model
            alternative_models: Dict mapping model IDs to their quality scores

        Returns:
            Tuple of (new_model_id, reason) or None if switching not recommended
        """
        current_score = self.get_model_quality_score(current_model_id)

        # Check if any alternative is significantly better
        for alt_model_id, alt_score in alternative_models.items():
            if alt_model_id == current_model_id:
                continue

            quality_gap = alt_score - current_score
            if quality_gap >= self.AUTO_SWITCH_QUALITY_GAP:
                reason = (
                    f"Model {alt_model_id} is {quality_gap * 100:.1f}% better "
                    f"({alt_score:.2f} vs {current_score:.2f})"
                )
                logger.info(f"Recommending model switch: {reason}")
                return (alt_model_id, reason)

        return None

    def get_quality_dashboard(self) -> Dict:
        """Get comprehensive quality monitoring dashboard.

        Returns:
            Dict with quality status for all models
        """
        dashboard = {
            "timestamp": datetime.now().isoformat(),
            "total_models_monitored": len(self.quality_history),
            "active_alerts": len(
                [a for a in self.alerts if (datetime.now() - a.timestamp).total_seconds() < 3600]
            ),
            "models": {},
        }

        for model_id, history in self.quality_history.items():
            if not history:
                continue

            snapshot = self.evaluate_model_quality(model_id)
            if not snapshot:
                continue

            stats = self.model_stats[model_id]
            dashboard["models"][model_id] = {
                "provider": stats.get("provider", "unknown"),
                "quality_score": snapshot.average_quality_score,
                "quality_trend": snapshot.quality_trend,
                "generation_time": f"{snapshot.avg_generation_time:.2f}s",
                "success_rate": f"{snapshot.success_rate * 100:.1f}%",
                "total_generations": snapshot.total_generations,
                "last_generation": (
                    stats["last_generation"].isoformat() if stats["last_generation"] else None
                ),
            }

        return dashboard

    def get_alerts(self, model_id: Optional[str] = None, limit: int = 100) -> List[QualityAlert]:
        """Get quality alerts.

        Args:
            model_id: Optional filter by model ID
            limit: Maximum number of alerts to return

        Returns:
            List of QualityAlert objects
        """
        filtered = self.alerts
        if model_id:
            filtered = [a for a in filtered if a.model_id == model_id]

        # Sort by timestamp (newest first)
        filtered.sort(key=lambda a: a.timestamp, reverse=True)
        return filtered[:limit]

    def reset_model_tracking(self, model_id: str) -> None:
        """Reset quality tracking for a model.

        Args:
            model_id: ID of the model to reset
        """
        if model_id in self.quality_history:
            self.quality_history[model_id] = []
        if model_id in self.model_stats:
            self.model_stats[model_id] = {
                "provider": self.model_stats[model_id].get("provider", "unknown"),
                "total_generations": 0,
                "failed_generations": 0,
                "total_generation_time": 0.0,
                "created_at": datetime.now(),
                "last_generation": None,
            }
        logger.info(f"Quality tracking reset for model {model_id}")

    def get_model_quality_timeline(self, model_id: str) -> List[ModelQualitySnapshot]:
        """Get quality snapshots over time for a model.

        Args:
            model_id: ID of the model

        Returns:
            List of ModelQualitySnapshot objects in chronological order
        """
        if model_id not in self.quality_snapshots:
            return []
        return self.quality_snapshots[model_id]
