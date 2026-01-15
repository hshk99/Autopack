"""ROAD-J: Self-Healing Engine - Automatic recovery from telemetry anomalies.

Responds to ROAD-G anomaly alerts with automatic healing actions:
- Token spike → context pruning + retry
- Duration anomaly → model escalation + timeout extension
- Failure rate critical → diagnostic analysis + replan trigger

Integrates with:
- ROAD-G: TelemetryAnomalyDetector (alert source)
- error_recovery.py: DoctorAction recovery pipeline
- executor/phase_orchestrator.py: Phase execution context
"""

import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

from .anomaly_detector import AnomalyAlert, AlertSeverity

logger = logging.getLogger(__name__)


class HealingAction(Enum):
    """Auto-healing actions mapped to recovery strategies."""

    # Context management
    PRUNE_CONTEXT = "prune_context"  # Reduce token usage
    OPTIMIZE_PROMPT = "optimize_prompt"  # Rewrite for efficiency

    # Model adjustments
    ESCALATE_MODEL = "escalate_model"  # Switch to more capable model
    DOWNGRADE_MODEL = "downgrade_model"  # Switch to cheaper model
    EXTEND_TIMEOUT = "extend_timeout"  # Increase time limits

    # Execution flow
    RETRY_PHASE = "retry_phase"  # Retry current phase
    REPLAN_PHASE = "replan_phase"  # Request phase replan
    SKIP_PHASE = "skip_phase"  # Skip problematic phase
    ROLLBACK_RUN = "rollback_run"  # Rollback entire run

    # Monitoring
    ALERT_ONLY = "alert_only"  # Just log, no action
    ESCALATE_HUMAN = "escalate_human"  # Needs human intervention


@dataclass
class HealingDecision:
    """Decision on how to heal an anomaly."""

    alert: AnomalyAlert
    action: HealingAction
    reason: str
    parameters: Dict[str, Any]
    confidence: float  # 0.0-1.0, how confident we are in this action


class AutoHealingEngine:
    """Automatically responds to anomaly alerts with recovery actions.

    Implements ROAD-J self-healing:
    1. Receives AnomalyAlert from ROAD-G
    2. Analyzes alert context (metric, severity, phase_id)
    3. Selects appropriate healing action
    4. Logs decision and delegates to execution callback

    Example usage:
        auto_healer = AutoHealingEngine(
            enable_aggressive_healing=False,
            healing_executor=my_healing_callback
        )
        auto_healer.heal(alert)
    """

    def __init__(
        self,
        enable_aggressive_healing: bool = False,
        healing_executor: Optional[Callable[[HealingDecision], bool]] = None,
    ):
        """
        Args:
            enable_aggressive_healing: If True, take more proactive actions
                                      (e.g., auto-rollback on critical)
            healing_executor: Callback to execute healing decision
                             Returns True if healing succeeded
        """
        self.enable_aggressive_healing = enable_aggressive_healing
        self.healing_executor = healing_executor

        # Track healing history to avoid loops
        self.healing_history: Dict[str, int] = {}  # phase_id -> healing_count
        self.max_healing_attempts = 3

    def heal(self, alert: AnomalyAlert) -> Optional[HealingDecision]:
        """
        Analyze alert and perform automatic healing.

        Returns:
            HealingDecision if action was taken, None if alert ignored
        """
        # Check if we've exceeded max healing attempts for this phase
        phase_id = alert.phase_id
        if self._exceeds_max_attempts(phase_id):
            logger.warning(
                f"[ROAD-J] Max healing attempts ({self.max_healing_attempts}) "
                f"exceeded for phase {phase_id}, escalating to human"
            )
            return self._escalate_to_human(alert)

        # Route to severity-specific handler
        if alert.severity == AlertSeverity.CRITICAL:
            decision = self._heal_critical(alert)
        elif alert.severity == AlertSeverity.WARNING:
            decision = self._heal_warning(alert)
        else:
            decision = self._heal_info(alert)

        if decision and decision.action != HealingAction.ALERT_ONLY:
            self._record_healing_attempt(phase_id)
            self._log_healing_decision(decision)

            # Execute healing if executor is provided
            if self.healing_executor:
                success = self.healing_executor(decision)
                if success:
                    logger.info(
                        f"[ROAD-J] Healing succeeded: {decision.action.value} "
                        f"for {alert.metric} anomaly"
                    )
                else:
                    logger.error(
                        f"[ROAD-J] Healing failed: {decision.action.value} "
                        f"for {alert.metric} anomaly"
                    )

        return decision

    def _heal_critical(self, alert: AnomalyAlert) -> HealingDecision:
        """Handle CRITICAL severity alerts."""
        metric = alert.metric

        if metric == "failure_rate":
            # High failure rate: diagnostic analysis + replan
            if self.enable_aggressive_healing:
                return HealingDecision(
                    alert=alert,
                    action=HealingAction.REPLAN_PHASE,
                    reason=(
                        f"Failure rate {alert.current_value:.1%} critically high. "
                        "Replanning phase with corrective measures."
                    ),
                    parameters={
                        "phase_id": alert.phase_id,
                        "failure_rate": alert.current_value,
                        "threshold": alert.threshold,
                    },
                    confidence=0.8,
                )
            else:
                return HealingDecision(
                    alert=alert,
                    action=HealingAction.ESCALATE_HUMAN,
                    reason=(
                        f"Failure rate {alert.current_value:.1%} critically high. "
                        "Requires human analysis (aggressive healing disabled)."
                    ),
                    parameters={"alert_id": alert.alert_id},
                    confidence=1.0,
                )

        elif metric == "tokens":
            # Severe token spike: aggressive context pruning
            return HealingDecision(
                alert=alert,
                action=HealingAction.PRUNE_CONTEXT,
                reason=(
                    f"Token usage {alert.current_value} critically exceeds "
                    f"threshold {alert.threshold}. Pruning context aggressively."
                ),
                parameters={
                    "phase_id": alert.phase_id,
                    "target_tokens": int(alert.baseline * 1.5),  # Prune to 1.5x baseline
                    "current_tokens": int(alert.current_value),
                },
                confidence=0.7,
            )

        elif metric == "duration":
            # Timeout risk: escalate model + extend timeout
            return HealingDecision(
                alert=alert,
                action=HealingAction.ESCALATE_MODEL,
                reason=(
                    f"Duration {alert.current_value}s critically exceeds "
                    f"threshold {alert.threshold}s. Escalating to more capable model."
                ),
                parameters={
                    "phase_id": alert.phase_id,
                    "extend_timeout_by": 1.5,  # Extend by 50%
                },
                confidence=0.6,
            )

        # Default: alert only for unknown critical metrics
        return HealingDecision(
            alert=alert,
            action=HealingAction.ALERT_ONLY,
            reason=f"Unknown critical metric {metric}, logging only",
            parameters={},
            confidence=0.0,
        )

    def _heal_warning(self, alert: AnomalyAlert) -> HealingDecision:
        """Handle WARNING severity alerts."""
        metric = alert.metric

        if metric == "tokens":
            # Token spike: optimize prompt or prune context
            return HealingDecision(
                alert=alert,
                action=HealingAction.OPTIMIZE_PROMPT,
                reason=(
                    f"Token usage {alert.current_value} above baseline {alert.baseline}. "
                    "Optimizing prompt for efficiency."
                ),
                parameters={
                    "phase_id": alert.phase_id,
                    "target_reduction": 0.3,  # Aim for 30% reduction
                },
                confidence=0.6,
            )

        elif metric == "duration":
            # Duration warning: consider model escalation
            if alert.current_value > alert.threshold * 1.3:
                # >30% over threshold: escalate
                return HealingDecision(
                    alert=alert,
                    action=HealingAction.ESCALATE_MODEL,
                    reason=(
                        f"Duration {alert.current_value}s significantly exceeds "
                        f"threshold {alert.threshold}s. Escalating model."
                    ),
                    parameters={"phase_id": alert.phase_id},
                    confidence=0.5,
                )
            else:
                # Moderate overage: just monitor
                return HealingDecision(
                    alert=alert,
                    action=HealingAction.ALERT_ONLY,
                    reason="Duration slightly elevated, monitoring",
                    parameters={},
                    confidence=0.8,
                )

        # Default: alert only
        return HealingDecision(
            alert=alert,
            action=HealingAction.ALERT_ONLY,
            reason=f"Warning for {metric}, no action needed",
            parameters={},
            confidence=0.9,
        )

    def _heal_info(self, alert: AnomalyAlert) -> HealingDecision:
        """Handle INFO severity alerts."""
        # INFO alerts are informational only, no healing needed
        return HealingDecision(
            alert=alert,
            action=HealingAction.ALERT_ONLY,
            reason="Informational alert, no action required",
            parameters={},
            confidence=1.0,
        )

    def _escalate_to_human(self, alert: AnomalyAlert) -> HealingDecision:
        """Escalate to human intervention after max attempts."""
        return HealingDecision(
            alert=alert,
            action=HealingAction.ESCALATE_HUMAN,
            reason=f"Max healing attempts exceeded for {alert.phase_id}",
            parameters={"alert_id": alert.alert_id, "phase_id": alert.phase_id},
            confidence=1.0,
        )

    def _exceeds_max_attempts(self, phase_id: str) -> bool:
        """Check if phase has exceeded max healing attempts."""
        return self.healing_history.get(phase_id, 0) >= self.max_healing_attempts

    def _record_healing_attempt(self, phase_id: str) -> None:
        """Record a healing attempt for tracking."""
        self.healing_history[phase_id] = self.healing_history.get(phase_id, 0) + 1

    def _log_healing_decision(self, decision: HealingDecision) -> None:
        """Log healing decision for observability."""
        logger.info(
            f"[ROAD-J] Healing decision: {decision.action.value} "
            f"(confidence: {decision.confidence:.1%}) - {decision.reason}"
        )

    def reset_healing_history(self, phase_id: Optional[str] = None) -> None:
        """Reset healing attempt counter.

        Args:
            phase_id: If provided, reset only for this phase.
                     If None, reset all.
        """
        if phase_id:
            self.healing_history.pop(phase_id, None)
        else:
            self.healing_history.clear()
        logger.debug(f"[ROAD-J] Reset healing history for {phase_id or 'all phases'}")

    def get_healing_stats(self) -> Dict[str, Any]:
        """Get statistics about healing attempts."""
        return {
            "total_phases_healed": len(self.healing_history),
            "phases_at_max_attempts": sum(
                1 for count in self.healing_history.values() if count >= self.max_healing_attempts
            ),
            "healing_history": dict(self.healing_history),
        }
